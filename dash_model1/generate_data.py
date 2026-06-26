import numpy as np
import pandas as pd
from scipy.stats import truncnorm
import uuid
import random
from datetime import datetime, timedelta
import os

np.random.seed(42)
random.seed(42)

N_PATIENTS = 5000
STAKEHOLDERS = ["health_plan_A", "health_plan_B", "employer_C", "clinic_D"]
STAKEHOLDER_WEIGHTS = [0.35, 0.30, 0.20, 0.15]
START_DATE = datetime(2022, 1, 1)
DAYS_RANGE = 3 * 365

COUNTRIES = ["Germany", "Brazil", "Spain", "Portugal", "United Kingdom", "France", "Netherlands"]
COUNTRY_WEIGHTS = [0.25, 0.40, 0.12, 0.10, 0.06, 0.04, 0.03]

STATES_BY_COUNTRY = {
    "Germany": ["Bayern", "Nordrhein-Westfalen", "Baden-Württemberg", "Berlin", "Hamburg", "Hessen", "Sachsen"],
    "Brazil": ["São Paulo", "Rio de Janeiro", "Minas Gerais", "Bahia", "Rio Grande do Sul", "Paraná", "Pernambuco"],
    "Spain": ["Cataluña", "Madrid", "Andalucía", "Valencia", "País Vasco", "Galicia", "Aragón"],
    "Portugal": ["Lisboa", "Porto", "Algarve", "Braga", "Setúbal", "Coimbra", "Aveiro"],
    "United Kingdom": ["England", "Scotland", "Wales", "Northern Ireland"],
    "France": ["Île-de-France", "Auvergne-Rhône-Alpes", "Nouvelle-Aquitaine", "Occitanie", "Hauts-de-France"],
    "Netherlands": ["Noord-Holland", "Zuid-Holland", "Noord-Brabant", "Utrecht", "Gelderland"],
}

# Screening protocols: (type, sex, min_age, max_age, interval_years, base_coverage)
SCREENINGS = [
    ("mammography", "F", 50, 74, 2, 0.62),
    ("pap_smear", "F", 25, 65, 3, 0.58),
    ("colonoscopy", None, 45, 75, 10, 0.38),
    ("fobt", None, 45, 75, 1, 0.50),
    ("psa", "M", 50, 69, 2, 0.44),
]

REF_DATE = datetime(2026, 6, 26)


def truncated_normal(mean, sd, low, high, size):
    a = (low - mean) / sd
    b = (high - mean) / sd
    return truncnorm.rvs(a, b, loc=mean, scale=sd, size=size)


def ckd_epi_egfr(creatinine, age, sex):
    kappa = 0.7 if sex == "F" else 0.9
    alpha = -0.241 if sex == "F" else -0.302
    sex_factor = 1.012 if sex == "F" else 1.0
    scr_k = creatinine / kappa
    egfr = (
        142
        * min(scr_k, 1) ** alpha
        * max(scr_k, 1) ** (-1.200)
        * 0.9938 ** age
        * sex_factor
    )
    return round(max(5.0, egfr), 1)


def maybe_null(value, miss_rate=0.15):
    return None if random.random() < miss_rate else value


def generate_draw(patient_id, age, sex, stakeholder, metabolic_burden, date):
    mb = metabolic_burden

    hba1c = round(max(4.0, min(14.0, 5.0 + mb * 3.5 + np.random.normal(0, 0.3))), 1)
    fasting_glucose = round(max(60, min(500, 70 + (hba1c - 4.0) * 18 + np.random.normal(0, 10))))
    total_cholesterol = round(max(100, min(400, 140 + mb * 100 + age * 0.5 + np.random.normal(0, 18))))
    hdl = round(max(20, min(100, (55 if sex == "F" else 45) - mb * 25 + np.random.normal(0, 7))))
    triglycerides = round(max(40, min(800, 80 + mb * 250 + abs(np.random.normal(0, 30)))))
    ldl = round(max(30, min(300, total_cholesterol - hdl - triglycerides / 5)))
    creatinine = round(
        max(0.4, min(8.0,
            (0.7 if sex == "F" else 0.9) + age * 0.003 + mb * 0.8 + np.random.normal(0, 0.08)
        )),
        2,
    )
    egfr = ckd_epi_egfr(creatinine, age, sex)
    tsh = round(max(0.1, min(20.0, np.random.lognormal(0.8, 0.5))), 2)
    vitamin_d = round(max(4.0, min(100.0, np.random.lognormal(3.2, 0.5))), 1)
    b12 = round(max(80, min(2000, np.random.lognormal(6.0, 0.4))))
    ferritin_mean = 40 if sex == "F" else 120
    ferritin = round(max(2, min(600, np.random.lognormal(np.log(ferritin_mean), 0.6))))
    hgb_mean = 13.0 if sex == "F" else 15.0
    hemoglobin = round(max(6.0, min(18.5, hgb_mean - mb * 1.5 + np.random.normal(0, 0.7))), 1)
    hscrp = round(max(0.1, min(50.0, np.random.lognormal(-0.5 + mb * 2.5, 0.8))), 2)
    alt = round(max(5, min(200, 15 + mb * 60 + abs(np.random.normal(0, 10)))))

    return {
        "patient_id": patient_id,
        "age": age,
        "sex": sex,
        "stakeholder": stakeholder,
        "collection_date": date,
        "hba1c": maybe_null(hba1c),
        "fasting_glucose": maybe_null(fasting_glucose),
        "total_cholesterol": maybe_null(total_cholesterol),
        "hdl": maybe_null(hdl),
        "triglycerides": maybe_null(triglycerides),
        "ldl": maybe_null(ldl),
        "creatinine": maybe_null(creatinine),
        "egfr": maybe_null(egfr),
        "tsh": maybe_null(tsh),
        "vitamin_d": maybe_null(vitamin_d),
        "b12": maybe_null(b12),
        "ferritin": maybe_null(ferritin),
        "hemoglobin": maybe_null(hemoglobin),
        "hscrp": maybe_null(hscrp),
        "alt": maybe_null(alt),
    }


