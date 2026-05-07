"""
Portfolio Analysis Script — ABC Phones Case Study
Answers Questions 3A, 3B, and 3C.
"""

import pandas as pd
import numpy as np
from pathlib import Path
import sys
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scripts.data_cleaning import (
    load_and_clean_credit_data,
    load_and_clean_sales_customer_data,
    load_and_clean_nps_data,
    build_customer_master,
    handle_missing_values,
)
from scripts.feature_engineering import (
    compute_age_band,
    compute_income_band,
    compute_days_past_due,
    compute_risk_category,
)

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs"
PLOTS_DIR = OUTPUT_DIR / "plots"
PLOTS_DIR.mkdir(parents=True, exist_ok=True)

sns.set_style("whitegrid")
plt.rcParams["figure.figsize"] = (12, 6)
plt.rcParams["figure.dpi"] = 150


# ============================================================================
# QUESTION 3A: Portfolio Health
# ============================================================================
def question_3a_portfolio_health(df):
    metrics = []

    for snapshot_date, grp in df.groupby("date"):
        total = len(grp)

        delinq = (grp["days_past_due"] > 0).sum()
        delinq_rate = delinq / total * 100

        par = (grp["arrears"] > 0).sum()
        par_rate = par / total * 100

        in_arrears = (
            grp["balance_due_status"].str.lower().str.contains("due", na=False)
        ).sum()
        arrears_rate = in_arrears / total * 100

        written_off = grp[
            grp["account_status_l1"].str.contains("write.?off", na=False, case=False)
        ]
        loss_rate = len(written_off) / total * 100
        total_balance = grp["balance"].sum()
        writeoff_balance = written_off["balance"].sum() if len(written_off) > 0 else 0
        loss_pct_balance = writeoff_balance / max(total_balance, 1) * 100

        total_paid = grp["total_paid"].sum()
        total_due = grp["total_due_today"].sum()
        collection_rate = total_paid / max(total_due, 1) * 100

        avg_dpd = grp[grp["days_past_due"] > 0]["days_past_due"].mean()

        risk_dist = grp["risk_category"].value_counts(normalize=True).to_dict()

        metrics.append(
            {
                "snapshot_date": snapshot_date,
                "total_accounts": total,
                "delinquency_rate_pct": round(delinq_rate, 2),
                "par_rate_pct": round(par_rate, 2),
                "arrears_rate_pct": round(arrears_rate, 2),
                "loss_rate_pct": round(loss_rate, 2),
                "loss_balance_pct": round(loss_pct_balance, 2),
                "collection_rate_pct": round(collection_rate, 2),
                "avg_dpd_delinquent": round(avg_dpd, 1) if not pd.isna(avg_dpd) else 0,
                "total_balance": round(total_balance, 2),
                "written_off_accounts": len(written_off),
                "low_risk_pct": round(risk_dist.get("Low", 0) * 100, 1),
                "medium_risk_pct": round(risk_dist.get("Medium", 0) * 100, 1),
                "high_risk_pct": round(risk_dist.get("High", 0) * 100, 1),
                "critical_risk_pct": round(risk_dist.get("Critical", 0) * 100, 1),
            }
        )

    df_metrics = pd.DataFrame(metrics)
    print("\nPortfolio Metrics by Snapshot:")
    print(df_metrics.to_string(index=False))
    df_metrics.to_csv(OUTPUT_DIR / "portfolio_metrics.csv", index=False)
    print(f"\nSaved to {OUTPUT_DIR / 'portfolio_metrics.csv'}")

    dates = [m["snapshot_date"] for m in metrics]

    fig, ax = plt.subplots()
    ax.plot(
        dates,
        [m["delinquency_rate_pct"] for m in metrics],
        "o-",
        label="Delinquency Rate",
        linewidth=2,
    )
    ax.plot(
        dates,
        [m["par_rate_pct"] for m in metrics],
        "s--",
        label="Portfolio at Risk (PAR)",
        linewidth=2,
    )
    ax.plot(
        dates,
        [m["loss_rate_pct"] for m in metrics],
        "x-",
        label="Write-off Rate",
        linewidth=2,
    )
    ax.set_xlabel("Snapshot Date")
    ax.set_ylabel("Rate (%)")
    ax.set_title("Portfolio Risk Metrics Over Time")
    ax.legend()
    ax.tick_params(axis="x", rotation=45)
    plt.tight_layout()
    plt.savefig(PLOTS_DIR / "portfolio_risk_trends.png")
    plt.close()
    print("  Saved portfolio_risk_trends.png")

    fig, ax = plt.subplots()
    categories = [
        "low_risk_pct",
        "medium_risk_pct",
        "high_risk_pct",
        "critical_risk_pct",
    ]
    labels = ["Low", "Medium", "High", "Critical"]
    colors = ["#2ecc71", "#f39c12", "#e74c3c", "#c0392b"]
    bottom = np.zeros(len(metrics))
    for cat, label, color in zip(categories, labels, colors):
        values = [m[cat] for m in metrics]
        ax.bar(dates, values, bottom=bottom, label=label, color=color)
        bottom += np.array(values)
    ax.set_xlabel("Snapshot Date")
    ax.set_ylabel("Portfolio Composition (%)")
    ax.set_title("Risk Category Composition Over Time")
    ax.legend(loc="upper left")
    ax.tick_params(axis="x", rotation=45)
    plt.tight_layout()
    plt.savefig(PLOTS_DIR / "risk_category_composition.png")
    plt.close()
    print("  Saved risk_category_composition.png")

    print("\n--- Segment Analysis: Age Band vs Risk ---")
    age_risk = df.groupby(["age_band", "risk_category"]).size().unstack(fill_value=0)
    age_risk_pct = age_risk.div(age_risk.sum(axis=1), axis=0) * 100
    print(age_risk_pct.to_string())

    fig, ax = plt.subplots()
    age_risk_pct.plot(kind="bar", stacked=True, ax=ax, color=colors)
    ax.set_xlabel("Age Band")
    ax.set_ylabel("Proportion (%)")
    ax.set_title("Risk Category by Age Band")
    ax.legend(loc="upper right")
    ax.tick_params(axis="x", rotation=45)
    plt.tight_layout()
    plt.savefig(PLOTS_DIR / "risk_by_age_band.png")
    plt.close()
    print("  Saved risk_by_age_band.png")

    print("\n--- Segment Analysis: Income Band vs Risk ---")
    income_risk = (
        df.groupby(["avg_monthly_income_band", "risk_category"])
        .size()
        .unstack(fill_value=0)
    )
    income_risk_pct = income_risk.div(income_risk.sum(axis=1), axis=0) * 100
    print(income_risk_pct.to_string())

    return df_metrics


