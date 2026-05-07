"""
Data Cleaning & Standardization Script — ABC Phones Case Study
Ingests raw data from all 3 sources, standardizes formats, resolves inconsistencies,
and produces clean, analytics-ready DataFrames.

Usage: python scripts/data_cleaning.py
Output: outputs/cleaned_summary.csv, plus cleaned DataFrames for downstream use
"""

import pandas as pd
import os
from .utils import standardize_columns, DATA_DIR, OUTPUT_DIR

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def load_and_clean_credit_data():
    """
    Load all 5 credit snapshots, standardize, and concatenate.

    Cleaning steps:
    1. Drop 'Unnamed: 28' extra column (present in Jun/Sep/Dec snapshots)
    2. Convert DATE to datetime (DD-MM-YYYY format based on filenames)
    3. Standardize dtypes (ADVANCE, ARREARS to float64)
    4. Remove duplicate (LOAN_ID, DATE) rows
    5. Parse all date columns consistently
    """
    credit_dir = DATA_DIR / "credit_data" / "Credit Data"
    snapshots = sorted([f for f in os.listdir(credit_dir) if f.endswith(".csv")])
    frames = []

    for fname in snapshots:
        path = credit_dir / fname
        df = pd.read_csv(path, low_memory=False)
        df = standardize_columns(df)

        # Drop unnamed extra column if present
        unnamed = [c for c in df.columns if "unnamed" in c]
        if unnamed:
            df = df.drop(columns=unnamed)

        # Standardize DATE column
        df["date"] = pd.to_datetime(df["date"], format="%m/%d/%Y", errors="coerce")

        # Parse other date columns
        date_cols = [
            "sale_date",
            "return_date",
            "credit_expiry",
            "next_invoice_date",
            "max_payment_date",
        ]
        for col in date_cols:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], format="%m/%d/%Y", errors="coerce")

        # Standardize dtypes: force float for cols that drift
        float_cols = [
            "advance",
            "arrears",
            "discount",
            "overpayment_amount",
            "balance",
            "closing_balance",
            "balance_due_to_date",
            "total_due_today",
        ]
        for col in float_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        # Drop duplicates on (loan_id, date) — keep first occurrence
        before = len(df)
        df = df.drop_duplicates(subset=["loan_id", "date"], keep="first")
        if before - len(df) > 0:
            print(f"  {fname}: dropped {before - len(df)} duplicate rows")

        frames.append(df)

    df_credit = pd.concat(frames, ignore_index=True)
    print(f"  Total credit rows: {len(df_credit):,}")
    print(f"  Unique loan_ids: {df_credit['loan_id'].nunique():,}")
    print(f"  Date range: {df_credit['date'].min()} to {df_credit['date'].max()}")
    return df_credit


def load_and_clean_sales_customer_data():
    """
    Load sales/customer data, standardize join keys, clean fields.

    Key fixes:
    1. DOB sheet has trailing space in 'Loan Id ' -> rename to 'Loan_Id'
    2. Standardize all key columns to consistent naming
    3. Clean DOB values (parse ISO 8601)
    4. Compute derived customer fields
    """
    path = DATA_DIR / "sales_customer" / "Sales and Customer Data.xlsx"
    xls = pd.ExcelFile(path)

    # Sales Details — deduplicate on LOAN_ID to reduce memory
    df_sales = pd.read_excel(xls, sheet_name="Sales Details")
    print(f"  Sales Details: {len(df_sales):,} rows, {df_sales.shape[1]} cols")

    cols_before = df_sales.columns.tolist()
    df_sales = standardize_columns(df_sales)
    print(
        f"  Standardized column names: {list(zip(cols_before[:5], df_sales.columns[:5]))}"
    )

    # Parse sale_date
    df_sales["sale_date"] = pd.to_datetime(
        df_sales["sale_date"], format="%m/%d/%Y", errors="coerce"
    )
    if "return_date" in df_sales.columns:
        df_sales["return_date"] = pd.to_datetime(
            df_sales["return_date"], format="%m/%d/%Y", errors="coerce"
        )

    # Deduplicate: keep last sale per loan_id (most recent product/terms)
    if "loan_id" in df_sales.columns:
        before = len(df_sales)
        df_sales = df_sales.drop_duplicates(subset="loan_id", keep="last")
        print(
            f"  Deduplicated Sales: {before} -> {len(df_sales)} (kept latest per loan_id)"
        )

    # DOB sheet (has trailing space in key)
    df_dob = pd.read_excel(xls, sheet_name="DOB")
    df_dob = standardize_columns(df_dob)
    df_dob = df_dob.rename(columns={"loan_id": "loan_id_dob"})

    # Parse DOB (mixed timezones in data, use utc=True)
    df_dob["date_of_birth"] = pd.to_datetime(
        df_dob["date_of_birth"], utc=True, errors="coerce"
    )
    if df_dob["date_of_birth"].dt.tz is not None:
        df_dob["date_of_birth"] = df_dob["date_of_birth"].dt.tz_localize(None)

    # Gender sheet
    df_gender = pd.read_excel(xls, sheet_name="Gender")
    df_gender = standardize_columns(df_gender)

    # Income sheet
    df_income = pd.read_excel(xls, sheet_name="Income Level")
    df_income = standardize_columns(df_income)

    return df_sales, df_dob, df_gender, df_income


