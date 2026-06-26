# Population Health Intelligence Platform
### A Clinical Analytics Layer on Top of Lab Data Infrastructure

**Prepared by:** Joao Pedro Medeiros
**Date:** June 2026

## What This Is

the platform already solves the hardest part: ingesting raw lab data from any source and delivering clean, structured biomarker records through its Lab API. What this plan adds is an **analytics intelligence layer** — a multi-tenant dashboard that transforms those harmonized biomarker records into population health insights that stakeholders can act on.

The core design principle is a **layered onion model**: one codebase, one database, filtered by identity. When the CEO logs in, they see all clients. When a health plan logs in, they see only their population — same dashboard, same analytics, scoped to their data. Every analytical result is computed from the same clinical logic, so benchmarking across populations is apples-to-apples.


## Analytics Architecture: 5 Layers

### Layer 1 — Descriptive Analysis

Before anything else, understand the data. For each biomarker — HbA1c, LDL, eGFR, Vitamin D, hsCRP, and 10 others — compute distribution statistics and flag patients above clinical thresholds.

**Example from demo cohort (5,000 patients, 4 stakeholders, 7 countries — Brazil 40%, Germany 25%, Spain 12%):**

| Biomarker | Mean | Flag threshold | % above threshold |
|---|---|---|---|
| HbA1c | 5.8% | >= 6.5% (diabetes) | 13.7% |
| HbA1c | 5.8% | 5.7-6.4% (pre-diabetes) | 39.1% |
| eGFR | 72 mL/min | < 60 (CKD Stage 3+) | 24.2% |
| LDL | 118 mg/dL | >= 130 (borderline+) | 21.0% |
| Vitamin D | 28 ng/mL | < 20 (deficiency) | 28.3% |

This layer alone is immediately valuable: a health plan can see that 39% of their members are pre-diabetic and have never been flagged in claims data.

### Layer 2 — Proxy Disease Classification

Using established clinical thresholds from ACC/AHA, KDIGO, and WHO — no proprietary algorithm, no black box — each patient receives computed flags stored in enriched tables:

**Metabolic:** diabetes proxy, pre-diabetes, glycemic status, insulin resistance index (TG/HDL)
**Cardiovascular:** LDL tier, HDL status, non-HDL cholesterol, ACC/AHA 2018 simplified risk category, statin eligibility
**Renal:** CKD-EPI eGFR calculation, CKD staging G1-G5
**Nutritional:** Vitamin D deficiency/insufficiency, anemia (sex-adjusted hemoglobin), B12 status

Every flag is traceable: the rule that produced it is documented and the source biomarker value is preserved. Nothing is modified in the source data.

**Cardiovascular risk distribution (demo cohort):**

![alt text](image-1.png)

### Layer 3 — Geographic Distribution and External Benchmarking

The same population split by country and region, surfaced on an interactive choropleth map. The geographic view allows filtering the entire dashboard by country or sub-region — turning a national prevalence number into a regional action item.

In the demo cohort Brazil is the primary market (40% of patients), followed by Germany (25%), Spain (12%), and Portugal (10%). Each country view drills into regional breakdowns — São Paulo vs. Rio Grande do Sul, Bayern vs. Berlin — enabling health plans that operate across geographies to identify where the disease burden is concentrated.

**External benchmarking via the Global Burden of Disease (GBD) API**

The most powerful use of the geographic layer is not just showing our data in isolation — it is comparing it against population-level epidemiological references. The Institute for Health Metrics and Evaluation (IHME) provides the GBD API, a publicly accessible endpoint that returns age-standardized prevalence and incidence estimates for over 370 diseases and risk factors, broken down by country and year.

For each country in the platform's population, a background query pulls the GBD estimates for the relevant conditions — diabetes, CKD, dyslipidemia — and displays them alongside the platform's observed prevalence. This answers a question no lab database can answer alone:

> "Is our population's 14% diabetes rate typical for Brazil, or is this client's membership sicker than the national average?"

For Brazil, the GBD 2021 estimate for diabetes prevalence (age-standardized) is approximately 10-11%. A health plan showing 14% in our platform is carrying measurably higher metabolic burden than the national reference — an actionable insight for underwriting and care management.

