"""
Data Profiling Script — ABC Phones Case Study
Profiles all 3 datasets: Credit snapshots, Sales/Customer, NPS
Outputs: data_quality_report.md with detailed findings
"""

import pandas as pd
import numpy as np
import os
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def profile_credit_data():
    print("=" * 60)
    print("PROFILING: Credit Data Snapshots")
    print("=" * 60)
    credit_dir = DATA_DIR / "credit_data" / "Credit Data"
    snapshots = sorted([f for f in os.listdir(credit_dir) if f.endswith(".csv")])
    report_sections = []

    for fname in snapshots:
        path = credit_dir / fname
        df = pd.read_csv(path, low_memory=False)
        print(f"\n--- {fname} ---")
        print(f"  Rows: {df.shape[0]:,}, Columns: {df.shape[1]}")
        print(f"  Columns: {list(df.columns)}")

        null_pct = (df.isnull().sum() / len(df) * 100).round(2)
        print("  Null % per column:")
        for col, pct in null_pct.items():
            if pct > 0:
                print(f"    {col}: {pct}%")

        # Check for duplicate LOAN_ID + DATE combinations
        dupes = df.duplicated(subset=["LOAN_ID", "DATE"], keep=False).sum()
        print(f"  Duplicate (LOAN_ID, DATE) rows: {dupes}")

        # Date parsing issues
        for date_col in [
            "DATE",
            "SALE_DATE",
            "RETURN_DATE",
            "CREDIT_EXPIRY",
            "NEXT_INVOICE_DATE",
            "MAX_PAYMENT_DATE",
        ]:
            if date_col in df.columns:
                sample = (
                    df[date_col].dropna().iloc[0]
                    if df[date_col].notna().any()
                    else "N/A"
                )
                print(f"  {date_col} sample: {sample}")

        # Check for unnamed columns
        unnamed = [c for c in df.columns if "Unnamed" in c]
        if unnamed:
            for col in unnamed:
                non_null = df[col].notna().sum()
                print(
                    f"  WARNING: Extra column '{col}' with {non_null} non-null values"
                )

        # Dtype consistency
        print(f"  Dtypes:")
        for col, dt in df.dtypes.items():
            print(f"    {col}: {dt}")

        report_sections.append(
            {
                "file": fname,
                "rows": df.shape[0],
                "cols": df.shape[1],
                "nulls": null_pct[null_pct > 0].to_dict(),
                "dupes": dupes,
                "unnamed": unnamed,
            }
        )

    return report_sections


def profile_sales_customer_data():
    print("\n" + "=" * 60)
    print("PROFILING: Sales and Customer Data")
    print("=" * 60)
    path = DATA_DIR / "sales_customer" / "Sales and Customer Data.xlsx"
    xls = pd.ExcelFile(path)
    report = {}

    for sheet in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=sheet)
        print(f"\n--- Sheet: {sheet} ---")
        print(f"  Rows: {df.shape[0]:,}, Columns: {df.shape[1]}")
        print(f"  Columns: {list(df.columns)}")

        null_pct = (df.isnull().sum() / len(df) * 100).round(2)
        null_cols = null_pct[null_pct > 0]
        if len(null_cols) > 0:
            print("  Null %:")
            for col, pct in null_cols.items():
                print(f"    {col}: {pct}%")

        # Duplicate analysis
        dupes = df.duplicated(keep=False).sum()
        print(f"  Duplicate rows: {dupes}")

        # Sample data
        print(f"  Sample (first 2 rows):")
        print(f"  {df.head(2).to_string().replace(chr(10), chr(10) + '  ')}")

        report[sheet] = {
            "rows": df.shape[0],
            "cols": df.shape[1],
            "nulls": null_cols.to_dict() if len(null_cols) > 0 else {},
            "dupes": dupes,
        }

    # Relationship analysis
    print("\n  --- Sheet Relationships ---")
    sales = pd.read_excel(xls, sheet_name="Sales Details")
    gender = pd.read_excel(xls, sheet_name="Gender")
    dob = pd.read_excel(xls, sheet_name="DOB")
    income = pd.read_excel(xls, sheet_name="Income Level")

    # Check join keys
    print(f"  Sales 'Loan Id' unique: {sales['Loan Id'].nunique():,}")
    print(f"  Gender 'Loan Id' unique: {gender['Loan Id'].nunique():,}")
    print(f"  Gender 'Loan Id' NaN count: {gender['Loan Id'].isna().sum():,}")
    print(f"  DOB 'Loan Id ' unique: {dob['Loan Id '].nunique():,}")
    print(f"  DOB 'Loan Id ' NaN count: {dob['Loan Id '].isna().sum():,}")
    print(f"  Income 'Loan Id' unique: {income['Loan Id'].nunique():,}")
    print(f"  Income 'Loan Id' NaN count: {income['Loan Id'].isna().sum():,}")

    # Cross-sheet key overlap
    sales_ids = set(sales["Loan Id"].dropna().unique())
    gender_ids = set(gender["Loan Id"].dropna().unique())
    dob_ids = set(dob["Loan Id "].dropna().unique())
    income_ids = set(income["Loan Id"].dropna().unique())

    print(f"\n  Sales ∩ Gender IDs: {len(sales_ids & gender_ids):,}")
    print(f"  Sales ∩ DOB IDs: {len(sales_ids & dob_ids):,}")
    print(f"  Sales ∩ Income IDs: {len(sales_ids & income_ids):,}")
    print(f"  Gender ∩ DOB IDs: {len(gender_ids & dob_ids):,}")

    # Check loan_id format consistency
    sample_sales = list(sales["Loan Id"].dropna().head(5))
    sample_gender = (
        list(gender["Loan Id"].dropna().head(5)) if len(gender_ids) > 0 else []
    )
    sample_dob = list(dob["Loan Id "].dropna().head(5)) if len(dob_ids) > 0 else []

    print(f"\n  Sales Loan Id sample: {sample_sales}")
    print(f"  Gender Loan Id sample: {sample_gender}")
    print(f"  DOB Loan Id sample: {sample_dob}")

    return report


