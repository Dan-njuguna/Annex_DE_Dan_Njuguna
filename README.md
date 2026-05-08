# ABC Phones — Data Engineering Case Study

End-to-end data engineering pipeline processing credit snapshots, sales/customer data, and NPS surveys into analytics-ready tables with automated data quality monitoring.

**Pipeline automation:** DVC
**SQL transformations:** dbt (medallion architecture: staging → intermediate → analytics)

---

## Step-by-Step Workflow

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- Docker & Docker Compose (for PostgreSQL)

All dependencies are managed via `pyproject.toml` + `uv.lock`.

---

### Step 1: Clone & Install

```bash
git clone <repo-url> Annex_DE_Dan
cd Annex_DE_Dan
uv venv && source .venv/bin/activate && uv sync
```

### Step 2: Configure Environment

```bash
cp .env.example .env
```

Edit `.env` if your PostgreSQL credentials differ from the defaults:

```ini
DB_HOST=localhost
DB_PORT=5432
DB_USER=abcphones
DB_PASSWORD=abcphones_secret
DB_NAME=abcphones
```

### Step 3: Start PostgreSQL

```bash
docker compose up -d
```

This starts PostgreSQL 16 on port 5432 with schemas `public`, `staging`, `intermediate`, `analytics`.

### Step 4: Place Raw Data

```bash
unzip path/to/dataset.zip -d data/raw/
```

Expected structure after extraction:

```
data/raw/
├── credit_data/Credit Data/
│   ├── Credit Data - 01-01-2025.csv
│   ├── Credit Data - 30-03-2025.csv
│   ├── Credit Data - 30-06-2025.csv
│   ├── Credit Data - 30-09-2025.csv
│   └── Credit Data - 30-12-2025.csv
├── sales_customer/Sales and Customer Data.xlsx
└── nps/NPS Data (1).xlsx
```

### Step 5: Run the ETL Pipeline

```bash
uv run dvc repro
```

This runs all ETL stages in order (cleaning, feature engineering, quality checks, analysis, and DB load):

```
profile_data ──→ clean_data ──→ engineer_features ──→ check_quality
                     │                                     └──→ analyze
                     └──→ load_to_db (loads enriched CSV into PostgreSQL)
```

Outputs appear in `outputs/`:

| Script                  | Produces                                                                        |
| ----------------------- | ------------------------------------------------------------------------------- |
| `data_profiling`      | `outputs/data_quality_report.md`                                              |
| `data_cleaning`       | `outputs/cleaned_summary.csv`, `customer_master.csv`, `nps_responses.csv` |
| `feature_engineering` | `outputs/credit_enriched.csv`                                                 |
| `quality_checks`      | `outputs/dq_check_results.json`                                               |
| `analysis`            | `outputs/portfolio_metrics.csv`, `outputs/plots/*.png`                      |
| `load_to_db`          | PostgreSQL tables (`cleaned_credit_data`, `customer_master`, `nps_responses`) |

Before loading into PostgreSQL, `load_to_db` renames verbose survey columns, renames `date` → `snapshot_date`, adds `ingested_at` timestamps, and appends `gender`/`citizenship` columns so the DB schema matches dbt model expectations.

> **Alternate:** Run scripts individually with `uv run python -m scripts.<name>`.

### Step 6: Run dbt Transformations

```bash
cd transform && uv run dbt build
```

This executes the medallion architecture:

```
staging (bronze, views) ──→ intermediate (silver, views) ──→ analytics (gold, tables)
```

| Layer  | Models                                                                                                        | Schema           |
| ------ | ------------------------------------------------------------------------------------------------------------- | ---------------- |
| Bronze | `stg_credit_accounts`, `stg_customers`, `stg_nps_responses`                                             | `staging`      |
| Silver | `int_account_latest`, `int_portfolio_daily_metrics`, `int_customer_risk_profiles`, `int_nps_enriched` | `intermediate` |
| Gold   | `analytics_portfolio_summary`, `analytics_customer_risk`, `analytics_nps_correlation`                   | `analytics`    |

### Step 7: Generate Outputs (Optional)

```bash
uv run python -m scripts.generate_diagram    # → pipeline_design/architecture.png
uv run python -m scripts.generate_slides     # → slides/Annex_DE_Presentation.pdf
```

---

## Quick Reference

### Running Scripts Individually

```bash
# Pipeline scripts (run as modules)
uv run python -m scripts.data_profiling
uv run python -m scripts.data_cleaning
uv run python -m scripts.feature_engineering
DQ_WEBHOOK_URL="" uv run python -m scripts.quality_checks
uv run python -m scripts.analysis

# Utility scripts
uv run python -m scripts.load_to_db
uv run python -m scripts.generate_diagram
uv run python -m scripts.generate_slides

# DVC
uv run dvc repro          # Full pipeline
uv run dvc dag            # View dependency graph
```

