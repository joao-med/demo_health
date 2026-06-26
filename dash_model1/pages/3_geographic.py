import streamlit as st
import duckdb
import pandas as pd
import altair as alt
import folium
from streamlit_folium import st_folium
import requests
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

DB_PATH = "analytics.duckdb"
GEOJSON_PATH = "data/countries.geojson"
GEOJSON_URL = (
    "https://raw.githubusercontent.com/datasets/geo-countries/master/data/countries.geojson"
)

METRICS = {
    "% Diabetes proxy": "pct_diabetes",
    "% Pre-diabetes": "pct_prediabetes",
    "% CKD Stage 3+": "pct_ckd3",
    "% High LDL": "pct_ldl_high",
    "% Vit D Deficient": "pct_vitd_def",
    "Mean HbA1c": "mean_hba1c",
    "Mean LDL": "mean_ldl",
    "Mean eGFR": "mean_egfr",
}

IS_PCT = {
    "pct_diabetes", "pct_prediabetes", "pct_ckd3", "pct_ldl_high", "pct_vitd_def",
}


@st.cache_data(show_spinner=False)
def load_flags(_stakeholder_id):
    con = duckdb.connect(DB_PATH, read_only=True)
    q = "SELECT * FROM patient_flags"
    if _stakeholder_id:
        q += " WHERE stakeholder = ?"
        df = con.execute(q, [_stakeholder_id]).df()
    else:
        df = con.execute(q).df()
    con.close()
    return df


@st.cache_data(show_spinner=False)
def load_geo(_stakeholder_id):
    con = duckdb.connect(DB_PATH, read_only=True)
    if _stakeholder_id:
        df = con.execute(
            "SELECT patient_id, country, state_region FROM lab_results "
            "WHERE stakeholder = ? GROUP BY patient_id, country, state_region",
            [_stakeholder_id],
        ).df()
    else:
        df = con.execute(
            "SELECT patient_id, country, state_region FROM lab_results "
            "GROUP BY patient_id, country, state_region"
        ).df()
    con.close()
    return df


