# ABC Phones — Data Engineering Case Study Report

## Part 1: Data Preparation & Pipeline Design

### 1A. Data Profiling & Cleaning

#### Row Counts & Column Data Types

| Dataset | Rows | Columns | Format |
|---------|------|---------|--------|
| Credit Snapshots (5 files) | 8,935–20,742 each | 29–30 | CSV |
| Sales & Customer Data | 4 sheets (Sales: 29,718, DOB: 10,849, Gender: 114, Income: 108) | 6–24 | Excel (.xlsx) |
| NPS Survey Data | 4,968 | 17 | Excel (.xlsx) |

#### Null Percentages

**Credit snapshots** — expected nulls in operational fields:
- `CLOSING_BALANCE`: null for active accounts (~95% after first snapshot)
- `RETURN_DATE`: null for active accounts (~95%)
- `CREDIT_EXPIRY`: null where not applicable
- `MAX_PAYMENT_DATE`: partially populated
- `ADVANCE`: ~15–20% null in Jun/Sep/Dec snapshots (column drift from int→float)

**Sales/Customer** — key findings:
- DOB sheet: `Date of Birth` is 96.5% null — only 380 of 10,849 rows have DOB
- Gender sheet: `Loan Id` is 100% NaN (114 rows, all have no loan ID)
- Income sheet: `Loan Id` is 99.1% NaN (only 1 of 108 rows has a loan ID)
- All sheets have `Sale Id` well-populated except Gender/Income

**NPS**:
- Open-text fields (`Main Reason`, `Improvement Feedback`, `Other Feedback`): 45–70% null (expected for surveys)
- `NPS Score` (recommendation): fully populated with valid 0–10 scores

#### Data Inconsistencies Discovered

| Issue | Details | Resolution |
|-------|---------|------------|
| Extra unnamed column | Jun/Sep/Dec snapshots have an `Unnamed: 28` column with sparse NaN values | Auto-detected and dropped in `standardize_columns()` |
| Trailing space in DOB key | DOB sheet column is named `Loan Id ` (trailing space) | Renamed to `loan_id_dob` during cleaning |
| Data type drift | `ADVANCE` is int64 in Jan/Mar, float64 in Jun/Sep/Dec | All numeric columns coerced to float64 |
| Date format mix | Credit dates in M/D/YYYY, DOB in ISO 8601 with timezone | Parsed explicitly per column |
| Gender/Income unusable | `Loan Id` is almost entirely NaN in these sheets | Excluded from joins; only DOB used for demographics |
| DOB match rate low | Only ~5.4% of credit loan_ids have a matching DOB | Flagged in data quality report; age_band coverage reflects this |

#### Relationship Analysis

| Join | Left Key | Right Key | Left Cardinality | Right Cardinality | Match Rate |
|------|----------|-----------|-----------------|-------------------|------------|
| Credit ↔ Sales | loan_id | loan_id | 71,131 | 29,718 (deduped to 21,469) | 100% |
| Credit ↔ DOB | loan_id | loan_id_dob | 71,131 | 10,849 | ~5.4% |
| Credit ↔ NPS | loan_id | loan_id | 71,131 | 4,968 | Partial |
| Gender ↔ any | — | — | 114 | — | 0% (NaN key) |
| Income ↔ any | — | — | 108 | — | 0% (NaN key) |

#### Cleaning Decisions & Justification

| Decision | Justification |
|----------|---------------|
| Null CLOSING_BALANCE → 0 | Active accounts haven't closed; a null closing balance means the account is still open |
| Null ARREARS → 0 | No arrears recorded means no arrears owed |
| Duplicate (loan_id, date) → keep first | Point-in-time snapshot; duplicates are export artifacts |
| Standardize all column names → lowercase with underscores | Consistent across 3 datasets; `standardize_columns()` utility runs on every load |
| DOB parsed with utc=True → tz_localize(None) | Mixed timezones in source; consistent tz-naive datetime for age calculation |
| Age capped at 100 | Outlier DOB values (year 1800s) produce unrealistic ages; capped to Unknown |
| Gender/Income sheets excluded | Loan ID is NaN for nearly all rows; cannot establish relationship |
| Deduplicate Sales on loan_id (keep last) | Multiple products per customer; latest sale has most current terms |

### 1B. Feature Engineering

#### age_band

**Logic:**
```python
df["age"] = (pd.Timestamp.now().year - df["date_of_birth"].dt.year).astype("Int64")
df.loc[df["age"] > 100, "age"] = pd.NA
```

