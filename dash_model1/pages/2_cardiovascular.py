import streamlit as st
import duckdb
import pandas as pd
import altair as alt
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from components.filters import render_sidebar_filters
from components.panel_builder import (
    render_panel,
    CHART_BUILDERS,
    BIOMARKER_LABELS,
    CV_STRATIFY_OPTIONS,
)

DB_PATH = "analytics.duckdb"

RISK_ORDER = [
    "Very High - Severe Hypercholesterolemia",
    "High - Diabetes + Dyslipidemia",
    "High - CKD + Dyslipidemia",
    "Intermediate-High",
    "Borderline",
    "Lower Risk",
]

RISK_COLORS = {
    "Very High - Severe Hypercholesterolemia": "#d62728",
    "High - Diabetes + Dyslipidemia": "#e87a1e",
    "High - CKD + Dyslipidemia": "#e8a21e",
    "Intermediate-High": "#f0c040",
    "Borderline": "#8fbcdb",
    "Lower Risk": "#2ca02c",
}


@st.cache_data(show_spinner=False)
def load_cv_flags(_stakeholder_id=None):
    con = duckdb.connect(DB_PATH, read_only=True)
    q = "SELECT * FROM cv_risk_flags"
    if _stakeholder_id:
        q += " WHERE stakeholder = ?"
        df = con.execute(q, [_stakeholder_id]).df()
    else:
        df = con.execute(q).df()
    con.close()
    return df


@st.cache_data(show_spinner=False)
def load_lab_results(_stakeholder_id=None):
    con = duckdb.connect(DB_PATH, read_only=True)
    q = "SELECT * FROM lab_results"
    if _stakeholder_id:
        q += " WHERE stakeholder = ?"
        df = con.execute(q, [_stakeholder_id]).df()
    else:
        df = con.execute(q).df()
    con.close()
    return df


role = st.session_state.get("role", "admin")
stakeholder_id = st.session_state.get("stakeholder_id", None)
is_admin = role == "admin"

df_cv = load_cv_flags(stakeholder_id)
df_raw = load_lab_results(stakeholder_id)

filtered_raw = render_sidebar_filters(df_raw, show_stakeholder=is_admin)
patient_ids = filtered_raw["patient_id"].unique()
filtered_cv = df_cv[df_cv["patient_id"].isin(patient_ids)]

st.title("Cardiovascular Risk Dashboard")
st.caption("Lab-based risk stratification - ACC/AHA 2018 simplified (no BP/smoking required)")

n_patients = filtered_cv["patient_id"].nunique()
n_statin = filtered_cv["statin_eligible"].notna().sum()
pct_statin = filtered_cv["statin_eligible"].sum() / max(n_statin, 1)

n_risk = filtered_cv["cv_risk_category"].notna().sum()
pct_very_high = (
    (filtered_cv["cv_risk_category"] == "Very High - Severe Hypercholesterolemia").sum()
    / max(n_risk, 1)
)
pct_high = (
    filtered_cv["cv_risk_category"].str.startswith("High -", na=False).sum()
    / max(n_risk, 1)
)

mean_ldl = filtered_cv["ldl"].dropna().mean()
mean_tc_hdl = filtered_cv["tc_hdl_ratio"].dropna().mean()

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Patients", f"{n_patients:,}")
k2.metric("Statin Eligible", f"{pct_statin:.1%}")
k3.metric("Very High CV Risk", f"{pct_very_high:.1%}")
k4.metric("Mean LDL", f"{mean_ldl:.0f} mg/dL")
k5.metric("Mean TC/HDL", f"{mean_tc_hdl:.2f}")

st.divider()

st.subheader("Risk Stratification Overview")

col_left, col_right = st.columns([2, 1])