# ============================================================================
# QUESTION 3B: Credit Outcomes × Customer Experience
# ============================================================================
def question_3b_credit_nps_relationship(df, df_nps):
    print("\n" + "=" * 60)
    print("QUESTION 3B: CREDIT OUTCOMES × CUSTOMER EXPERIENCE")
    print("=" * 60)

    df_latest = df.sort_values("date").groupby("loan_id").last().reset_index()

    nps_col = (
        "nps_score"
        if "nps_score" in df_nps.columns
        else [c for c in df_nps.columns if "recommend" in c.lower()][0]
    )
    df_nps_clean = df_nps.rename(columns={nps_col: "nps_score"}).copy()
    df_nps_clean["nps_score"] = pd.to_numeric(
        df_nps_clean["nps_score"], errors="coerce"
    )

    df_merged = df_latest.merge(
        df_nps_clean[["loan_id", "nps_score"]], on="loan_id", how="inner"
    )
    print(f"  Merged credit + NPS: {len(df_merged):,} records")

    def nps_category(score):
        if pd.isna(score):
            return "Unknown"
        elif score <= 6:
            return "Detractor"
        elif score <= 8:
            return "Passive"
        else:
            return "Promoter"

    df_merged["nps_category"] = df_merged["nps_score"].apply(nps_category)

    print("\n--- NPS Score by Risk Category ---")
    risk_nps = df_merged.groupby("risk_category")["nps_score"].agg(
        ["mean", "median", "count"]
    )
    print(risk_nps.to_string())

    print("\n--- NPS by Days Past Due Buckets ---")
    df_merged["dpd_bucket"] = pd.cut(
        df_merged["days_past_due"],
        bins=[-1, 0, 7, 30, 90, 365, 9999],
        labels=[
            "Current",
            "1-7 days",
            "8-30 days",
            "31-90 days",
            "91-365 days",
            "365+ days",
        ],
    )
    dpd_nps = df_merged.groupby("dpd_bucket", observed=True)["nps_score"].agg(
        ["mean", "median", "count"]
    )
    print(dpd_nps.to_string())

    df_merged["has_arrears"] = df_merged["arrears"] > 0
    arrears_nps = df_merged.groupby("has_arrears")["nps_score"].agg(
        ["mean", "median", "count"]
    )
    print("\n--- NPS by Arrears Status ---")
    print(arrears_nps.to_string())

    df_merged["collection_rate"] = np.where(
        df_merged["total_due_today"] > 0,
        df_merged["total_paid"] / df_merged["total_due_today"] * 100,
        100,
    )
    df_merged["coll_bucket"] = pd.cut(
        df_merged["collection_rate"],
        bins=[-1, 25, 50, 75, 100, 200],
        labels=["<25%", "25-50%", "50-75%", "75-100%", ">100%"],
    )
    coll_nps = df_merged.groupby("coll_bucket", observed=True)["nps_score"].agg(
        ["mean", "median", "count"]
    )
    print("\n--- NPS by Collection Rate ---")
    print(coll_nps.to_string())

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    risk_order = ["Low", "Medium", "High", "Critical"]
    risk_data = df_merged[df_merged["risk_category"].isin(risk_order)]
    sns.boxplot(
        data=risk_data,
        x="risk_category",
        y="nps_score",
        order=risk_order,
        ax=axes[0],
        palette=["#2ecc71", "#f39c12", "#e74c3c", "#c0392b"],
    )
    axes[0].set_title("NPS Score Distribution by Risk Category")
    axes[0].set_xlabel("Risk Category")
    axes[0].set_ylabel("NPS Score (0-10)")

    dpd_order = ["Current", "1-7 days", "8-30 days", "31-90 days", "91-365 days"]
    dpd_data = df_merged[df_merged["dpd_bucket"].isin(dpd_order)]
    sns.boxplot(
        data=dpd_data,
        x="dpd_bucket",
        y="nps_score",
        order=dpd_order,
        ax=axes[1],
        palette="Reds_r",
    )
    axes[1].set_title("NPS Score by Days Past Due")
    axes[1].set_xlabel("Days Past Due")
    axes[1].set_ylabel("NPS Score (0-10)")
    axes[1].tick_params(axis="x", rotation=45)

    plt.tight_layout()
    plt.savefig(PLOTS_DIR / "nps_vs_credit_risk.png")
    plt.close()
    print("  Saved nps_vs_credit_risk.png")

    fig, ax = plt.subplots()
    coll_order = ["<25%", "25-50%", "50-75%", "75-100%", ">100%"]
    coll_data = df_merged[df_merged["coll_bucket"].isin(coll_order)]
    sns.boxplot(
        data=coll_data,
        x="coll_bucket",
        y="nps_score",
        order=coll_order,
        ax=ax,
        palette="Blues_r",
    )
    ax.set_title("NPS Score by Payment Collection Rate")
    ax.set_xlabel("Collection Rate Bucket")
    ax.set_ylabel("NPS Score (0-10)")
    ax.tick_params(axis="x", rotation=45)
    plt.tight_layout()
    plt.savefig(PLOTS_DIR / "nps_vs_collection_rate.png")
    plt.close()
    print("  Saved nps_vs_collection_rate.png")

    return df_merged


