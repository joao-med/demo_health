import streamlit as st
import pandas as pd


def render_sidebar_filters(df, show_stakeholder=True):
    st.sidebar.header("Filters")

    filtered = df.copy()

    if show_stakeholder:
        stakeholder_options = ["All"] + sorted(
            df["stakeholder"].dropna().unique().tolist()
        )
        selected_stakeholder = st.sidebar.selectbox(
            "Stakeholder", stakeholder_options, key="filter_stakeholder"
        )
        if selected_stakeholder != "All":
            filtered = filtered[filtered["stakeholder"] == selected_stakeholder]

    sex_options = ["All", "M", "F"]
    selected_sex = st.sidebar.selectbox("Sex", sex_options, key="filter_sex")
    if selected_sex != "All":
        filtered = filtered[filtered["sex"] == selected_sex]

    age_min = int(df["age"].min())
    age_max = int(df["age"].max())
    age_range = st.sidebar.slider(
        "Age range", age_min, age_max, (age_min, age_max), key="filter_age"
    )
    filtered = filtered[
        (filtered["age"] >= age_range[0]) & (filtered["age"] <= age_range[1])
    ]

    date_min = pd.to_datetime(df["collection_date"].min()).date()
    date_max = pd.to_datetime(df["collection_date"].max()).date()
    col1, col2 = st.sidebar.columns(2)
    with col1:
        date_start = st.date_input("From", date_min, key="filter_date_start")
    with col2:
        date_end = st.date_input("To", date_max, key="filter_date_end")

    filtered = filtered[
        (pd.to_datetime(filtered["collection_date"]).dt.date >= date_start)
        & (pd.to_datetime(filtered["collection_date"]).dt.date <= date_end)
    ]

    if "country" in df.columns:
        country_options = ["All"] + sorted(df["country"].dropna().unique().tolist())
        selected_country = st.sidebar.selectbox(
            "Country", country_options, key="filter_country"
        )
        if selected_country != "All":
            filtered = filtered[filtered["country"] == selected_country]

        if "state_region" in df.columns and selected_country != "All":
            region_options = ["All"] + sorted(
                df[df["country"] == selected_country]["state_region"].dropna().unique().tolist()
            )
            selected_region = st.sidebar.selectbox(
                "Region", region_options, key="filter_region"
            )
            if selected_region != "All":
                filtered = filtered[filtered["state_region"] == selected_region]

    st.sidebar.caption(f"{len(filtered):,} draws | {filtered['patient_id'].nunique():,} patients")

    return filtered
