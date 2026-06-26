import altair as alt
import pandas as pd

BIOMARKER_LABELS = {
    "hba1c": "HbA1c (%)",
    "fasting_glucose": "Fasting Glucose (mg/dL)",
    "ldl": "LDL Cholesterol (mg/dL)",
    "hdl": "HDL Cholesterol (mg/dL)",
    "total_cholesterol": "Total Cholesterol (mg/dL)",
    "triglycerides": "Triglycerides (mg/dL)",
    "egfr": "eGFR (mL/min/1.73m²)",
    "creatinine": "Creatinine (mg/dL)",
    "tsh": "TSH (mIU/L)",
    "vitamin_d": "Vitamin D (ng/mL)",
    "b12": "Vitamin B12 (pg/mL)",
    "ferritin": "Ferritin (ng/mL)",
    "hemoglobin": "Hemoglobin (g/dL)",
    "hscrp": "hsCRP (mg/L)",
    "alt": "ALT (U/L)",
}

THRESHOLDS = {
    "hba1c": [
        {"value": 5.7, "color": "orange"},
        {"value": 6.5, "color": "red"},
    ],
    "fasting_glucose": [
        {"value": 100, "color": "orange"},
        {"value": 126, "color": "red"},
    ],
    "ldl": [
        {"value": 130, "color": "orange"},
        {"value": 160, "color": "red"},
    ],
    "egfr": [
        {"value": 60, "color": "orange"},
        {"value": 30, "color": "red"},
    ],
    "vitamin_d": [
        {"value": 20, "color": "red"},
        {"value": 30, "color": "orange"},
    ],
    "hscrp": [
        {"value": 1.0, "color": "orange"},
        {"value": 3.0, "color": "red"},
    ],
    "tsh": [
        {"value": 0.4, "color": "orange"},
        {"value": 4.0, "color": "red"},
    ],
}

STRATIFY_OPTIONS = ["none", "sex", "stakeholder", "country", "state_region"]

CV_STRATIFY_OPTIONS = [
    "none",
    "sex",
    "stakeholder",
    "cv_risk_category",
    "aip_category",
    "tg_hdl_category",
    "non_hdl_status",
    "ldl_status",
    "glycemic_status",
    "ckd_stage",
    "hscrp_category",
    "statin_eligible",
]


def _threshold_layers(biomarker):
    layers = []
    for t in THRESHOLDS.get(biomarker, []):
        rule = (
            alt.Chart(pd.DataFrame({"v": [t["value"]]}))
            .mark_rule(color=t["color"], strokeDash=[4, 4], size=1.5)
            .encode(x="v:Q")
        )
        layers.append(rule)
    return layers


def build_histogram(df, config):
    biomarker = config["biomarker"]
    stratify = config.get("stratify_by", "none")
    label = BIOMARKER_LABELS.get(biomarker, biomarker)

    strat_valid = stratify != "none" and stratify in df.columns
    cols = [biomarker] + ([stratify] if strat_valid else [])
    df_clean = df[cols].dropna()

    color_enc = (
        alt.Color(f"{stratify}:N", legend=alt.Legend(title=stratify))
        if strat_valid
        else alt.value("#4A90D9")
    )

    base = (
        alt.Chart(df_clean)
        .mark_bar(opacity=0.7)
        .encode(
            x=alt.X(f"{biomarker}:Q", bin=alt.Bin(maxbins=40), title=label),
            y=alt.Y("count()", title="Count"),
            color=color_enc,
            tooltip=[
                alt.Tooltip(f"{biomarker}:Q", title=label, bin=True),
                alt.Tooltip("count()", title="Count"),
            ],
        )
    )

    return alt.layer(base, *_threshold_layers(biomarker)).properties(height=270)