def generate_screening_events(patient_ids, ages, sexes, stakeholders):
    rows = []
    for i, pid in enumerate(patient_ids):
        age = int(ages[i])
        sex = sexes[i]
        stakeholder = stakeholders[i]

        for s_type, s_sex, min_age, max_age, interval_yrs, coverage in SCREENINGS:
            if s_sex is not None and sex != s_sex:
                continue
            if not (min_age <= age <= max_age):
                continue

            # Stochastic coverage: some patients just never got screened
            if random.random() > coverage:
                continue

            # How many times screened in the past ~5 years?
            max_events = max(1, int(5 / interval_yrs))
            n_events = random.randint(1, max(1, max_events))

            # Most recent event: within 0 to interval*1.8 years ago
            max_days_ago = int(interval_yrs * 1.8 * 365)
            most_recent_days_ago = random.randint(30, max_days_ago)
            most_recent = REF_DATE - timedelta(days=most_recent_days_ago)

            dates = [most_recent]
            for _ in range(n_events - 1):
                prior = dates[-1] - timedelta(days=int(interval_yrs * 365) + random.randint(-90, 90))
                if prior > datetime(2019, 1, 1):
                    dates.append(prior)

            for dt in dates:
                rows.append({
                    "patient_id": pid,
                    "stakeholder": stakeholder,
                    "screening_type": s_type,
                    "event_date": dt,
                    "result": random.choice(["Normal", "Normal", "Normal", "Abnormal", "Inconclusive"]),
                })

    return pd.DataFrame(rows)


def main():
    print(f"Generating {N_PATIENTS} patients...")

    ages = truncated_normal(52, 15, 18, 90, N_PATIENTS).astype(int)
    sexes = np.random.choice(["M", "F"], size=N_PATIENTS)
    stakeholders = np.random.choice(STAKEHOLDERS, size=N_PATIENTS, p=STAKEHOLDER_WEIGHTS)
    countries = np.random.choice(COUNTRIES, size=N_PATIENTS, p=COUNTRY_WEIGHTS)
    state_regions = [random.choice(STATES_BY_COUNTRY[c]) for c in countries]
    patient_ids = [f"PT{str(uuid.uuid4())[:6].upper()}" for _ in range(N_PATIENTS)]
    metabolic_burdens = np.random.beta(2, 6, N_PATIENTS)

    rows = []
    for i in range(N_PATIENTS):
        n_draws = np.random.choice([1, 2, 3, 4], p=[0.30, 0.35, 0.25, 0.10])
        draw_days = sorted(random.sample(range(DAYS_RANGE), n_draws))
        for day in draw_days:
            date = START_DATE + timedelta(days=int(day))
            row = generate_draw(
                patient_ids[i], int(ages[i]), sexes[i],
                stakeholders[i], float(metabolic_burdens[i]), date,
            )
            row["country"] = countries[i]
            row["state_region"] = state_regions[i]
            rows.append(row)

    df = pd.DataFrame(rows)
    df["collection_date"] = pd.to_datetime(df["collection_date"])
    df = df.sort_values(["patient_id", "collection_date"]).reset_index(drop=True)

    os.makedirs("data", exist_ok=True)
    df.to_parquet("data/patients_raw.parquet", index=False)
    df.to_csv("data/patients_raw.csv", index=False)
    print(f"Done: {N_PATIENTS} patients, {len(df)} total draws")

    print("Generating screening events...")
    df_screen = generate_screening_events(patient_ids, ages, sexes, stakeholders)
    df_screen["event_date"] = pd.to_datetime(df_screen["event_date"])
    df_screen.to_parquet("data/screening_events.parquet", index=False)
    print(f"Done: {len(df_screen)} screening event records for {df_screen['patient_id'].nunique()} patients")

    print(f"  Diabetes proxy:    {(df['hba1c'] >= 6.5).mean():.1%}")
    print(f"  Pre-diabetes:      {((df['hba1c'] >= 5.7) & (df['hba1c'] < 6.5)).mean():.1%}")
    print(f"  CKD stage 3+:      {(df['egfr'] < 60).mean():.1%}")
    print(f"  High LDL (>=130):  {(df['ldl'] >= 130).mean():.1%}")
    print(f"  Vit D deficient:   {(df['vitamin_d'] < 20).mean():.1%}")


if __name__ == "__main__":
    main()
