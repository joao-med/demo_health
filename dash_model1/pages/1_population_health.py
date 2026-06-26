import streamlit as st
import duckdb
import pandas as pd
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from components.filters import render_sidebar_filters
from components.panel_builder import (
    render_panel,
    CHART_BUILDERS,
    BIOMARKER_LABELS,
    STRATIFY_OPTIONS,
)

DB_PATH = "analytics.duckdb"


@st.cache_data(show_spinner=False)
def load_lab_results(stakeholder_id=None):
    con = duckdb.connect(DB_PATH, read_only=True)
    if stakeholder_id:
        df = con.execute(
            "SELECT * FROM lab_results WHERE stakeholder = ?", [stakeholder_id]
        ).df()
    else:
        df = con.execute("SELECT * FROM lab_results").df()
    con.close()
    return df


@st.cache_data(show_spinner=False)
def load_patient_flags(stakeholder_id=None):
    con = duckdb.connect(DB_PATH, read_only=True)
    if stakeholder_id:
        df = con.execute(
            "SELECT * FROM patient_flags WHERE stakeholder = ?", [stakeholder_id]
        ).df()
    else:
        df = con.execute("SELECT * FROM patient_flags").df()
    con.close()
    return df


role = st.session_state.get("role", "admin")
stakeholder_id = st.session_state.get("stakeholder_id", None)
is_admin = role == "admin"

df_raw = load_lab_results(stakeholder_id)
df_flags = load_patient_flags(stakeholder_id)

filtered_raw = render_sidebar_filters(df_raw, show_stakeholder=is_admin)
filtered_flags = df_flags[
    df_flags["patient_id"].isin(filtered_raw["patient_id"].unique())
]

st.title("Population Health Overview")
st.caption(
    "Admin view — all stakeholders"
    if is_admin
    else f"Stakeholder view — {stakeholder_id}"
)

# KPI cards
total_patients = filtered_flags["patient_id"].nunique()
n_glycemic = filtered_flags["glycemic_status"].notna().sum()
n_ckd = filtered_flags["ckd_stage"].notna().sum()
n_ldl = filtered_flags["ldl_status"].notna().sum()
n_vitd = filtered_flags["vitd_status"].notna().sum()

pct_diabetes = (filtered_flags["glycemic_status"] == "Diabetes").sum() / max(n_glycemic, 1)
pct_prediab = (filtered_flags["glycemic_status"] == "Pre-diabetes").sum() / max(n_glycemic, 1)
pct_ckd3 = (
    filtered_flags["ckd_stage"].isin(["G3a", "G3b", "G4", "G5"]).sum() / max(n_ckd, 1)
)
pct_ldl_high = (
    filtered_flags["ldl_status"].isin(["High", "Very High"]).sum() / max(n_ldl, 1)
)
pct_vitd_def = (
    filtered_flags["vitd_status"] == "Deficient"
).sum() / max(n_vitd, 1)
pct_anemia = (
    filtered_flags["anemia_status"] == "Anemia"
).sum() / max(filtered_flags["anemia_status"].notna().sum(), 1)

k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("Patients", f"{total_patients:,}")
k2.metric("Diabetes", f"{pct_diabetes:.1%}")
k3.metric("Pre-diabetes", f"{pct_prediab:.1%}")
k4.metric("CKD Stage 3+", f"{pct_ckd3:.1%}")
k5.metric("LDL High+", f"{pct_ldl_high:.1%}")
k6.metric("Vit D Deficient", f"{pct_vitd_def:.1%}")

st.divider()

# Configurable panels
BIOMARKER_OPTIONS = list(BIOMARKER_LABELS.keys())
CHART_OPTIONS = list(CHART_BUILDERS.keys())

DEFAULT_PANELS = [
    {"biomarker": "hba1c", "chart_type": "Histogram", "stratify_by": "sex"},
    {"biomarker": "ldl", "chart_type": "Histogram", "stratify_by": "none"},
    {"biomarker": "egfr", "chart_type": "Histogram", "stratify_by": "none"},
    {"biomarker": "hba1c", "chart_type": "Time Series", "stratify_by": "stakeholder"},
    {"biomarker": "vitamin_d", "chart_type": "Bar", "stratify_by": "sex"},
    {"biomarker": "hemoglobin", "chart_type": "Box Plot", "stratify_by": "sex"},
]

for row_i in range(2):
    cols = st.columns(3)
    for col_i in range(3):
        panel_i = row_i * 3 + col_i
        default = DEFAULT_PANELS[panel_i]

        with cols[col_i]:
            c1, c2, c3 = st.columns(3)
            with c1:
                biomarker = st.selectbox(
                    "Biomarker",
                    BIOMARKER_OPTIONS,
                    index=BIOMARKER_OPTIONS.index(default["biomarker"]),
                    key=f"bio_{panel_i}",
                    label_visibility="collapsed",
                )
            with c2:
                chart_type = st.selectbox(
                    "Chart",
                    CHART_OPTIONS,
                    index=CHART_OPTIONS.index(default["chart_type"]),
                    key=f"chart_{panel_i}",
                    label_visibility="collapsed",
                )
            with c3:
                stratify = st.selectbox(
                    "By",
                    STRATIFY_OPTIONS,
                    index=STRATIFY_OPTIONS.index(default["stratify_by"]),
                    key=f"strat_{panel_i}",
                    label_visibility="collapsed",
                )

            config = {
                "biomarker": biomarker,
                "chart_type": chart_type,
                "stratify_by": stratify,
            }

            try:
                chart = render_panel(config, filtered_raw)
                st.altair_chart(chart, use_container_width=True)
            except Exception as e:
                st.warning(f"Could not render panel: {e}")