# ============================================================================
# QUESTION 3C: Data Gaps & Future Improvements
# ============================================================================
def question_3c_data_gaps():
    print("\n" + "=" * 60)
    print("QUESTION 3C: DATA GAPS & FUTURE IMPROVEMENTS")
    print("=" * 60)

    gaps = """
--- WHAT'S MISSING ---
1. Employment/occupation data: No employment type (salaried/self-employed/unemployed)
   or employer name available. This limits income stability assessment.
2. Location/geographic data: No region, city, or constituency data.
   Cannot analyze geographic concentration risk or regional performance.
3. Transaction-level detail: Only snapshot-level payment summaries exist.
   No individual payment transactions or reversal logs.
4. Device return reason: return_date exists but no reason_code or condition data.
5. Customer contact info: No phone/email on record for collections outreach.
6. Credit bureau data: credit_check_done is a string field with unclear values.

--- WHAT'S INCONSISTENT ---
1. Date formats: ISO 8601 in DOB sheet, M/D/YYYY in credit CSVs, inconsistent.
2. Income calculation: 'received', 'persons_received', 'banks_received' overlap
   and the relationship between them is undefined.
3. Column naming: 'loan_id' vs 'loan_id ' (trailing space) across sheets.
4. Data types: advance/arrears as int64 in some snapshots, float64 in others.
5. Extra columns: 'unnamed: 28' appears in 3 of 5 snapshots.

--- WHAT'S AMBIGUOUS ---
1. account_status_l1/l2: No published definition of the status hierarchy.
   What is the difference between 'Active - Arrears' and 'In Collections'?
2. credit_check_done: Values are inconsistent strings (YES/NO/TRUE/FALSE/null).
3. return_policy_compliance: All values are NaN, unclear what this tracks.
4. balance_due_status: 'Advance', 'Up to date', 'Due' semantics not documented.
5. Income 'duration': Is this months of employment, or months of bank statement data?

--- PROPOSED IMPROVEMENTS ---
1. Standardize Join Keys: Enforce a single loan_id naming convention across all
   source systems. No trailing spaces, no case inconsistencies. Add foreign key
   constraints at database level.

2. Formalize an Income Model: Replace 4 overlapping income columns with a single
   structured income table: (loan_id, income_type, amount, verified_date,
   verification_method). This eliminates ambiguity about total income.

3. Add Metadata/Data Dictionary: Maintain a version-controlled data dictionary
   for all source columns with clear definitions, valid value ranges, and
   examples. Attach as YAML/JSON alongside each dataset export.

4. Structured Account Status: Replace free-text account_status_l1 with an
   enumerated type backed by a status transition table:
   (status_code, description, is_active, is_delinquent, is_terminal).
"""
    print(gaps)
    with open(OUTPUT_DIR / "data_gaps_report.md", "w") as f:
        f.write(gaps)
    print(f"Saved to {OUTPUT_DIR / 'data_gaps_report.md'}")