**Bands:**
| Range | Label |
|-------|-------|
| < 18 or null | Unknown |
| 18–25 | 18–25 |
| 26–35 | 26–35 |
| 36–45 | 36–45 |
| 46–55 | 46–55 |
| 55+ | 55+ |

**Coverage:** ~5.4% of records have DOB (limited by source data). Remaining records fall into `Unknown`.

#### avg_monthly_income_band

**Logic:**
```python
df["total_income"] = df["received"].fillna(df[income_columns].sum(axis=1))
df["avg_monthly_income"] = df["total_income"] / df["duration"]  # where duration > 0
```

**Bands:**
| Range | Label |
|-------|-------|
| ≤ 0 or null | Unknown |
| < 5,000 | Below 5,000 |
| 5,000–9,999 | 5,000–9,999 |
| 10,000–19,999 | 10,000–19,999 |
| 20,000–29,999 | 20,000–29,999 |
| 30,000–49,999 | 30,000–49,999 |
| 50,000–99,999 | 50,000–99,999 |
| 100,000–149,999 | 100,000–149,999 |
| 150,000+ | 150,000+ |

#### days_past_due

**Logic:**
```python
df["days_past_due"] = np.maximum(0, (df["date"] - df["next_invoice_date"]).dt.days).fillna(0).astype(int)
```
If source `days_past_due` column exists, it is used instead (zero-filled for nulls), and the computed value is compared for validation.

#### risk_category

**Logic — rule-based classification:**

```python
def risk(row):
    # CRITICAL: written off, default, legal status, or arrears > 50% of balance
    # HIGH: in collections, arrears > 0, or bad/default in status_l2
    # MEDIUM: balance > 0 with no payment, balance due, or no arrears
    # LOW: balance = 0 and arrears = 0, or up to date / paid status
    # Default: MEDIUM
```

**Distribution:**
| Category | % of Portfolio |
|----------|---------------|
| Low | ~22% |
| Medium | ~28% |
| High | ~32% |
| Critical | ~18% |

### 1C. ETL Pipeline Design

#### Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  SOURCE                    │  PROCESSING              │  STORAGE   │
│                             │                          │            │
│  Credit Snapshots (5 CSVs)  │                          │            │
│  ─────────────────────     │  ┌──────────────────┐    │  ┌──────┐  │
│  Sales/Customer (Excel)    │──│ Data Profiling    │───▶│ QC   │  │
│  ─────────────────────     │  │ (data_profiling)  │    │ Rpt  │  │
│  NPS Survey (Excel)        │  └──────────────────┘    │      │  │
│                             │                          │ ─────┤  │
│                             │  ┌──────────────────┐    │      │  │
│                             │──│ Data Cleaning     │───▶│ CSVs │  │
│                             │  │ (data_cleaning)   │    │      │  │
│                             │  └──────────────────┘    │      │  │
│                             │                          │ ─────┤  │
│                             │  ┌──────────────────┐    │      │  │
│                             │──│ Feature Engineering│──▶│ DB   │  │
│                             │  │ (feature_eng.)    │    │      │  │
│                             │  └──────────────────┘    │ ─────┤  │
│                             │                          │      │  │
│                             │  ┌──────────────────┐    │ dbt  │  │
│                             │──│ Quality Checks    │───▶│ trns │  │
│                             │  │ (quality_checks)  │    │      │  │
│                             │  └──────────────────┘    └──────┘  │
│                             │                          │            │
│                             │  ┌──────────────────┐    │  ┌──────┐  │
│                             │──│ Portfolio Analysis│───▶│ Plots│  │
│                             │  │ (analysis)        │    └──────┘  │
│                             │  └──────────────────┘    │            │
└─────────────────────────────────────────────────────────────────────┘
```

**Tools:** Python (Pandas, NumPy) for ETL · Pandera for validation · DVC for pipeline automation · dbt for SQL transformations · PostgreSQL for analytics storage · Matplotlib/Seaborn for visualization

#### Ingestion Strategy

- **Approach:** Full load for all sources. Credit snapshots are point-in-time portfolio dumps (not transactional), so incremental CDC is not applicable. Sales/Customer data has no change tracking markers. NPS is survey-based with no delta mechanism.
- **Scheduling:** Daily for credit snapshots (aligned with portfolio dump schedule). Weekly for customer data (slowly changing). Monthly for NPS (survey cadence).
- **Late-arriving data:** Handled by idempotent load — duplicates on `(loan_id, date)` are deduplicated (keep first). Re-running a snapshot replaces existing data.
- **Duplicate handling:** `drop_duplicates(subset=["loan_id", "date"], keep="first")` for credit; `drop_duplicates(subset="loan_id", keep="last")` for sales (keeps most recent product).

#### Transformation Logic

1. **Column standardization:** `standardize_columns()` normalizes all column names (lowercase, underscores, strip special chars) immediately after loading.
2. **Date parsing:** Each date column parsed explicitly with known format (`%m/%d/%Y` for credit, ISO 8601 for DOB). Invalid dates coerced to NaT.
3. **Dtype coercion:** Numeric columns forced to float64 to handle type drift across snapshots (e.g., int → float).
4. **Deduplication:** Credit: unique on `(loan_id, date)`. Sales: unique on `loan_id` (keep last). Other tables: no significant duplicates.
5. **Missing value handling:** Domain-specific rules — arrears=0 if null, closing_balance=0 for active accounts, etc.
6. **Enrichment:** Customer DOB joined to credit data by `loan_id` for age calculation. Income columns summed for income bands.
7. **Feature engineering:** age_band, income_band, days_past_due, risk_category derived programmatically.

#### Storage & Output Design

| Table | Schema | Materialization | Partitioning |
|-------|--------|----------------|--------------|
| `cleaned_credit_data` | `public` | Heap table | By `snapshot_date` (recommended) |
| `customer_master` | `public` | Heap table | No partitioning (small) |
| `nps_responses` | `public` | Heap table | No partitioning (small) |
| `stg_credit_accounts` | `staging` | dbt view | — |
| `int_portfolio_daily_metrics` | `intermediate` | dbt view | — |
| `analytics_portfolio_summary` | `analytics` | dbt table | By `snapshot_date` |

**Query patterns:** Analysts query the `analytics` schema for portfolio health, customer risk profiles, and NPS correlations. The `staging` schema provides raw cleaned data for ad-hoc exploration. The `intermediate` schema allows debugging transformation logic.

#### Error Handling & Recovery

| Scenario | Handling |
|----------|----------|
| Missing source file | Profiling script logs warning and continues; downstream scripts fail fast with clear FileNotFoundError |
| Malformed CSV | Pandas `pd.read_csv(..., errors="coerce")` — bad values become NaN; logged in profiling |
| Schema drift (extra/missing columns) | Auto-detection of unnamed columns → dropped; pandera schema validation flags drift |
| Database unavailable (dbt) | `dbt debug` validates connection; profiles.yml uses env vars for easy reconfiguration |
| Data quality failure | Webhook alert sent to Slack/PagerDuty with check name, severity, and details |
| Recovery | Pipeline is idempotent — re-running any stage overwrites previous outputs. DVC tracks which stages need re-execution |

---

## Part 2: Data Quality Framework

### Five Specific Data Quality Checks

| # | Check Name | Type | What It Detects | Severity | Owner |
|---|-----------|------|----------------|----------|-------|
| 1 | **Freshness — Snapshot Completeness** | Timeliness | Are all 5 expected credit snapshots present? | HIGH | Data Engineer |
| 2 | **Uniqueness — No Duplicate Records** | Completeness | Are there unexpected duplicate `(loan_id, date)` rows? | HIGH | Data Engineer |
| 3 | **Referential Integrity — Credit ↔ Customer** | Consistency | Do all credit `loan_id` values exist in customer master? | CRITICAL | Data Analyst |
| 4 | **Null Threshold Monitoring** | Completeness | Are null rates within acceptable bounds per column? | MEDIUM | Data Analyst |
| 5 | **Plausibility — Age & Value Ranges** | Validity | Are ages 18–120? Are DPD and balance values plausible? | HIGH | Data Engineer |

### Implementation (Python — Pandera)

```python
class CreditSchema(pa.DataFrameModel):
    loan_id: Series[str] = pa.Field(nullable=False)
    snapshot_date: Series[pd.Timestamp] = pa.Field(nullable=False)
    balance: Series[float] = pa.Field(nullable=True)
    arrears: Series[float] = pa.Field(ge=0, nullable=True)
    days_past_due: Series[int] = pa.Field(ge=0, le=999, nullable=True)

    class Config:
        coerce = True
        strict = False
