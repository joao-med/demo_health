import streamlit as st
import duckdb
import pandas as pd
import numpy as np
import altair as alt

DB_PATH = "openhealth.duckdb"

SCREENING_LABELS = {
    "mammography": "Mammography",
    "pap_smear": "Pap Smear",
    "colonoscopy": "Colonoscopy",
    "fobt": "Fecal Occult Blood Test",
    "psa": "PSA (Prostate)",
}

SCREENING_DETAILS = {
    "mammography": "Women 50-74 yrs - every 2 years (INCA / USPSTF B)",
    "pap_smear": "Women 25-65 yrs - every 3 years (FEBRASGO / INCA)",
    "colonoscopy": "All 45-75 yrs - every 10 years (SBCE / USPSTF A)",
    "fobt": "All 45-75 yrs - annually (USPSTF A, stool DNA/gFOBT)",
    "psa": "Men 50-69 yrs - every 2 years (SBU, shared decision)",
}

STATUS_COLORS = {
    "Up to Date": "#2ca02c",
    "Overdue": "#e87a1e",
    "No Data": "#aaaaaa",
}

STATUS_ORDER = ["Up to Date", "Overdue", "No Data"]


@st.cache_data
def load_compliance(_stakeholder_id):
    con = duckdb.connect(DB_PATH, read_only=True)
    where = f"WHERE stakeholder = '{_stakeholder_id}'" if _stakeholder_id else ""
    df = con.execute(f"SELECT * FROM screening_compliance {where}").df()
    con.close()
    return df


@st.cache_data
def load_patient_flags(_stakeholder_id):
    con = duckdb.connect(DB_PATH, read_only=True)
    where = f"WHERE stakeholder = '{_stakeholder_id}'" if _stakeholder_id else ""
    df = con.execute(f"SELECT patient_id, age, sex, stakeholder FROM patient_flags {where}").df()
    con.close()
    return df


def age_group(age):
    if age < 35:
        return "18-34"
    elif age < 50:
        return "35-49"
    elif age < 65:
        return "50-64"
    else:
        return "65+"