| Source | What it provides | Access |
|---|---|---|
| IHME GBD | Country-level prevalence/incidence for 370+ conditions | ihmeuw.org/gbd-api |
| WHO Global Health Observatory | Mortality, NCD indicators by country | who.int/data/gho/info/gho-odata-api |
| DATASUS (Brazil) | SUS hospitalization and mortality microdata | datasus.saude.gov.br |
| Eurostat Health | EU member state health statistics | ec.europa.eu/eurostat/api |

### Layer 4 — Statistical Intelligence

Non-parametric group comparison (Mann-Whitney U for 2 groups, Kruskal-Wallis for 3+) with effect sizes. Any biomarker, any grouping variable — by sex, glycemic status, CKD stage, CV risk tier, or stakeholder.

This layer serves two audiences simultaneously. Human analysts read box plots and p-values to identify which subgroups carry the most clinical burden. AI agents in a future state query the same endpoints programmatically to generate narrative summaries — the statistical output is structured JSON, not prose, so an LLM agent can consume it without a rewrite.

### Layer 5 — Preventive Care Compliance

Lab data and screening records together answer the question that insurers care about most: are my members doing the screenings they are supposed to do?

| Screening | Population | Interval | Source |
|---|---|---|---|
| Mammography | Women 50-74 | Every 2 years | INCA / USPSTF B |
| Pap Smear | Women 25-65 | Every 3 years | FEBRASGO / INCA |
| Colonoscopy | All 45-75 | Every 10 years | SBCE / USPSTF A |
| Fecal Occult Blood | All 45-75 | Annually | USPSTF A |
| PSA | Men 50-69 | Every 2 years | SBU, shared decision |

Each eligible patient receives one of three statuses per screening: **Up to Date**, **Overdue**, or **No Record**. In the demo cohort approximately 61% of eligible patients have no screening record — a gap invisible in claims data but immediately visible here, and directly actionable for care management teams.

## Technical Stack

| Component | Choice | Rationale |
|---|---|---|
| Data layer | DuckDB (file-based) | Zero infrastructure, analytical-speed SQL, runs locally or on any server |
| Dashboard | Streamlit | Fastest path to interactive UI; replaceable with React/Node for production |
| Charts | Altair (Vega-Lite) | Declarative, reproducible |
| Maps | Folium + streamlit-folium | Leaflet.js choropleth, no API key needed |
| External benchmarks | IHME GBD API + WHO GHO | Country-level epidemiological reference, queried live |
| Multi-tenancy | Parameterized SQL + session_state | Row-level security without a separate auth service |

## 8-Week Roadmap

**Weeks 1-2 — Foundation and first internal demo**

Data audit and EDA: biomarker coverage matrix (which tests exist, at what completeness, how many longitudinal draws per patient), Bronze/Silver/Gold table schema. Initial data enrichment: compute patient_flags and cv_risk_flags so the clinical classification layer is in place from day one. Build the first version of the dashboard covering Layers 1, 2, 3 (geographic, if the geo data quality supports it), and 5 (preventive care compliance). This first demo is high-level only — no stakeholder tenancy or row-level scoping yet. The goal is a working end-to-end proof of concept that shows the full analytical range of what the platform can produce.

**Weeks 3-4 — Internal review and next-step definition**

Present the demo to the internal team (Frederick, Frank, Garrett). Collect structured feedback on which layers are most commercially relevant, which need refinement, and what a specific paying client would actually want to see. Based on that review: further enrich the data model where gaps are identified, decide which analytical layers to prioritize for the client demo, and lock the scope for the next phase. The key output of this phase is not more code — it is a clear decision on what to build for whom.

**Weeks 5-6 — Client demo and stack evaluation**

Build a targeted demo for a specific prospective client identified in weeks 3-4 — something concrete enough that someone would pay for it. This is the first time multi-tenant scoping is fully implemented, so the client sees only their data and their population's benchmarks against national references. In parallel, run the stack evaluation: assess infrastructure costs, decide whether data flows from GCP and how, map out what preprocessing steps are needed before data reaches the dashboard (schema validation, pipeline orchestration, data contracts), and document the architecture decision for the production stack.

**Weeks 7-8 — Maturity, security, and deployment**

Harden what exists: RLS audit and credential management, error handling, monitoring, performance under realistic data volumes. Decide on the production frontend. Deploy a stable, maintainable version that the team can iterate on independently. The exit milestone is a dashboard that runs reliably against real data, is scoped correctly per stakeholder, and is ready for a second client conversation.
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        