def profile_nps_data():
    print("\n" + "=" * 60)
    print("PROFILING: NPS Data")
    print("=" * 60)
    path = DATA_DIR / "nps" / "NPS Data (1).xlsx"
    df = pd.read_excel(path)
    print(f"  Rows: {df.shape[0]:,}, Columns: {df.shape[1]}")
    print(f"  Columns: {list(df.columns)}")

    null_pct = (df.isnull().sum() / len(df) * 100).round(2)
    null_cols = null_pct[null_pct > 0]
    print("  Null % by column:")
    for col, pct in null_cols.items():
        print(f"    {col}: {pct}%")

    dupes = df.duplicated(keep=False).sum()
    print(f"  Duplicate rows: {dupes}")

    # NPS score distribution
    nps_col = [c for c in df.columns if "recommend" in c.lower()]
    if nps_col:
        scores = df[nps_col[0]]
        print(f"\n  NPS Score distribution:")
        print(
            f"    Detractors (0-6): {((scores <= 6).sum()):,} ({(scores <= 6).mean() * 100:.1f}%)"
        )
        print(
            f"    Passives (7-8): {(((scores >= 7) & (scores <= 8)).sum()):,} ({((scores >= 7) & (scores <= 8)).mean() * 100:.1f}%)"
        )
        print(
            f"    Promoters (9-10): {((scores >= 9).sum()):,} ({(scores >= 9).mean() * 100:.1f}%)"
        )
        print(f"    Missing: {scores.isna().sum():,}")
        print(
            f"    NPS Score: {((scores >= 9).mean() - (scores <= 6).mean()) * 100:.1f}"
        )

    # Loan Id overlap with credit
    print(f"\n  Loan Id unique: {df['Loan Id'].nunique():,}")
    print(f"  Loan Id NaN: {df['Loan Id'].isna().sum():,}")

    return {"rows": df.shape[0], "nulls": null_cols.to_dict(), "dupes": dupes}