def run():
    st.title("Preventive Care Screening")
    st.caption("Coverage tracking across 5 evidence-based screening protocols")

    stakeholder_id = st.session_state.get("stakeholder_id")
    df = load_compliance(stakeholder_id)
    df_patients = load_patient_flags(stakeholder_id)

    if df.empty:
        st.warning("No screening compliance data available.")
        return

    # Sidebar filters
    with st.sidebar:
        st.subheader("Filters")

        screening_options = list(SCREENING_LABELS.keys())
        selected_screenings = st.multiselect(
            "Screening type",
            screening_options,
            default=screening_options,
            format_func=lambda x: SCREENING_LABELS[x],
        )

        sex_options = ["All", "F", "M"]
        sex_filter = st.selectbox("Sex", sex_options)

        age_groups = ["All", "18-34", "35-49", "50-64", "65+"]
        age_filter = st.selectbox("Age group", age_groups)

        if stakeholder_id is None:
            stakeholders = sorted(df["stakeholder"].unique().tolist())
            sh_filter = st.selectbox("Stakeholder", ["All"] + stakeholders)
        else:
            sh_filter = "All"

    df_f = df.copy()
    df_f["age_group"] = df_f["age"].apply(age_group)

    if selected_screenings:
        df_f = df_f[df_f["screening_type"].isin(selected_screenings)]
    if sex_filter != "All":
        df_f = df_f[df_f["sex"] == sex_filter]
    if age_filter != "All":
        df_f = df_f[df_f["age_group"] == age_filter]
    if sh_filter != "All":
        df_f = df_f[df_f["stakeholder"] == sh_filter]

    if df_f.empty:
        st.info("No patients match the selected filters.")
        return

    n_eligible = df_f["patient_id"].nunique()
    n_up_to_date = df_f[df_f["compliance_status"] == "Up to Date"]["patient_id"].nunique()
    n_overdue = df_f[df_f["compliance_status"] == "Overdue"]["patient_id"].nunique()
    n_no_data = df_f[df_f["compliance_status"] == "No Data"]["patient_id"].nunique()
    total_slots = len(df_f)
    pct_covered = (df_f["compliance_status"] == "Up to Date").sum() / max(total_slots, 1)
    pct_overdue = (df_f["compliance_status"] == "Overdue").sum() / max(total_slots, 1)

    st.divider()

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Eligible patients", f"{n_eligible:,}")
    k2.metric("Screening slots", f"{total_slots:,}")
    k3.metric("Up to Date", f"{pct_covered:.1%}", help="% of screening slots where patient is current")
    k4.metric("Overdue", f"{pct_overdue:.1%}", help="% of screening slots past due interval")
    k5.metric("No Record", f"{(1 - pct_covered - pct_overdue):.1%}", help="% with no screening record")

    st.divider()

    # Compliance by screening type
    st.subheader("Compliance by Screening Type")

    type_counts = (
        df_f.groupby(["screening_type", "compliance_status"])
        .size()
        .reset_index(name="count")
    )
    type_counts["label"] = type_counts["screening_type"].map(SCREENING_LABELS)
    type_counts["total"] = type_counts.groupby("screening_type")["count"].transform("sum")
    type_counts["pct"] = type_counts["count"] / type_counts["total"]

    bar_chart = (
        alt.Chart(type_counts)
        .mark_bar()
        .encode(
            x=alt.X("pct:Q", axis=alt.Axis(format=".0%"), title="% of eligible patients"),
            y=alt.Y("label:N", title=None, sort=list(SCREENING_LABELS.values())),
            color=alt.Color(
                "compliance_status:N",
                scale=alt.Scale(
                    domain=STATUS_ORDER,
                    range=[STATUS_COLORS[s] for s in STATUS_ORDER],
                ),
                legend=alt.Legend(title="Status", orient="bottom"),
            ),
            order=alt.Order("compliance_status:N", sort="descending"),
            tooltip=[
                alt.Tooltip("label:N", title="Screening"),
                alt.Tooltip("compliance_status:N", title="Status"),
                alt.Tooltip("count:Q", title="Patients"),
                alt.Tooltip("pct:Q", title="Share", format=".1%"),
            ],
        )
        .properties(height=260)
    )
    st.altair_chart(bar_chart, use_container_width=True)

    # Coverage detail table per screening
    st.subheader("Coverage Summary")
    summary_rows = []
    for s_type in (selected_screenings or list(SCREENING_LABELS.keys())):
        sub = df_f[df_f["screening_type"] == s_type]
        if sub.empty:
            continue
        n = len(sub)
        n_ok = (sub["compliance_status"] == "Up to Date").sum()
        n_ov = (sub["compliance_status"] == "Overdue").sum()
        n_nd = (sub["compliance_status"] == "No Data").sum()
        median_days = sub["days_since_last"].dropna().median()
        summary_rows.append({
            "Screening": SCREENING_LABELS[s_type],
            "Protocol": SCREENING_DETAILS[s_type],
            "Eligible": n,
            "Up to Date": n_ok,
            "Overdue": n_ov,
            "No Record": n_nd,
            "Coverage %": f"{n_ok/n:.1%}",
            "Median days since last": int(median_days) if not np.isnan(median_days) else "N/A",
        })

    st.dataframe(pd.DataFrame(summary_rows), hide_index=True, use_container_width=True)

    st.divider()

    # Overdue trend: overdue rate by age group and sex
    left_col, right_col = st.columns(2)

    with left_col:
        st.subheader("Overdue Rate by Age Group")
        df_f["age_group"] = df_f["age"].apply(age_group)
        age_compliance = (
            df_f.groupby(["age_group", "compliance_status"])
            .size()
            .reset_index(name="count")
        )
        age_compliance["total"] = age_compliance.groupby("age_group")["count"].transform("sum")
        age_compliance["pct"] = age_compliance["count"] / age_compliance["total"]

        age_bar = (
            alt.Chart(age_compliance)
            .mark_bar()
            .encode(
                x=alt.X("age_group:N", title="Age group", sort=["18-34", "35-49", "50-64", "65+"]),
                y=alt.Y("pct:Q", axis=alt.Axis(format=".0%"), title="% of slots"),
                color=alt.Color(
                    "compliance_status:N",
                    scale=alt.Scale(
                        domain=STATUS_ORDER,
                        range=[STATUS_COLORS[s] for s in STATUS_ORDER],
                    ),
                    legend=None,
                ),
                order=alt.Order("compliance_status:N", sort="descending"),
                tooltip=[
                    alt.Tooltip("age_group:N", title="Age group"),
                    alt.Tooltip("compliance_status:N", title="Status"),
                    alt.Tooltip("pct:Q", format=".1%", title="Share"),
                    alt.Tooltip("count:Q", title="Patients"),
                ],
            )
            .properties(height=260)
        )
        st.altair_chart(age_bar, use_container_width=True)

    with right_col:
        st.subheader("Coverage Heatmap by Screening x Stakeholder")
        if stakeholder_id is None:
            heat_df = (
                df_f.groupby(["screening_type", "stakeholder"])
                .apply(lambda g: (g["compliance_status"] == "Up to Date").mean())
                .reset_index(name="coverage")
            )
            heat_df["label"] = heat_df["screening_type"].map(SCREENING_LABELS)
            heat = (
                alt.Chart(heat_df)
                .mark_rect()
                .encode(
                    x=alt.X("stakeholder:N", title=None),
                    y=alt.Y("label:N", title=None),
                    color=alt.Color(
                        "coverage:Q",
                        scale=alt.Scale(scheme="greens", domain=[0, 1]),
                        legend=alt.Legend(title="Coverage", format=".0%"),
                    ),
                    tooltip=[
                        alt.Tooltip("label:N", title="Screening"),
                        alt.Tooltip("stakeholder:N"),
                        alt.Tooltip("coverage:Q", format=".1%", title="Coverage"),
                    ],
                )
                .properties(height=260)
            )
            text = heat.mark_text(fontSize=11).encode(
                text=alt.Text("coverage:Q", format=".0%"),
                color=alt.value("black"),
            )
            st.altair_chart(heat + text, use_container_width=True)
        else:
            st.info("Stakeholder heatmap available in admin view.")
            sex_comp = (
                df_f.groupby(["sex", "compliance_status"])
                .size()
                .reset_index(name="count")
            )
            sex_comp["total"] = sex_comp.groupby("sex")["count"].transform("sum")
            sex_comp["pct"] = sex_comp["count"] / sex_comp["total"]
            sex_bar = (
                alt.Chart(sex_comp)
                .mark_bar()
                .encode(
                    x=alt.X("sex:N", title="Sex"),
                    y=alt.Y("pct:Q", axis=alt.Axis(format=".0%"), title="% of slots"),
                    color=alt.Color(
                        "compliance_status:N",
                        scale=alt.Scale(
                            domain=STATUS_ORDER,
                            range=[STATUS_COLORS[s] for s in STATUS_ORDER],
                        ),
                        legend=None,
                    ),
                    order=alt.Order("compliance_status:N", sort="descending"),
                    tooltip=["sex:N", "compliance_status:N", alt.Tooltip("pct:Q", format=".1%")],
                )
                .properties(height=260)
            )
            st.altair_chart(sex_bar, use_container_width=True)

    st.divider()

    # Patient-level table
    with st.expander("Patient-level detail"):
        st.caption("One row per patient per screening type. Filter using sidebar controls.")
        pivot = (
            df_f.pivot_table(
                index=["patient_id", "age", "sex", "stakeholder"],
                columns="screening_type",
                values="compliance_status",
                aggfunc="first",
            )
            .reset_index()
        )
        pivot.columns.name = None
        for col in list(SCREENING_LABELS.keys()):
            if col not in pivot.columns:
                pivot[col] = "N/A"
        pivot = pivot.rename(columns=SCREENING_LABELS)
        pivot = pivot.sort_values("age", ascending=False)
        st.dataframe(pivot, hide_index=True, use_container_width=True)


run()