@st.cache_data(show_spinner=False)
def fetch_geojson():
    if os.path.exists(GEOJSON_PATH):
        with open(GEOJSON_PATH) as f:
            return json.load(f)
    try:
        resp = requests.get(GEOJSON_URL, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        os.makedirs("data", exist_ok=True)
        with open(GEOJSON_PATH, "w") as f:
            json.dump(data, f)
        return data
    except Exception:
        return None


def build_country_stats(df_flags, df_geo):
    merged = df_flags.merge(df_geo[["patient_id", "country", "state_region"]], on="patient_id", how="left")

    def safe_pct(series, mask):
        valid = series.notna()
        return mask[valid].mean() if valid.sum() > 0 else 0.0

    rows = []
    for country, grp in merged.groupby("country"):
        rows.append({
            "country": country,
            "n_patients": len(grp),
            "pct_diabetes": safe_pct(grp["glycemic_status"], grp["glycemic_status"] == "Diabetes"),
            "pct_prediabetes": safe_pct(grp["glycemic_status"], grp["glycemic_status"] == "Pre-diabetes"),
            "pct_ckd3": safe_pct(grp["ckd_stage"], grp["ckd_stage"].isin(["G3a", "G3b", "G4", "G5"])),
            "pct_ldl_high": safe_pct(grp["ldl_status"], grp["ldl_status"].isin(["High", "Very High"])),
            "pct_vitd_def": safe_pct(grp["vitd_status"], grp["vitd_status"] == "Deficient"),
            "mean_hba1c": grp["hba1c"].mean(),
            "mean_ldl": grp["ldl"].mean(),
            "mean_egfr": grp["egfr"].mean(),
        })
    return pd.DataFrame(rows)


def build_region_stats(df_flags, df_geo, country):
    merged = df_flags.merge(df_geo[["patient_id", "country", "state_region"]], on="patient_id", how="left")
    grp = merged[merged["country"] == country]
    rows = []
    for region, rgrp in grp.groupby("state_region"):
        rows.append({
            "state_region": region,
            "n_patients": len(rgrp),
            "pct_diabetes": (rgrp["glycemic_status"] == "Diabetes").mean(),
            "pct_ckd3": rgrp["ckd_stage"].isin(["G3a", "G3b", "G4", "G5"]).mean(),
            "pct_ldl_high": rgrp["ldl_status"].isin(["High", "Very High"]).mean(),
            "mean_hba1c": rgrp["hba1c"].mean(),
            "mean_ldl": rgrp["ldl"].mean(),
        })
    return pd.DataFrame(rows)


role = st.session_state.get("role", "admin")
stakeholder_id = st.session_state.get("stakeholder_id", None)

df_flags = load_flags(stakeholder_id)
df_geo = load_geo(stakeholder_id)
geojson = fetch_geojson()

country_stats = build_country_stats(df_flags, df_geo)

st.title("Geographic Distribution")
st.caption("Population health metrics by country and region")

with st.sidebar:
    st.subheader("Map options")
    selected_metric_label = st.selectbox("Metric to map", list(METRICS.keys()))
    selected_metric = METRICS[selected_metric_label]
    countries_available = sorted(country_stats["country"].tolist())
    selected_country = st.selectbox("Drilldown country", ["All"] + countries_available)

n_countries = country_stats["country"].nunique()
n_patients_total = int(country_stats["n_patients"].sum())
best_idx = country_stats[selected_metric].idxmax()
top_country = country_stats.loc[best_idx, "country"]
top_val = country_stats.loc[best_idx, selected_metric]

k1, k2, k3 = st.columns(3)
k1.metric("Countries", n_countries)
k2.metric("Total patients", f"{n_patients_total:,}")
fmt = f"{top_val:.1%}" if selected_metric in IS_PCT else f"{top_val:.1f}"
k3.metric(f"Highest {selected_metric_label}", f"{top_country} ({fmt})")

st.divider()

col_map, col_table = st.columns([3, 2])

with col_map:
    st.subheader("World Map")
    if geojson is None:
        st.warning("GeoJSON unavailable - no internet connection. Showing table only.")
    else:
        m = folium.Map(location=[20, 5], zoom_start=2, tiles="CartoDB positron")
        folium.Choropleth(
            geo_data=geojson,
            data=country_stats,
            columns=["country", selected_metric],
            key_on="feature.properties.name",
            fill_color="YlOrRd",
            fill_opacity=0.75,
            line_opacity=0.3,
            legend_name=selected_metric_label,
            nan_fill_color="#e8e8e8",
            highlight=True,
        ).add_to(m)
        st_folium(m, width=700, height=420, returned_objects=[])

with col_table:
    st.subheader("Country comparison")
    display = country_stats[["country", "n_patients", "pct_diabetes", "pct_ckd3", "pct_ldl_high", "mean_hba1c"]].copy()
    display.columns = ["Country", "Patients", "Diabetes %", "CKD 3+%", "High LDL %", "Mean HbA1c"]
    for col in ["Diabetes %", "CKD 3+%", "High LDL %"]:
        display[col] = (display[col] * 100).round(1).astype(str) + "%"
    display["Mean HbA1c"] = display["Mean HbA1c"].round(2)
    display = display.sort_values("Patients", ascending=False)
    st.dataframe(display, use_container_width=True, hide_index=True)

st.divider()

if selected_country != "All":
    st.subheader(f"Regional breakdown - {selected_country}")
    region_stats = build_region_stats(df_flags, df_geo, selected_country)

    if region_stats.empty:
        st.info("No regional data available.")
    else:
        rc1, rc2 = st.columns(2)

        with rc1:
            bar = (
                alt.Chart(region_stats)
                .mark_bar()
                .encode(
                    x=alt.X("pct_diabetes:Q", title="Diabetes %", axis=alt.Axis(format=".0%")),
                    y=alt.Y("state_region:N", sort="-x", title=None),
                    color=alt.value("#e07b39"),
                    tooltip=[
                        alt.Tooltip("state_region:N", title="Region"),
                        alt.Tooltip("pct_diabetes:Q", title="Diabetes %", format=".1%"),
                        alt.Tooltip("n_patients:Q", title="Patients"),
                    ],
                )
                .properties(title="Diabetes proxy by region", height=280)
            )
            st.altair_chart(bar, use_container_width=True)

        with rc2:
            bar2 = (
                alt.Chart(region_stats)
                .mark_bar()
                .encode(
                    x=alt.X("mean_ldl:Q", title="Mean LDL (mg/dL)"),
                    y=alt.Y("state_region:N", sort="-x", title=None),
                    color=alt.value("#4A90D9"),
                    tooltip=[
                        alt.Tooltip("state_region:N", title="Region"),
                        alt.Tooltip("mean_ldl:Q", title="Mean LDL", format=".0f"),
                        alt.Tooltip("n_patients:Q", title="Patients"),
                    ],
                )
                .properties(title="Mean LDL by region", height=280)
            )
            st.altair_chart(bar2, use_container_width=True)

        st.dataframe(
            region_stats.rename(columns={
                "state_region": "Region",
                "n_patients": "Patients",
                "pct_diabetes": "Diabetes %",
                "pct_ckd3": "CKD 3+ %",
                "pct_ldl_high": "High LDL %",
                "mean_hba1c": "Mean HbA1c",
                "mean_ldl": "Mean LDL",
            }).assign(**{
                "Diabetes %": lambda d: (d["Diabetes %"] * 100).round(1).astype(str) + "%",
                "CKD 3+ %": lambda d: (d["CKD 3+ %"] * 100).round(1).astype(str) + "%",
                "High LDL %": lambda d: (d["High LDL %"] * 100).round(1).astype(str) + "%",
            }),
            use_container_width=True,
            hide_index=True,
        )
