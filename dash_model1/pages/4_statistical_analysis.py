import streamlit as st
import duckdb
import pandas as pd
import numpy as np
import altair as alt
from scipy import stats

DB_PATH = "analytics.duckdb"

BIOMARKER_LABELS = {
    "hba1c": "HbA1c (%)",
    "fasting_glucose": "Fasting Glucose (mg/dL)",
    "total_cholesterol": "Total Cholesterol (mg/dL)",
    "hdl": "HDL (mg/dL)",
    "ldl": "LDL (mg/dL)",
    "triglycerides": "Triglycerides (mg/dL)",
    "egfr": "eGFR (mL/min/1.73m2)",
    "creatinine": "Creatinine (mg/dL)",
    "vitamin_d": "Vitamin D (ng/mL)",
    "hscrp": "hsCRP (mg/L)",
    "tsh": "TSH (uIU/mL)",
    "b12": "B12 (pg/mL)",
    "ferritin": "Ferritin (ng/mL)",
    "hemoglobin": "Hemoglobin (g/dL)",
    "alt": "ALT (U/L)",
}

GROUPING_OPTIONS = {
    "Sex": "sex",
    "Glycemic Status": "glycemic_status",
    "CKD Stage": "ckd_stage",
    "LDL Status": "ldl_status",
    "Vitamin D Status": "vitd_status",
    "CV Risk Category": "cv_risk_category",
    "AIP Category": "aip_category",
    "TG/HDL Category": "tg_hdl_category",
    "Statin Eligible": "statin_eligible",
    "Stakeholder": "stakeholder",
}


@st.cache_data
def load_raw(_stakeholder_id):
    con = duckdb.connect(DB_PATH, read_only=True)
    where = f"WHERE lr.stakeholder = '{_stakeholder_id}'" if _stakeholder_id else ""
    df = con.execute(f"""
        SELECT
            lr.patient_id, lr.age, lr.sex, lr.stakeholder, lr.collection_date,
            lr.hba1c, lr.fasting_glucose, lr.total_cholesterol,
            lr.hdl, lr.ldl, lr.triglycerides, lr.creatinine, lr.egfr,
            lr.tsh, lr.vitamin_d, lr.b12, lr.ferritin,
            lr.hemoglobin, lr.hscrp, lr.alt,
            pf.glycemic_status, pf.ckd_stage, pf.ldl_status,
            pf.vitd_status, pf.anemia_status, pf.comorbidity_count,
            cv.cv_risk_category, cv.aip_category, cv.tg_hdl_category,
            cv.statin_eligible
        FROM lab_results lr
        LEFT JOIN patient_flags pf ON lr.patient_id = pf.patient_id
        LEFT JOIN cv_risk_flags cv ON lr.patient_id = cv.patient_id
        {where}
    """).df()
    con.close()
    return df


def rank_biserial(a, b):
    stat, _ = stats.mannwhitneyu(a, b, alternative="two-sided")
    n = len(a) * len(b)
    return 1 - (2 * stat) / n if n > 0 else 0.0


def eta_squared(groups):
    all_vals = np.concatenate(groups)
    grand_mean = np.mean(all_vals)
    ss_between = sum(len(g) * (np.mean(g) - grand_mean) ** 2 for g in groups)
    ss_total = np.sum((all_vals - grand_mean) ** 2)
    return ss_between / ss_total if ss_total > 0 else 0.0


def significance_label(p):
    if p < 0.001:
        return "p < 0.001 ***"
    elif p < 0.01:
        return "p < 0.01 **"
    elif p < 0.05:
        return "p < 0.05 *"
    else:
        return f"p = {p:.3f} (ns)"


def effect_label(val, kind="r"):
    val = abs(val)
    if kind == "r":
        if val < 0.1: return "negligible"
        elif val < 0.3: return "small"
        elif val < 0.5: return "medium"
        else: return "large"
    else:
        if val < 0.01: return "negligible"
        elif val < 0.06: return "small"
        elif val < 0.14: return "medium"
        else: return "large"