def build_line(df, config):
    biomarker = config["biomarker"]
    stratify = config.get("stratify_by", "none")
    label = BIOMARKER_LABELS.get(biomarker, biomarker)

    if "collection_date" not in df.columns:
        raise ValueError("Time Series requires collection_date column.")
    strat_cols = [stratify] if (stratify != "none" and stratify in df.columns) else []
    cols = ["collection_date", biomarker] + strat_cols
    df_clean = df[cols].dropna().copy()
    df_clean["month"] = (
        pd.to_datetime(df_clean["collection_date"])
        .dt.to_period("M")
        .dt.to_timestamp()
    )

    group_cols = ["month"] + (strat_cols)
    agg = df_clean.groupby(group_cols)[biomarker].mean().reset_index()
    agg.columns = group_cols + ["mean_value"]

    color_enc = (
        alt.Color(f"{stratify}:N") if strat_cols else alt.value("#4A90D9")
    )

    chart = (
        alt.Chart(agg)
        .mark_line(point=True)
        .encode(
            x=alt.X("month:T", title="Month"),
            y=alt.Y("mean_value:Q", title=f"Mean {label}"),
            color=color_enc,
            tooltip=(
                ["month:T", alt.Tooltip("mean_value:Q", format=".2f")]
                + ([f"{stratify}:N"] if strat_cols else [])
            ),
        )
    )

    return chart.properties(height=270)


def build_bar(df, config):
    biomarker = config["biomarker"]
    stratify = config.get("stratify_by", "none")
    label = BIOMARKER_LABELS.get(biomarker, biomarker)

    group_col = stratify if stratify != "none" else "sex"
    if group_col not in df.columns:
        raise ValueError(f"Column '{group_col}' not in data.")
    age_cols = ["age"] if "age" in df.columns else []
    df_clean = df[[biomarker, group_col] + age_cols].dropna(subset=[biomarker]).copy()

    if stratify == "none" and "age" in df_clean.columns:
        df_clean["age_band"] = pd.cut(
            df_clean["age"],
            bins=[17, 30, 45, 60, 75, 90],
            labels=["18-30", "31-45", "46-60", "61-75", "76+"],
        )
        agg = (
            df_clean.groupby("age_band", observed=True)[biomarker]
            .mean()
            .reset_index()
        )
        agg.columns = ["group", "mean_value"]
        x_title = "Age Band"
    elif stratify == "none":
        agg = pd.DataFrame({"group": ["All"], "mean_value": [df_clean[biomarker].mean()]})
        x_title = "Group"
    else:
        agg = df_clean.groupby(group_col)[biomarker].mean().reset_index()
        agg.columns = ["group", "mean_value"]
        x_title = group_col.replace("_", " ").title()

    chart = (
        alt.Chart(agg)
        .mark_bar()
        .encode(
            x=alt.X("group:N", title=x_title),
            y=alt.Y("mean_value:Q", title=f"Mean {label}"),
            color=alt.Color("group:N", legend=None),
            tooltip=[
                alt.Tooltip("group:N", title=x_title),
                alt.Tooltip("mean_value:Q", title=f"Mean {label}", format=".1f"),
            ],
        )
    )

    return chart.properties(height=270)


def build_box(df, config):
    biomarker = config["biomarker"]
    stratify = config.get("stratify_by", "sex")
    label = BIOMARKER_LABELS.get(biomarker, biomarker)
    group_col = stratify if (stratify != "none" and stratify in df.columns) else "sex"
    if group_col not in df.columns:
        group_col = df.columns[0]

    df_clean = df[[biomarker, group_col]].dropna()

    chart = (
        alt.Chart(df_clean)
        .mark_boxplot(extent="min-max", size=40)
        .encode(
            x=alt.X(f"{group_col}:N", title=group_col.replace("_", " ").title()),
            y=alt.Y(f"{biomarker}:Q", title=label),
            color=alt.Color(f"{group_col}:N", legend=None),
        )
    )

    return chart.properties(height=270)


CHART_BUILDERS = {
    "Histogram": build_histogram,
    "Time Series": build_line,
    "Bar": build_bar,
    "Box Plot": build_box,
}


def render_panel(config, df):
    chart_type = config.get("chart_type", "Histogram")
    builder = CHART_BUILDERS.get(chart_type, build_histogram)
    return builder(df, config)
