"""
Two-agent layer:
  DataFetcherAgent  — runs DuckDB queries, validates results
  AnalystAgent      — generates plain-language clinical narrative

If ANTHROPIC_API_KEY is set, both agents use Claude Haiku.
Otherwise they fall back to deterministic template-based outputs.
"""

import os
import duckdb
import pandas as pd

DB_PATH = "analytics.duckdb"

QUERY_TEMPLATES = {
    "Glycemic status breakdown": """
        SELECT glycemic_status, COUNT(*) AS n,
            ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 1) AS pct
        FROM patient_flags
        {where}
        GROUP BY glycemic_status
        ORDER BY n DESC
    """,
    "CKD stage distribution": """
        SELECT ckd_stage, COUNT(*) AS n,
            ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 1) AS pct
        FROM patient_flags
        {where}
        GROUP BY ckd_stage
        ORDER BY ckd_stage
    """,
    "LDL status breakdown": """
        SELECT ldl_status, COUNT(*) AS n,
            ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 1) AS pct
        FROM patient_flags
        {where}
        GROUP BY ldl_status
        ORDER BY n DESC
    """,
    "CV risk category distribution": """
        SELECT cv_risk_category, COUNT(*) AS n,
            ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 1) AS pct
        FROM cv_risk_flags
        {where}
        GROUP BY cv_risk_category
        ORDER BY n DESC
    """,
    "Top biomarker means by sex": """
        SELECT sex,
            ROUND(AVG(hba1c), 2) AS mean_hba1c,
            ROUND(AVG(ldl), 1) AS mean_ldl,
            ROUND(AVG(hdl), 1) AS mean_hdl,
            ROUND(AVG(egfr), 1) AS mean_egfr,
            ROUND(AVG(vitamin_d), 1) AS mean_vitd
        FROM patient_flags
        {where}
        GROUP BY sex
    """,
    "Comorbidity burden summary": """
        SELECT comorbidity_count AS conditions,
            COUNT(*) AS n_patients,
            ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 1) AS pct
        FROM patient_flags
        {where}
        GROUP BY comorbidity_count
        ORDER BY comorbidity_count
    """,
}


class DataFetcherAgent:
    def __init__(self, stakeholder_id=None):
        self.stakeholder_id = stakeholder_id
        self._where = (
            f"WHERE stakeholder = '{stakeholder_id}'"
            if stakeholder_id else ""
        )

    def run(self, query_name: str) -> pd.DataFrame:
        template = QUERY_TEMPLATES.get(query_name)
        if template is None:
            raise ValueError(f"Unknown query: {query_name}")
        sql = template.format(where=self._where)
        con = duckdb.connect(DB_PATH, read_only=True)
        df = con.execute(sql).df()
        con.close()
        if df.empty:
            raise ValueError("Query returned no results.")
        return df

    def run_llm(self, natural_language: str) -> pd.DataFrame:
        """LLM-powered path: generate SQL from natural language via Claude Haiku."""
        api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set.")

        import anthropic

        schema = """
Tables:
- lab_results(patient_id, age, sex, stakeholder, country, state_region, collection_date,
  hba1c, fasting_glucose, total_cholesterol, hdl, triglycerides, ldl, creatinine, egfr,
  tsh, vitamin_d, b12, ferritin, hemoglobin, hscrp, alt)
- patient_flags(patient_id, age, sex, stakeholder, glycemic_status, ckd_stage, ldl_status,
  vitd_status, anemia_status, comorbidity_count, hba1c, ldl, hdl, egfr, vitamin_d, hemoglobin, hscrp)
- cv_risk_flags(patient_id, age, sex, stakeholder, cv_risk_category, aip_category,
  tg_hdl_category, non_hdl_status, statin_eligible, ldl, hdl, triglycerides, aip, tc_hdl_ratio)
"""
        where_clause = (
            f"Add WHERE stakeholder = '{self.stakeholder_id}' to any table query."
            if self.stakeholder_id else ""
        )

        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            messages=[{
                "role": "user",
                "content": (
                    f"You are a DuckDB SQL expert. Given this schema:\n{schema}\n"
                    f"{where_clause}\n"
                    f"Write a single valid DuckDB SQL SELECT query (no explanation) to answer:\n"
                    f"{natural_language}\n"
                    f"Return ONLY the SQL."
                )
            }]
        )
        sql = message.content[0].text.strip().strip("```sql").strip("```").strip()
        con = duckdb.connect(DB_PATH, read_only=True)
        df = con.execute(sql).df()
        con.close()
        return df


class AnalystAgent:
    def __init__(self, stakeholder_id=None):
        self.stakeholder_id = stakeholder_id
        self._scope = stakeholder_id or "all stakeholders"

    def analyze(self, query_name: str, df: pd.DataFrame) -> str:
        api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        if api_key:
            return self._llm_analyze(query_name, df, api_key)
        return self._template_analyze(query_name, df)

    def _template_analyze(self, query_name: str, df: pd.DataFrame) -> str:
        lines = [f"**Analysis: {query_name}** (scope: {self._scope})\n"]

        if "glycemic_status" in df.columns:
            for _, row in df.iterrows():
                lines.append(f"- {row['glycemic_status']}: {row['n']:,} patients ({row['pct']}%)")
            diabetes_pct = df[df["glycemic_status"] == "Diabetes"]["pct"].sum()
            pre_pct = df[df["glycemic_status"] == "Pre-diabetes"]["pct"].sum()
            lines.append(
                f"\n{diabetes_pct}% of patients meet the proxy criterion for diabetes "
                f"and {pre_pct}% are pre-diabetic. "
                f"Combined glycemic burden: {diabetes_pct + pre_pct:.1f}%."
            )

        elif "cv_risk_category" in df.columns:
            high_n = df[df["cv_risk_category"].str.startswith("High", na=False)]["n"].sum()
            very_high_n = df[df["cv_risk_category"].str.startswith("Very High", na=False)]["n"].sum()
            total = df["n"].sum()
            lines.append(
                f"{(high_n + very_high_n) / total * 100:.1f}% of patients fall into "
                f"high or very high CV risk categories — these patients are candidates "
                f"for statin therapy and lipid management intervention."
            )

        elif "comorbidity_count" in df.columns:
            multi = df[df["conditions"] >= 2]["n_patients"].sum()
            total = df["n_patients"].sum()
            lines.append(
                f"{multi / total * 100:.1f}% of patients carry 2 or more concurrent "
                f"risk conditions. This high comorbidity burden signals compounding clinical "
                f"risk and higher expected healthcare utilization."
            )

        else:
            lines.append(df.to_string(index=False))

        lines.append("\n_AI-generated summary — verify before sharing._")
        return "\n".join(lines)

    def _llm_analyze(self, query_name: str, df: pd.DataFrame, api_key: str) -> str:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        data_str = df.to_string(index=False)
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            messages=[{
                "role": "user",
                "content": (
                    f"You are a clinical data analyst. Scope: {self._scope}.\n"
                    f"Query: {query_name}\n"
                    f"Data:\n{data_str}\n\n"
                    f"Write a concise (3-5 sentence) clinical interpretation for a health plan manager. "
                    f"Highlight what is actionable. No bullet points. Plain prose."
                )
            }]
        )
        text = message.content[0].text.strip()
        return text + "\n\n_AI-generated summary — verify before sharing._"
 