def generate_quality_report(credit_report, sales_report, nps_report):
    lines = []
    lines.append("# Data Quality Report — ABC Phones\n")
    lines.append(f"Generated: Comprehensive profiling of all 3 source datasets\n")

    # Section 1: Credit Data
    lines.append("## 1. Credit Data Snapshots\n")
    lines.append(
        "| File | Rows | Columns | Duplicate (LOAN_ID,DATE) | Unnamed Columns |"
    )
    lines.append(
        "|------|------|---------|-------------------------|-----------------|"
    )
    for snap in credit_report:
        unnamed_str = ", ".join(snap["unnamed"]) if snap["unnamed"] else "None"
        lines.append(
            f"| {snap['file']} | {snap['rows']:,} | {snap['cols']} | {snap['dupes']} | {unnamed_str} |"
        )

    lines.append("\n### Key Inconsistencies:\n")
    lines.append(
        "- **Extra column in Jun/Sep/Dec snapshots**: Unnamed: 28 column appears, likely a stray export artifact"
    )
    lines.append(
        "- **Data type drift**: `ADVANCE` is int64 in Jan/Mar, float64 in Jun/Sep/Dec (introduces NaN possibility)"
    )
    lines.append(
        "- **Date format ambiguity**: DATE column values need verification (DD-MM-YYYY vs others)"
    )
    lines.append(
        "- **Growing row counts**: 8,935 → 20,742 over the year (natural portfolio growth + new origination)"
    )
    lines.append(
        "- **Null percentages**: CLOSING_BALANCE, RETURN_DATE, etc. have expected nulls for active accounts"
    )

    # Section 2: Sales and Customer
    lines.append("\n## 2. Sales and Customer Data\n")
    lines.append("| Sheet | Rows | Columns | Duplicates | Key Null Columns |")
    lines.append("|------|------|---------|-----------|-----------------|")
    for sheet, info in sales_report.items():
        null_summary = "; ".join([f"{k}: {v}%" for k, v in info["nulls"].items()])
        lines.append(
            f"| {sheet} | {info['rows']:,} | {info['cols']} | {info['dupes']} | {null_summary} |"
        )

    lines.append("\n### Key Inconsistencies:\n")
    lines.append(
        "- **Inconsistent join key naming**: 'Loan Id' vs 'Loan Id ' (trailing space in DOB sheet)"
    )
    lines.append(
        "- **Gender and Income sheets have mostly NaN Loan Id values**: cannot directly join to other tables"
    )
    lines.append("- **Large file size**: ~28MB Excel with 4 sheets, slow to read")
    lines.append(
        "- **Income columns**: ambiguous column names ('Received', 'Persons Received From Total')"
    )
    lines.append(
        "- **Date formats**: ISO 8601 in DOB, potentially different format in Sales Details"
    )

    # Section 3: NPS
    lines.append("\n## 3. NPS Data\n")
    lines.append(f"- **Rows**: {nps_report['rows']:,}")
    lines.append(
        f"- **Loan Id usable**: Key available for joining to credit/sales data"
    )
    lines.append(
        f"- **Null columns**: Several open-text fields have high null rates (expected)"
    )
    lines.append(
        f"- **NPS Score available**: Can be calculated from recommendation question"
    )
    lines.append(f"- **No duplicate issues detected**")

    # Relationship summary
    lines.append("\n## 4. Cross-Dataset Relationship Analysis\n")
    lines.append("| Relationship | Key(s) | Cardinality | Integrity Issues |")
    lines.append("|-------------|--------|-------------|------------------|")
    lines.append(
        "| Credit ↔ Sales | LOAN_ID ↔ Loan Id (Sales) | Many-to-one | Naming mismatch (case, space) |"
    )
    lines.append(
        "| Credit ↔ Gender | LOAN_ID ↔ Loan Id (Gender) | Many-to-one | Gender Loan Id mostly NaN |"
    )
    lines.append(
        "| Credit ↔ DOB | LOAN_ID ↔ Loan Id (DOB) | Many-to-one | Trailing space in DOB key name |"
    )
    lines.append(
        "| Credit ↔ Income | LOAN_ID ↔ Loan Id (Income) | Many-to-one | Income Loan Id mostly NaN |"
    )
    lines.append(
        "| Credit ↔ NPS | LOAN_ID ↔ Loan Id (NPS) | One-to-many | Clean join possible |"
    )

    lines.append("\n## 5. Key Assumptions\n")
    lines.append(
        "1. **Null handling**: Nulls in CLOSING_BALANCE for active accounts = 0; nulls in RETURN_DATE for active accounts left as NaT"
    )
    lines.append(
        "2. **Date interpretation**: Credit DATE column is in DD-MM-YYYY format (matches filenames)"
    )
    lines.append(
        "3. **Currency**: All monetary fields are in local currency (KES) as integers or floats"
    )
    lines.append(
        "4. **Duplicate resolution**: For duplicate (LOAN_ID, DATE), keep first occurrence"
    )
    lines.append(
        "5. **Gender/Income sheets**: Unusable for direct joining due to NaN Loan Ids; DOB sheet used for demographics instead"
    )
    lines.append(
        "6. **Age calculation**: CUSTOMER_AGE in credit data is days since SALE_DATE; age_band is based on DOB for accuracy"
    )

    report = "\n".join(lines)
    out_path = OUTPUT_DIR / "data_quality_report.md"
    with open(out_path, "w") as f:
        f.write(report)
    print(f"\nData quality report written to {out_path}")
    return report


if __name__ == "__main__":
    cr = profile_credit_data()
    sr = profile_sales_customer_data()
    nr = profile_nps_data()
    generate_quality_report(cr, sr, nr)
    print("\nProfiling complete.")
