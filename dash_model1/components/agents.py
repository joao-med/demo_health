"""
Two-agent layer:
  DataFetcherAgent  - runs DuckDB queries, validates results
  AnalystAgent      - generates plain-language clinical narrative

If ANTHROPIC_API_KEY is set, both agents use Claude Haiku.
Otherwise they fall back to deterministic template-based outputs.
"""

import os
import duckdb
import pandas as pd

DB_PATH = "analytics.duckdb"

QUERY_TEMPLATES = {
    "population_summary": """
        SELECT
            COUNT(DISTINCT patient_id) AS n_patients,
            ROUND(AVG(CASE WHEN glycemic_status = 'Diabetes' THEN 1.0 ELSE 0.0 END) * 100, 1) AS pct_diabetes,
            ROUND(AVG(CASE WHEN ckd_stage IN ('G3a','G3b','G4','G5') THEN 1.0 ELSE 0.0 END) * 100, 1) AS pct_ckd3,
            ROUND(AVG(CASE WHEN ldl_status IN ('High','Very High') THEN 1.0 ELSE 0.0 END) * 100, 1) AS pct_ldl_high
        FROM patient_flags
    """,
    "cv_risk_summary": """
        SELECT cv_risk_category, COUNT(*) AS n
        FROM cv_risk_flags
        GROUP BY cv_risk_category
        ORDER BY n DESC
    """,
}


class DataFetcherAgent:
    def __init__(self, stakeholder_id=None):
        self.stakeholder_id = stakeholder_id

    def run_query(self, query_name):
        sql = QUERY_TEMPLATES.get(query_name, "")
        if not sql:
            return None
        con = duckdb.connect(DB_PATH, read_only=True)
        df = con.execute(sql).df()
        con.close()
        return df


class AnalystAgent:
    def __init__(self, api_key=None):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")

    def summarize(self, df: pd.DataFrame, context: str = "") -> str:
        if self.api_key:
            try:
                import anthropic
                client = anthropic.Anthropic(api_key=self.api_key)
                msg = client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=300,
                    messages=[{
                        "role": "user",
                        "content": (
                            f"You are a clinical data analyst. Given this population health summary:\n\n"
                            f"{df.to_string()}\n\n{context}\n\n"
                            "Write 2-3 sentences of clinical interpretation for a health plan manager."
                        ),
                    }],
                )
                return msg.content[0].text
            except Exception:
                pass
        row = df.iloc[0] if len(df) > 0 else {}
        return (
            f"Population of {row.get('n_patients', '?')} patients. "
            f"Diabetes prevalence: {row.get('pct_diabetes', '?')}%. "
            f"CKD Stage 3+: {row.get('pct_ckd3', '?')}%. "
            f"High LDL: {row.get('pct_ldl_high', '?')}%."
        )
