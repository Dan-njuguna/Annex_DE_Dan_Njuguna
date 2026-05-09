"""
Feature Engineering Script — ABC Phones Case Study
Derives: age_band, avg_monthly_income_band, days_past_due, risk_category

Assumptions:
- DOB is joined from Sales/Customer data (DOB sheet)
- Income is computed from Income Level sheet where available
- Risk category uses ACCOUNT_STATUS_L1, ARREARS, and PAYMENT patterns
"""

import pandas as pd
import numpy as np
from pathlib import Path
from scripts.data_cleaning import (
    load_and_clean_credit_data,
    load_and_clean_sales_customer_data,
    load_and_clean_nps_data,
    build_customer_master,
    handle_missing_values,
)

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def compute_age_band(df_credit, df_customer):
    df = df_credit.merge(
        df_customer[["loan_id", "date_of_birth"]].drop_duplicates(subset="loan_id"),
        on="loan_id",
        how="left",
    )

    df["age"] = (pd.Timestamp.now().year - df["date_of_birth"].dt.year).astype("Int64")

    out_of_range = (df["age"] < 18) | (df["age"] > 120)
    n_out = out_of_range.sum()
    if n_out > 0:
        print(f"  WARNING: {n_out} rows with age outside 18-120 range")
        print(f"    Min age: {df['age'].min()}, Max age: {df['age'].max()}")

    df["age_out_of_range"] = out_of_range
    df.loc[out_of_range, "age"] = pd.NA

    def age_band(age):
        if pd.isna(age) or age < 18:
            return "Unknown"
        elif age <= 25:
            return "18-25"
        elif age <= 35:
            return "26-35"
        elif age <= 45:
            return "36-45"
        elif age <= 55:
            return "46-55"
        else:
            return "55+"

    df["age_band"] = df["age"].apply(age_band)
    coverage = df["age_band"].notna().mean() * 100
    print(f"  Age band coverage: {coverage:.1f}%")
    return df


def compute_income_band(df, df_income):
    income_cols = {
        "loan_id": "loan_id",
        "duration": "duration",
        "received": "received",
        "persons_received_from_total": "persons_received_from_total",
        "banks_received": "banks_received",
        "paybills_received_others": "paybills_received_others",
    }
    income_clean = df_income[list(income_cols.keys())].copy()
    income_clean.columns = list(income_cols.values())

    df = df.merge(income_clean, on="loan_id", how="left")

    if "received" in df.columns:
        df["total_income"] = df["received"].fillna(
            df[
                [
                    "persons_received_from_total",
                    "banks_received",
                    "paybills_received_others",
                ]
            ].sum(axis=1)
        )
    else:
        df["total_income"] = 0

    df["avg_monthly_income"] = np.where(
        df["duration"] > 0, df["total_income"] / df["duration"], 0
    )

    def income_band(val):
        if pd.isna(val) or val <= 0:
            return "Unknown"
        elif val < 5000:
            return "Below 5,000"
        elif val < 10000:
            return "5,000-9,999"
        elif val < 20000:
            return "10,000-19,999"
        elif val < 30000:
            return "20,000-29,999"
        elif val < 50000:
            return "30,000-49,999"
        elif val < 100000:
            return "50,000-99,999"
        elif val < 150000:
            return "100,000-149,999"
        else:
            return "150,000+"

    df["avg_monthly_income_band"] = df["avg_monthly_income"].apply(income_band)
    coverage = (df["avg_monthly_income"] > 0).mean() * 100
    print(f"  Income band coverage: {coverage:.1f}%")
    return df


def compute_days_past_due(df):
    if "days_past_due" in df.columns and df["days_past_due"].notna().any():
        df["computed_dpd"] = (
            np.maximum(0, (df["date"] - df["next_invoice_date"]).dt.days)
            .fillna(0)
            .astype(int)
        )
        source_dpd = df["days_past_due"].fillna(0).astype(int)
        diff = (df["computed_dpd"] - source_dpd).abs().sum()
        print(f"  Days past due: source vs computed total diff = {diff}")
        print(f"  Using source days_past_due (zero-filled for nulls)")
        df["days_past_due"] = source_dpd
    else:
        df["days_past_due"] = (
            np.maximum(0, (df["date"] - df["next_invoice_date"]).dt.days)
            .fillna(0)
            .astype(int)
        )
        print(f"  Days past due computed from next_invoice_date")
    return df


def compute_risk_category(df):
    def risk(row):
        status_l1 = str(row.get("account_status_l1", "")).lower()
        status_l2 = str(row.get("account_status_l2", "")).lower()
        arrears = row.get("arrears", 0) or 0
        balance = row.get("balance", 0) or 0
        payment = row.get("payment", 0) or 0
        balance_due_status = str(row.get("balance_due_status", "")).lower()

        if any(
            w in status_l1 for w in ["write-off", "written off", "default", "legal"]
        ):
            return "Critical"
        if arrears > 0 and balance > 0 and (arrears / max(balance, 1)) > 0.5:
            return "Critical"

        if any(
            w in status_l1 for w in ["collection", "arrears", "delinquent", "overdue"]
        ):
            return "High"
        if arrears > 0:
            return "High"
        if any(w in status_l2 for w in ["bad", "default", "collection"]):
            return "High"

        if balance > 0 and payment == 0:
            return "Medium"
        if any(w in balance_due_status for w in ["due", "overdue"]):
            return "Medium"
        if balance > 0 and arrears == 0:
            return "Medium"

        if balance == 0 and arrears == 0:
            return "Low"
        if any(w in balance_due_status for w in ["advance", "up to date", "paid"]):
            return "Low"

        return "Medium"

    df["risk_category"] = df.apply(risk, axis=1)
    print(f"  Risk category distribution:")
    for cat in ["Low", "Medium", "High", "Critical"]:
        pct = (df["risk_category"] == cat).mean() * 100
        print(f"    {cat}: {pct:.1f}%")
    return df


def main():
    print("=" * 60)
    print("FEATURE ENGINEERING")
    print("=" * 60)

    print("\n[1/5] Loading cleaned data...")
    df_credit = load_and_clean_credit_data()
    df_sales, df_dob, df_gender, df_income = load_and_clean_sales_customer_data()
    df_nps = load_and_clean_nps_data()
    df_credit = handle_missing_values(df_credit)
    df_customer = build_customer_master(df_sales, df_dob)

    print("\n[2/5] Computing age_band...")
    df = compute_age_band(df_credit, df_customer)

    print("\n[3/5] Computing avg_monthly_income_band...")
    df = compute_income_band(df, df_income)

    print("\n[4/5] Computing days_past_due...")
    df = compute_days_past_due(df)

    print("\n[5/5] Computing risk_category...")
    df = compute_risk_category(df)

    # Save enriched dataset
    out_path = OUTPUT_DIR / "credit_enriched.csv"
    df.to_csv(out_path, index=False)
    print(f"\nEnriched credit data saved: {out_path}")
    print(f"  Shape: {df.shape}")
    print(
        f"  Features: age_band, avg_monthly_income_band, days_past_due, risk_category"
    )

    return df


if __name__ == "__main__":
    df = main()
    print("\nFeature engineering complete.")