# ============================================================================
# MAIN
# ============================================================================
def main():
    print("=" * 60)
    print("PORTFOLIO ANALYSIS & INSIGHTS")
    print("=" * 60)

    print("\n[1/5] Loading cleaned data...")
    df_credit = load_and_clean_credit_data()
    df_sales, df_dob, df_gender, df_income = load_and_clean_sales_customer_data()
    df_nps = load_and_clean_nps_data()
    df_credit = handle_missing_values(df_credit)
    df_customer = build_customer_master(df_sales, df_dob)

    print("\n[2/5] Engineering features...")
    df = compute_age_band(df_credit, df_customer)
    df = compute_income_band(df, df_income)
    df = compute_days_past_due(df)
    df = compute_risk_category(df)

    print("\n[3/5] Question 3A: Portfolio Health...")
    metrics = question_3a_portfolio_health(df)

    print("\n[4/5] Question 3B: Credit × NPS Relationship...")
    df_nps_analysis = question_3b_credit_nps_relationship(df, df_nps)

    print("\n[5/5] Question 3C: Data Gaps & Improvements...")
    question_3c_data_gaps()

    print("\n" + "=" * 60)
    print("ANALYSIS COMPLETE")
    print("=" * 60)
    print(f"\nOutputs saved to {OUTPUT_DIR}/")
    print(f"Plots saved to {PLOTS_DIR}/")


if __name__ == "__main__":
    main()