def load_and_clean_nps_data():
    """
    Load NPS survey data, clean column names, parse dates.
    """
    path = DATA_DIR / "nps" / "NPS Data (1).xlsx"
    df = pd.read_excel(path)

    print(f"  NPS rows: {len(df):,}")

    df = standardize_columns(df)

    # Rename key columns for readability
    rename_map = {
        "submitted_at": "submitted_at",
        "loan_id": "loan_id",
    }
    # Find the NPS score column
    nps_col = [c for c in df.columns if "recommend" in c.lower()]
    if nps_col:
        rename_map[nps_col[0]] = "nps_score"

    df = df.rename(columns=rename_map)
    df["submitted_at"] = pd.to_datetime(df["submitted_at"], errors="coerce")

    return df


def handle_missing_values(df_credit):
    """
    Apply consistent null handling rules:

    - closing_balance: NaN for active accounts -> 0 (not closed yet)
    - return_date: NaN for active accounts -> leave as NaT
    - arrears: NaN -> 0 (no arrears)
    - advance: NaN -> 0
    - payment_amount: NaN -> 0 (no payment recorded)
    - expected_payment: NaN -> 0
    """
    fill_zero_cols = [
        "closing_balance",
        "arrears",
        "advance",
        "payment_amount",
        "expected_payment",
        "adjustment_amount",
        "prepayment_amount",
        "overpayment_amount",
    ]
    for col in fill_zero_cols:
        if col in df_credit.columns:
            df_credit[col] = df_credit[col].fillna(0)

    # For days_past_due: NaN -> 0
    if "days_past_due" in df_credit.columns:
        df_credit["days_past_due"] = df_credit["days_past_due"].fillna(0).astype(int)

    return df_credit


def build_customer_master(df_sales, df_dob):
    """
    Build a customer master table by joining Sales Details with DOB data.
    Gender and Income sheets mostly have NaN Loan Ids, so we exclude them.
    """
    # Merge sales with DOB
    df_customer = df_sales.merge(
        df_dob[["loan_id_dob", "date_of_birth"]],
        left_on="loan_id",
        right_on="loan_id_dob",
        how="left",
    )
    df_customer = df_customer.drop(columns=["loan_id_dob"])

    print(f"  Customer master: {len(df_customer):,} rows")
    print(f"  DOB match rate: {df_customer['date_of_birth'].notna().mean() * 100:.1f}%")
    return df_customer


def main():
    print("=" * 60)
    print("DATA CLEANING PIPELINE")
    print("=" * 60)

    print("\n[1/4] Loading & cleaning credit data...")
    df_credit = load_and_clean_credit_data()

    print("\n[2/4] Loading & cleaning sales/customer data...")
    df_sales, df_dob, df_gender, df_income = load_and_clean_sales_customer_data()

    print("\n[3/4] Loading & cleaning NPS data...")
    df_nps = load_and_clean_nps_data()

    print("\n[4/4] Applying missing value handling...")
    df_credit = handle_missing_values(df_credit)
    df_customer = build_customer_master(df_sales, df_dob)

    # Save all cleaned datasets as CSVs
    df_credit.to_csv(OUTPUT_DIR / "cleaned_summary.csv", index=False)
    df_customer.to_csv(OUTPUT_DIR / "customer_master.csv", index=False)
    df_nps.to_csv(OUTPUT_DIR / "nps_responses.csv", index=False)
    print(f"\n  Cleaned credit data saved ({len(df_credit):,} rows)")
    print(f"  Customer master saved ({len(df_customer):,} rows)")
    print(f"  NPS responses saved ({len(df_nps):,} rows)")

    # Return all cleaned datasets for downstream use
    return {
        "credit": df_credit,
        "customer": df_customer,
        "sales": df_sales,
        "dob": df_dob,
        "nps": df_nps,
    }


if __name__ == "__main__":
    cleaned = main()
    print("\nData cleaning complete.")