with col_left:
    risk_counts = (
        filtered_cv["cv_risk_category"]
        .value_counts()
        .reset_index()
    )
    risk_counts.columns = ["category", "count"]
    risk_counts["pct"] = risk_counts["count"] / risk_counts["count"].sum()
    risk_counts["order"] = risk_counts["category"].map(
        {v: i for i, v in enumerate(RISK_ORDER)}
    )
    risk_counts = risk_counts.sort_values("order")

    color_scale = alt.Scale(
        domain=list(RISK_COLORS.keys()),
        range=list(RISK_COLORS.values()),
    )

    bar = (
        alt.Chart(risk_counts)
        .mark_bar()
        .encode(
            x=alt.X("count:Q", title="Patients"),
            y=alt.Y(
                "category:N",
                sort=RISK_ORDER,
                title=None,
                axis=alt.Axis(labelLimit=300),
            ),
            color=alt.Color("category:N", scale=color_scale, legend=None),
            tooltip=[
                alt.Tooltip("category:N", title="Risk Category"),
                alt.Tooltip("count:Q", title="Patients"),
                alt.Tooltip("pct:Q", title="% of population", format=".1%"),
            ],
        )
        .properties(height=240)
    )
    st.altair_chart(bar, use_container_width=True)

with col_right:
    st.markdown("**ACC/AHA 2018 - lab-only criteria**")
    st.markdown("""
- **Very High:** LDL >= 190 mg/dL
- **High (DM):** Diabetes + age 40-75 + LDL >= 70
- **High (CKD):** CKD G3+ + LDL >= 100
- **Intermediate-High:** LDL >= 160 + age >= 40
- **Borderline:** LDL >= 130
- **Lower Risk:** remaining
""")
    st.caption("Note: full PCE/Framingham score requires systolic BP and smoking status, not available in lab-only databases.")

st.divider()

st.subheader("Explore by Risk Category")
st.caption(
    "Use the dropdowns to stratify any biomarker by CV risk score, AIP, TG/HDL, or other categories."
)

df_enriched = filtered_raw.merge(
    filtered_cv[[
        "patient_id", "cv_risk_category", "aip_category",
        "tg_hdl_category", "non_hdl_status", "glycemic_status",
        "ckd_stage", "hscrp_category", "statin_eligible",
    ]],
    on="patient_id",
    how="left",
)

BIOMARKER_OPTIONS = list(BIOMARKER_LABELS.keys())
CHART_OPTIONS = list(CHART_BUILDERS.keys())

DEFAULT_PANELS = [
    {"biomarker": "hba1c", "chart_type": "Box Plot", "stratify_by": "cv_risk_category"},
    {"biomarker": "egfr", "chart_type": "Box Plot", "stratify_by": "cv_risk_category"},
    {"biomarker": "ldl", "chart_type": "Histogram", "stratify_by": "aip_category"},
    {"biomarker": "triglycerides", "chart_type": "Box Plot", "stratify_by": "tg_hdl_category"},
    {"biomarker": "hscrp", "chart_type": "Box Plot", "stratify_by": "cv_risk_category"},
    {"biomarker": "hdl", "chart_type": "Bar", "stratify_by": "glycemic_status"},
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
                    key=f"cv_bio_{panel_i}",
                    label_visibility="collapsed",
                )
            with c2:
                chart_type = st.selectbox(
                    "Chart",
                    CHART_OPTIONS,
                    index=CHART_OPTIONS.index(default["chart_type"]),
                    key=f"cv_chart_{panel_i}",
                    label_visibility="collapsed",
                )
            with c3:
                stratify = st.selectbox(
                    "By",
                    CV_STRATIFY_OPTIONS,
                    index=CV_STRATIFY_OPTIONS.index(default["stratify_by"]),
                    key=f"cv_strat_{panel_i}",
                    label_visibility="collapsed",
                )

            config = {
                "biomarker": biomarker,
                "chart_type": chart_type,
                "stratify_by": stratify,
            }

            try:
                chart = render_panel(config, df_enriched)
                st.altair_chart(chart, use_container_width=True)
            except Exception as e:
                st.warning(f"Could not render: {e}")