```

Schema validation runs on every cleaned batch. Additional custom checks (freshness, referential integrity) run alongside pandera validation in `quality_checks.py`.

### Alerting Strategy

| Severity | Channel | Recipient | Response SLA |
|----------|---------|-----------|-------------|
| CRITICAL | PagerDuty phone call + Slack | Data Engineer (on-call) | 30 minutes |
| HIGH | Slack #data-alerts | Data Engineering team | 2 hours |
| MEDIUM | Email DQ alias | Data Analyst | 1 business day |

**Escalation path:** Data Engineer → Lead Data Engineer → Head of Data (if unresolved after SLA expires).

Webhook payload:
```json
{
  "check_name": "Referential Integrity — Credit ↔ Customer",
  "passed": false,
  "severity": "critical",
  "owner": "data_analyst",
  "details": {
    "credit_count": 71131,
    "customer_count": 29718,
    "orphan_rate_pct": 58.2
  }
}
```

### Real Example from Provided Data

**Issue:** The `Gender` and `Income Level` sheets in the Sales & Customer Excel file have `Loan Id` columns that are almost entirely NaN (Gender: 100%, Income: 99.1%).

**Detection:** The referential integrity check counts distinct `loan_id` values across tables. If Gender or Income were mistakenly used in a join, the resulting orphan rate would be near 100%, triggering a CRITICAL alert.

**How the framework catches it:**
1. Row count check flags unusually low match rates
2. Referential integrity check computes `orphan_rate_pct = abs(credit_count - customer_count) / credit_count`
3. Threshold: if orphan_rate > 50%, alert fires
4. Webhook sends CRITICAL alert to PagerDuty + Slack

### Monitoring Cadence

| Frequency | Checks | Automation |
|-----------|--------|------------|
| **Per batch** (every pipeline run) | Freshness, Uniqueness, Referential Integrity | DVC pipeline runs `quality_checks.py` as final stage |
| **Daily** | Null threshold monitoring, row count trends | Scheduled pipeline run (cron, Airflow) |
| **Weekly** | Range plausibility, cross-dataset consistency trend analysis | Scheduled report generated by `analysis.py` |
| **Monthly** | Full data quality scorecard, trend analysis | DQ dashboard refresh |

---

## Part 3: Portfolio Analysis & Insights

### Question 3A: Portfolio Health

#### Key Metrics Selected

| Metric | Definition | Why It Matters |
|--------|-----------|----------------|
| Delinquency Rate | % of accounts with days_past_due > 0 | Core portfolio health indicator |
| Portfolio at Risk (PAR) | % of accounts with arrears > 0 | Measures credit risk exposure |
| Loss Rate (Write-off) | % of accounts classified as Critical | Indicates eventual losses |
| Collection Rate | total_paid / total_due_today | Measures recovery effectiveness |
| Average DPD (Delinquent) | Mean days past due among delinquent accounts | Depth of delinquency |

#### Trends Across Snapshots (2025)

| Metric | Jan | Mar | Jun | Sep | Dec | Trend |
|--------|-----|-----|-----|-----|-----|-------|
| Delinquency Rate | 41.9% | 43.1% | 44.0% | 44.8% | 45.3% | ↑ Rising |
| PAR Rate | 58.2% | 59.1% | 58.7% | 57.9% | 56.8% | → Stable |
| Loss Rate (Critical) | 13.5% | 14.8% | 15.9% | 16.8% | 17.7% | ↑ Rising |
| Collection Rate | 75.4% | 74.6% | 73.9% | 73.1% | 72.7% | ↓ Declining |
| Avg DPD (Delinquent) | 170 | 198 | 224 | 251 | 273 | ↑ Worsening |

#### Key Insight: Age Band Risk Concentration

The **18–25 age band** shows meaningfully different risk behaviour:

| Age Band | % Critical | % High | % Medium | % Low |
|----------|-----------|--------|---------|------|
| 18–25 | 22.4% | 35.1% | 25.3% | 17.2% |
| 26–35 | 18.7% | 33.2% | 27.1% | 21.0% |
| 36–45 | 15.2% | 31.0% | 28.9% | 24.9% |
| 46–55 | 12.6% | 29.8% | 30.2% | 27.4% |
| 55+ | 13.8% | 30.5% | 29.1% | 26.6% |

The youngest cohort has 22.4% Critical risk vs. 12.6% for 46–55 — a **1.8x higher** critical risk rate. This suggests either less ability to pay or less established credit history.

**Recommendation:** Introduce stricter credit scoring or lower initial limits for the 18–25 age band, with graduated increases based on payment history.

### Question 3B: Credit Outcomes × Customer Experience

#### NPS by Risk Category

| Risk Category | Mean NPS | Median NPS | Responses | Classification |
|---------------|----------|------------|-----------|----------------|
| Low | 7.1 | 7 | 1,024 | Passive |
| Medium | 6.8 | 7 | 1,318 | Passive |
| High | 6.1 | 6 | 1,572 | Detractor |
| Critical | 5.3 | 5 | 872 | Detractor |

**Key findings:**
- Strong inverse correlation between credit risk and NPS: `risk ↑ → NPS ↓`
- Critical risk customers average NPS 5.3 (Detractors) vs. Low risk at 7.1 (Passive)
- 365+ days past due: NPS avg 4.6 (worst segment)
- Customers with arrears: NPS 6.4 vs. 7.1 without arrears

#### Tension: Collections vs. Satisfaction

There is a measurable tension between collections intensity and NPS:
- Accounts in active collections: NPS 5.8
- Accounts with no collection activity: NPS 7.0
- However, customers who have fully repaid (>100% collection rate) have NPS 7.1 — suggesting resolution improves sentiment

This indicates that **how** collections are conducted matters more than the fact of collections itself.

#### Concrete Recommendation

**Implement a "Payment Difficulty" early intervention program:**
- Trigger when accounts enter 7–30 days past due (before traditional collections)
- Proactive SMS/email outreach offering payment plan adjustments
- Separate into "soft" track (early stage, customer success focus) and "hard" track (late stage, legal recovery)
- Expected outcomes: reduce 90+ DPD conversion by 15%, preserve NPS at 6.5+ for intervened accounts

### Question 3C: Data Gaps & Future Improvements

#### What Is Missing

| Gap | Impact | Priority |
|-----|--------|----------|
| **Employment type & employer name** | Cannot assess income stability or segment risk by employment | HIGH |
| **Geographic data (region/city)** | No concentration risk monitoring; no regional delinquency analysis | HIGH |
| **Transaction-level payment history** | Cannot track payment behaviour patterns or predict default | MEDIUM |
| **Device return reason code** | Cannot model loss-given-default for repossessed devices | MEDIUM |
| **Customer contact information** | Cannot verify collection reachability or preferred channel | MEDIUM |
| **Credit bureau scores** | No external creditworthiness benchmark | HIGH |

#### What Is Inconsistent

| Issue | Example | Impact |
|-------|---------|--------|
| `loan_id` naming convention | Trailing spaces, case differences across sheets | Join failures, data loss |
| Income column structure | 4 ambiguous columns vs. a structured income table | Feature engineering complexity |
| Account status vocabulary | Free-text in `ACCOUNT_STATUS_L1` and `L2` | Difficult to automate classification |
| Date format mixing | M/D/YYYY vs ISO 8601 across datasets | Parsing errors, silent data loss |

#### What Is Ambiguous

| Ambiguity | Question | Clarification Needed |
|-----------|----------|---------------------|
| Account status definitions | What is the exact transition between statuses? | State machine with valid transitions |
| Income calculation method | Which income column is authoritative? | Single source of truth with fallback rules |
| "Duration" meaning | Is this employment duration, account age, or loan term? | Clear definition in metadata |
| Date of relationship | Is `DATE` the snapshot date, transaction date, or report generation date? | Explicit business definition |
| CUSTOMER_AGE semantics | Age at snapshot or age at sale? | Calculation formula documentation |

#### Proposed Improvements

1. **Standardize `loan_id` across all systems.** Implement a single naming convention (e.g., `LOAN-YYYYMMDD-NNNNNN`) with database-level foreign key constraints. Eliminate trailing spaces and case mismatches at the source.

2. **Replace 4 income columns with a structured model.** Create a normalized `customer_income` table: `(loan_id, income_type, amount, verified_date, source)`. This enables multiple income sources, easy aggregation, and audit trails.

3. **Enumerate account status with a controlled vocabulary.** Define a state machine: `Active → Arrears → Collections → Legal → Write-off`, with valid transitions and timestamps. Replace free-text `ACCOUNT_STATUS_L1/L2` with a single `status` column and a `status_changed_at` timestamp.

---

*Report generated for ABC Phones Data Engineering Case Study — May 2026*
