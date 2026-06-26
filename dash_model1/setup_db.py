import duckdb
import os

DB_PATH = "openhealth.duckdb"


def main():
    con = duckdb.connect(DB_PATH)

    for tbl in ["screening_compliance", "screening_events", "cv_risk_flags", "patient_flags", "lab_results"]:
        con.execute(f"DROP TABLE IF EXISTS {tbl}")

    print("Loading lab_results from parquet...")
    con.execute("""
        CREATE TABLE lab_results AS
        SELECT * FROM read_parquet('data/patients_raw.parquet')
    """)

    print("Computing patient_flags...")
    con.execute("""
        CREATE TABLE patient_flags AS
        WITH latest AS (
            SELECT *,
                ROW_NUMBER() OVER (
                    PARTITION BY patient_id
                    ORDER BY collection_date DESC
                ) AS rn
            FROM lab_results
        ),
        base AS (SELECT * FROM latest WHERE rn = 1)
        SELECT
            patient_id,
            age,
            sex,
            stakeholder,
            collection_date AS latest_draw,
            hba1c,
            fasting_glucose,
            ldl,
            hdl,
            triglycerides,
            egfr,
            vitamin_d,
            b12,
            ferritin,
            hemoglobin,
            hscrp,

            CASE
                WHEN hba1c >= 6.5 OR fasting_glucose >= 126 THEN 'Diabetes'
                WHEN hba1c >= 5.7 OR fasting_glucose >= 100 THEN 'Pre-diabetes'
                WHEN hba1c IS NOT NULL OR fasting_glucose IS NOT NULL THEN 'Normal'
                ELSE NULL
            END AS glycemic_status,

            CASE
                WHEN egfr IS NULL THEN NULL
                WHEN egfr >= 90 THEN 'G1'
                WHEN egfr >= 60 THEN 'G2'
                WHEN egfr >= 45 THEN 'G3a'
                WHEN egfr >= 30 THEN 'G3b'
                WHEN egfr >= 15 THEN 'G4'
                ELSE 'G5'
            END AS ckd_stage,

            CASE
                WHEN ldl IS NULL THEN NULL
                WHEN ldl >= 190 THEN 'Very High'
                WHEN ldl >= 160 THEN 'High'
                WHEN ldl >= 130 THEN 'Borderline'
                WHEN ldl >= 100 THEN 'Near Optimal'
                ELSE 'Optimal'
            END AS ldl_status,

            CASE
                WHEN vitamin_d IS NULL THEN NULL
                WHEN vitamin_d < 20 THEN 'Deficient'
                WHEN vitamin_d < 30 THEN 'Insufficient'
                ELSE 'Sufficient'
            END AS vitd_status,

            CASE
                WHEN hemoglobin IS NULL THEN NULL
                WHEN sex = 'F' AND hemoglobin < 12.0 THEN 'Anemia'
                WHEN sex = 'M' AND hemoglobin < 13.5 THEN 'Anemia'
                ELSE 'Normal'
            END AS anemia_status,

            (
                CASE WHEN hba1c >= 6.5 OR fasting_glucose >= 126 THEN 1 ELSE 0 END
                + CASE WHEN ldl >= 160 THEN 1 ELSE 0 END
                + CASE WHEN egfr < 60 THEN 1 ELSE 0 END
                + CASE WHEN vitamin_d < 20 THEN 1 ELSE 0 END
                + CASE WHEN (sex = 'F' AND hemoglobin < 12.0)
                            OR (sex = 'M' AND hemoglobin < 13.5) THEN 1 ELSE 0 END
            )::INTEGER AS comorbidity_count

        FROM base
    """)

    print("Computing cv_risk_flags...")
    con.execute("""
        CREATE TABLE cv_risk_flags AS
        SELECT
            pf.patient_id,
            pf.age,
            pf.sex,
            pf.stakeholder,
            pf.latest_draw,
            pf.ldl,
            pf.hdl,
            tc.total_cholesterol,
            pf.triglycerides,
            pf.hscrp,
            pf.hba1c,
            pf.egfr,
            pf.glycemic_status,
            pf.ckd_stage,

            ROUND(tc.total_cholesterol - pf.hdl, 1) AS non_hdl,
            ROUND(tc.total_cholesterol / NULLIF(pf.hdl, 0), 2) AS tc_hdl_ratio,
            ROUND(pf.ldl / NULLIF(pf.hdl, 0), 2) AS ldl_hdl_ratio,
            ROUND(pf.triglycerides / NULLIF(pf.hdl, 0), 2) AS tg_hdl_ratio,
            ROUND(LOG10(NULLIF(pf.triglycerides, 0) / NULLIF(pf.hdl, 0)), 3) AS aip,

            CASE
                WHEN (tc.total_cholesterol - pf.hdl) IS NULL THEN NULL
                WHEN (tc.total_cholesterol - pf.hdl) >= 190 THEN 'Very High (>=190)'
                WHEN (tc.total_cholesterol - pf.hdl) >= 160 THEN 'High (160-189)'
                WHEN (tc.total_cholesterol - pf.hdl) >= 130 THEN 'Borderline (130-159)'
                ELSE 'Optimal (<130)'
            END AS non_hdl_status,

            CASE
                WHEN LOG10(NULLIF(pf.triglycerides, 0) / NULLIF(pf.hdl, 0)) IS NULL THEN NULL
                WHEN LOG10(NULLIF(pf.triglycerides, 0) / NULLIF(pf.hdl, 0)) > 0.21 THEN 'High Risk (>0.21)'
                WHEN LOG10(NULLIF(pf.triglycerides, 0) / NULLIF(pf.hdl, 0)) > 0.11 THEN 'Intermediate (0.11-0.21)'
                ELSE 'Low Risk (<=0.11)'
            END AS aip_category,

            CASE
                WHEN (pf.triglycerides / NULLIF(pf.hdl, 0)) IS NULL THEN NULL
                WHEN (pf.triglycerides / NULLIF(pf.hdl, 0)) >= 4.0 THEN 'High (>=4.0)'
                WHEN (pf.triglycerides / NULLIF(pf.hdl, 0)) >= 2.0 THEN 'Intermediate (2.0-3.9)'
                ELSE 'Low (<2.0)'
            END AS tg_hdl_category,

            CASE
                WHEN pf.ldl >= 190
                    THEN 'Very High - Severe Hypercholesterolemia'
                WHEN pf.glycemic_status = 'Diabetes' AND pf.age BETWEEN 40 AND 75 AND pf.ldl >= 70
                    THEN 'High - Diabetes + Dyslipidemia'
                WHEN pf.ckd_stage IN ('G3a', 'G3b', 'G4', 'G5') AND pf.ldl >= 100
                    THEN 'High - CKD + Dyslipidemia'
                WHEN pf.ldl >= 160 AND pf.age >= 40
                    THEN 'Intermediate-High'
                WHEN pf.ldl >= 130
                    THEN 'Borderline'
                ELSE 'Lower Risk'
            END AS cv_risk_category,

            CASE
                WHEN pf.ldl >= 190 THEN TRUE
                WHEN pf.glycemic_status = 'Diabetes' AND pf.age BETWEEN 40 AND 75 AND pf.ldl >= 70 THEN TRUE
                WHEN pf.ckd_stage IN ('G3a', 'G3b', 'G4', 'G5') AND pf.ldl >= 100 THEN TRUE
                ELSE FALSE
            END AS statin_eligible,

            CASE
                WHEN pf.hscrp IS NULL THEN NULL
                WHEN pf.hscrp >= 3.0 THEN 'High (>=3.0)'
                WHEN pf.hscrp >= 1.0 THEN 'Intermediate (1.0-2.9)'
                ELSE 'Low (<1.0)'
            END AS hscrp_category

        FROM patient_flags pf
        LEFT JOIN (
            SELECT patient_id, total_cholesterol
            FROM (
                SELECT patient_id, total_cholesterol,
                    ROW_NUMBER() OVER (PARTITION BY patient_id ORDER BY collection_date DESC) AS rn
                FROM lab_results
            ) t WHERE rn = 1
        ) tc ON pf.patient_id = tc.patient_id
    """)

    print("Loading screening_events...")
    con.execute("""
        CREATE TABLE screening_events AS
        SELECT * FROM read_parquet('data/screening_events.parquet')
    """)

    print("Computing screening_compliance...")
    con.execute("""
        CREATE TABLE screening_compliance AS
        WITH protocols AS (
            SELECT * FROM (VALUES
                ('mammography',  'F',   50, 74, 2),
                ('pap_smear',    'F',   25, 65, 3),
                ('colonoscopy',  NULL,  45, 75, 10),
                ('fobt',         NULL,  45, 75, 1),
                ('psa',          'M',   50, 69, 2)
            ) AS t(screening_type, required_sex, min_age, max_age, interval_years)
        ),
        eligible AS (
            SELECT
                pf.patient_id,
                pf.age,
                pf.sex,
                pf.stakeholder,
                p.screening_type,
                p.interval_years
            FROM patient_flags pf
            CROSS JOIN protocols p
            WHERE
                (p.required_sex IS NULL OR pf.sex = p.required_sex)
                AND pf.age BETWEEN p.min_age AND p.max_age
        ),
        last_event AS (
            SELECT
                patient_id,
                screening_type,
                MAX(event_date) AS last_done,
                COUNT(*) AS times_done
            FROM screening_events
            GROUP BY patient_id, screening_type
        ),
        combined AS (
            SELECT
                e.patient_id,
                e.age,
                e.sex,
                e.stakeholder,
                e.screening_type,
                e.interval_years,
                le.last_done,
                le.times_done,
                CASE
                    WHEN le.last_done IS NULL
                        THEN 'No Data'
                    WHEN le.last_done >= DATE '2026-06-26' - INTERVAL (e.interval_years * 365) DAY
                        THEN 'Up to Date'
                    ELSE 'Overdue'
                END AS compliance_status,
                DATE_DIFF('day', le.last_done, DATE '2026-06-26') AS days_since_last
            FROM eligible e
            LEFT JOIN last_event le
                ON e.patient_id = le.patient_id
                AND e.screening_type = le.screening_type
        )
        SELECT * FROM combined
    """)

    n_raw = con.execute("SELECT COUNT(*) FROM lab_results").fetchone()[0]
    n_flags = con.execute("SELECT COUNT(*) FROM patient_flags").fetchone()[0]
    n_cv = con.execute("SELECT COUNT(*) FROM cv_risk_flags").fetchone()[0]
    n_screen = con.execute("SELECT COUNT(*) FROM screening_events").fetchone()[0]
    n_comp = con.execute("SELECT COUNT(*) FROM screening_compliance").fetchone()[0]
    print(f"lab_results:          {n_raw:,} rows")
    print(f"patient_flags:        {n_flags:,} rows")
    print(f"cv_risk_flags:        {n_cv:,} rows")
    print(f"screening_events:     {n_screen:,} rows")
    print(f"screening_compliance: {n_comp:,} rows")
    con.close()
    print("Database ready: " + DB_PATH)


if __name__ == "__main__":
    main()