def run():
    st.title("Statistical Analysis")
    st.caption("Non-parametric group comparisons with effect sizes (Mann-Whitney U / Kruskal-Wallis)")

    stakeholder_id = st.session_state.get("stakeholder_id")
    df = load_raw(stakeholder_id)

    col_g, col_b = st.columns([1, 1])
    with col_g:
        group_label = st.selectbox("Grouping variable", list(GROUPING_OPTIONS.keys()))
    with col_b:
        biomarker = st.selectbox(
            "Biomarker",
            list(BIOMARKER_LABELS.keys()),
            format_func=lambda x: BIOMARKER_LABELS[x],
        )

    group_col = GROUPING_OPTIONS[group_label]

    if group_col not in df.columns:
        st.warning(f"Column '{group_col}' not available in data.")
        return

    available_groups = sorted(df[group_col].dropna().astype(str).unique().tolist())
    if len(available_groups) < 2:
        st.warning("Need at least 2 groups to compare.")
        return

    selected_groups = st.multiselect(
        "Select groups to compare",
        available_groups,
        default=available_groups[:min(4, len(available_groups))],
    )

    if len(selected_groups) < 2:
        st.info("Select at least 2 groups to run the test.")
        return

    df[group_col] = df[group_col].astype(str)
    df_filtered = df[df[group_col].isin(selected_groups)].dropna(subset=[biomarker])

    group_data = {
        g: df_filtered[df_filtered[group_col] == g][biomarker].values
        for g in selected_groups
    }
    group_data = {g: v for g, v in group_data.items() if len(v) >= 5}

    if len(group_data) < 2:
        st.warning("Not enough data in selected groups (need >= 5 observations each).")
        return

    groups_list = list(group_data.values())
    group_names = list(group_data.keys())

    if len(group_data) == 2:
        a, b = groups_list
        stat, p_value = stats.mannwhitneyu(a, b, alternative="two-sided")
        test_name = "Mann-Whitney U"
        effect_val = rank_biserial(a, b)
        effect_kind = "r"
        effect_name = "Rank-biserial r"
    else:
        stat, p_value = stats.kruskal(*groups_list)
        test_name = "Kruskal-Wallis H"
        effect_val = eta_squared(groups_list)
        effect_kind = "eta2"
        effect_name = "Eta-squared"

    st.divider()

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Test", test_name)
    m2.metric("Statistic", f"{stat:.3f}")
    m3.metric("Significance", significance_label(p_value))
    m4.metric(effect_name, f"{effect_val:.3f} ({effect_label(effect_val, effect_kind)})")

    st.divider()

    chart_col, stats_col = st.columns([3, 1])

    with chart_col:
        st.subheader(f"{BIOMARKER_LABELS[biomarker]} by {group_label}")

        plot_df = df_filtered[df_filtered[group_col].isin(group_names)].copy()

        box = (
            alt.Chart(plot_df)
            .mark_boxplot(extent="min-max", outliers=True, size=40)
            .encode(
                x=alt.X(f"{group_col}:N", title=group_label, sort=group_names),
                y=alt.Y(f"{biomarker}:Q", title=BIOMARKER_LABELS[biomarker]),
                color=alt.Color(f"{group_col}:N", legend=None),
                tooltip=[
                    alt.Tooltip(f"{group_col}:N", title="Group"),
                    alt.Tooltip(f"{biomarker}:Q", title="Value", format=".2f"),
                ],
            )
            .properties(height=380)
        )

        sig_text = significance_label(p_value)
        annotation_df = pd.DataFrame({
            "x": [group_names[0]],
            "y": [plot_df[biomarker].quantile(0.97)],
            "text": [sig_text],
        })
        annotation = (
            alt.Chart(annotation_df)
            .mark_text(align="left", baseline="top", fontSize=13, color="#555")
            .encode(
                x=alt.X("x:N", sort=group_names),
                y=alt.Y("y:Q"),
                text="text:N",
            )
        )
        st.altair_chart(box + annotation, use_container_width=True)

    with stats_col:
        st.subheader("Group summary")
        summary_rows = []
        for g in group_names:
            vals = group_data[g]
            summary_rows.append({
                "Group": str(g),
                "N": len(vals),
                "Median": round(np.median(vals), 2),
                "IQR": f"{np.percentile(vals, 25):.1f} - {np.percentile(vals, 75):.1f}",
                "Mean": round(np.mean(vals), 2),
            })
        st.dataframe(pd.DataFrame(summary_rows), hide_index=True, use_container_width=True)

        st.subheader("Pairwise (MW)")
        pw_rows = []
        for i in range(len(group_names)):
            for j in range(i + 1, len(group_names)):
                g1, g2 = group_names[i], group_names[j]
                a, b = group_data[g1], group_data[g2]
                if len(a) >= 5 and len(b) >= 5:
                    _, p = stats.mannwhitneyu(a, b, alternative="two-sided")
                    r = rank_biserial(a, b)
                    sig = "***" if p < 0.001 else ("**" if p < 0.01 else ("*" if p < 0.05 else "ns"))
                    pw_rows.append({"A": g1, "B": g2, "p": round(p, 4), "r": round(r, 3), "sig": sig})
        if pw_rows:
            st.dataframe(pd.DataFrame(pw_rows), hide_index=True, use_container_width=True)

    st.divider()

    with st.expander("Distribution overlap"):
        overlap_df = df_filtered[df_filtered[group_col].isin(group_names)].copy()
        hist = (
            alt.Chart(overlap_df)
            .mark_bar(opacity=0.45, binSpacing=0)
            .encode(
                x=alt.X(f"{biomarker}:Q", bin=alt.Bin(maxbins=40), title=BIOMARKER_LABELS[biomarker]),
                y=alt.Y("count():Q", stack=None, title="Count"),
                color=alt.Color(f"{group_col}:N", title=group_label),
                tooltip=[alt.Tooltip(f"{group_col}:N"), alt.Tooltip("count():Q", title="Count")],
            )
            .properties(height=260)
        )
        st.altair_chart(hist, use_container_width=True)


run()
 