### dbt Commands

```bash
cd transform

uv run dbt build                                  # All models
uv run dbt run --select staging                   # Bronze only
uv run dbt run --select intermediate              # Silver only
uv run dbt run --select analytics                 # Gold only
uv run dbt run --select +analytics_customer_risk  # Model + upstream deps
uv run dbt test                                   # Run tests
uv run dbt docs generate && uv run dbt docs serve # Documentation
uv run dbt debug                                  # Verify connection
uv run dbt ls                                     # List models
```

### PostgreSQL

```bash
docker compose up -d                      # Start
docker compose down                       # Stop
docker compose exec db psql -U abcphones  # Interactive shell
psql -h localhost -U abcphones -d abcphones  # From host
```

### Environment Variables

```ini
# Local:      DB_HOST=localhost
# Docker:     DB_HOST=db
DB_HOST=localhost
DB_PORT=5432
DB_USER=abcphones
DB_PASSWORD=abcphones_secret
DB_NAME=abcphones
```

---

## Feature Engineering

| Feature                     | Method                                                 | Bands                                                                                     |
| --------------------------- | ------------------------------------------------------ | ----------------------------------------------------------------------------------------- |
| `age_band`                | `current_year - dob_year` (outliers >100 → Unknown) | 18–25, 26–35, 36–45, 46–55, 55+                                                       |
| `avg_monthly_income_band` | `sum(income_cols) / duration`                        | <5K / 5–9,999 / 10–19,999 / 20–29,999 / 30–49,999 / 50–99,999 / 100–149,999 / 150K+ |
| `days_past_due`           | `max(0, date - next_invoice_date).days`              | Integer                                                                                   |
| `risk_category`           | Rules on status, arrears, balance, payment             | Low / Medium / High / Critical                                                            |

## Data Quality Checks

| Check                 | Severity | Description                                  |
| --------------------- | -------- | -------------------------------------------- |
| Freshness             | HIGH     | 5 credit snapshots expected per batch        |
| Uniqueness            | HIGH     | No duplicate `(loan_id, date)` rows        |
| Referential Integrity | CRITICAL | All credit loan_ids exist in customer master |
| Null Thresholds       | MEDIUM   | % nulls per column within tolerance          |
| Range / Plausibility  | MEDIUM   | Ages 18–120, balance ≥ 0, DPD ≥ 0         |

## Key Assumptions

| Assumption                                  | Rationale                             |
| ------------------------------------------- | ------------------------------------- |
| DATE in M/D/YYYY format                     | Observed pattern across all snapshots |
| Null CLOSING_BALANCE = 0                    | Active accounts haven't closed        |
| Null ARREARS = 0                            | No arrears if unrecorded              |
| Gender/Income sheets excluded               | Loan Id column mostly NaN             |
| DOB mixed timezones → utc=True → tz-naive | Consistent age calculation            |
| Age capped at 100                           | Outlier DOB values                    |
| Income = Received field                     | Most comprehensive income column      |

## Repository Structure

```
Annex_DE_Dan/
├── README.md
├── pyproject.toml, uv.lock          # Python deps (uv)
├── dvc.yaml, .dvc/                  # DVC pipeline
├── docker-compose.yml               # PostgreSQL
├── .env                             # DB config
├── scripts/                         # ETL scripts
│   ├── data_profiling.py            #   Profile raw data
│   ├── data_cleaning.py             #   Clean & standardize
│   ├── feature_engineering.py       #   Derive features
│   ├── quality_checks.py            #   DQ checks (pandera)
│   ├── analysis.py                  #   Portfolio analysis
│   ├── load_to_db.py                #   Load CSVs → PostgreSQL
│   ├── generate_diagram.py          #   Architecture diagram
│   └── generate_slides.py           #   Presentation PDF
├── transform/                       # dbt project
│   ├── dbt_project.yml
│   ├── profiles.yml
│   ├── macros/generate_schema_name.sql
│   └── models/
│       ├── staging/                 #   Bronze (3 views)
│       ├── intermediate/            #   Silver (4 views)
│       └── analytics/               #   Gold (3 tables)
├── docs/
│   └── case_study_report.md         # Full case study report
├── pipeline_design/
│   └── architecture.png             # Architecture diagram
├── slides/
│   └── Annex_DE_Presentation.pdf    # Presentation deck
├── outputs/                         # Generated artifacts
├── data/raw/                        # Source data
└── migrations/
    └── init.sql                     # PostgreSQL schemas
```

## Tech Stack

Python · Pandas · NumPy · Pandera · Matplotlib · Seaborn · DVC · dbt · PostgreSQL · uv · Docker
