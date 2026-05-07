"""
Load cleaned CSV outputs into PostgreSQL for dbt transformations.

Cleaning happens here so DB columns match dbt model expectations:
  - credit_enriched.csv: rename date→snapshot_date, add ingested_at
  - customer_master.csv:  add gender/citizenship/ingested_at as NULL
  - nps_responses.csv:    rename verbose survey columns → concise names

Usage:
    uv run python -m scripts.load_to_db

Requires PostgreSQL running (see docker-compose.yml) and env vars configured.
"""

import os
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone
import psycopg2
from psycopg2.extras import execute_values

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs"

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "user": os.getenv("DB_USER", "abcphones"),
    "password": os.getenv("DB_PASSWORD", "abcphones_secret"),
    "dbname": os.getenv("DB_NAME", "abcphones"),
}

CSV_TABLES = {
    "credit_enriched.csv": "cleaned_credit_data",
    "customer_master.csv": "customer_master",
    "nps_responses.csv": "nps_responses",
}

NPS_COLUMN_RENAME = {
    "what_is_the_main_reason_for_your_score": "main_reason",
    "what_is_one_thing_we_could_do_to_improve_your_experience_with_us": "improvement_feedback",
    "are_you_happy_with_the_quality_and_performance_of_your_device": "happy_device",
    "are_you_happy_with_the_service_and_support_provided_by_abc_phones": "happy_service",
    "have_you_ever_experienced_a_delay_in_your_payment_reflecting_in_your_abc_account": "payment_delay",
    "have_you_ever_had_difficulty_getting_assistance_from_abc_phones_customer_support_when_needed": "difficulty_support",
    "have_you_experienced_any_battery_related_issues_with_your_mophones_device": "battery_issues",
    "have_you_used_the_mophones_app_moapp_to_manage_your_account_or_make_payments": "used_app",
    "which_communication_channel_do_you_prefer_when_contacting_mophones_for_inquiries_or_support": "preferred_channel",
    "have_you_ever_had_your_phone_lock_despite_making_a_payment_on_time": "phone_lock_issue",
    "any_other_feedback": "other_feedback",
}


def get_connection():
    return psycopg2.connect(**DB_CONFIG)


def infer_schema(df, table_name):
    type_map = {
        "int64": "BIGINT",
        "Int64": "BIGINT",
        "float64": "DOUBLE PRECISION",
        "bool": "BOOLEAN",
        "datetime64[ns]": "TIMESTAMP",
        "datetime64[ns, UTC]": "TIMESTAMPTZ",
        "object": "TEXT",
    }
    cols = []
    for col, dtype in df.dtypes.items():
        pg_type = type_map.get(str(dtype), "TEXT")
        safe_col = col.replace(" ", "_").lower()
        cols.append(f'"{safe_col}" {pg_type}')
    return (
        f'CREATE TABLE IF NOT EXISTS "{table_name}" (\n  ' + ",\n  ".join(cols) + "\n)"
    )


def load_csv_to_table(conn, csv_path, table_name):
    df = pd.read_csv(csv_path, low_memory=False)
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    # --- Per-table column cleaning ---

    if table_name == "cleaned_credit_data":
        df = df.rename(columns={"date": "snapshot_date"})

    elif table_name == "customer_master":
        df["citizenship"] = None
        df["gender"] = None

    elif table_name == "nps_responses":
        df = df.rename(columns=NPS_COLUMN_RENAME)

    # Add ingested_at timestamp for all tables
    now = datetime.now(timezone.utc)
    df["ingested_at"] = now

    # Drop and recreate to ensure schema matches
    with conn.cursor() as cur:
        cur.execute(f'DROP TABLE IF EXISTS "{table_name}" CASCADE')
    conn.commit()

    ddl = infer_schema(df, table_name)
    with conn.cursor() as cur:
        cur.execute(ddl)
    conn.commit()
    print(f"  Created table: {table_name}")

    rows = [tuple(None if pd.isna(v) else v for v in row) for row in df.to_numpy()]
    cols = [f'"{c}"' for c in df.columns]

    with conn.cursor() as cur:
        execute_values(
            cur,
            f'INSERT INTO "{table_name}" ({", ".join(cols)}) VALUES %s',
            rows,
        )
    conn.commit()
    print(f"  Loaded {len(rows)} rows into {table_name}")


def main():
    print("=" * 60)
    print("LOAD CLEANED DATA TO POSTGRESQL")
    print("=" * 60)

    print(
        f"\nConnecting to {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['dbname']}..."
    )
    conn = get_connection()
    print("  Connected.")

    for csv_name, table_name in CSV_TABLES.items():
        csv_path = OUTPUT_DIR / csv_name
        if not csv_path.exists():
            print(f"\n  SKIP: {csv_name} not found (run feature_engineering first)")
            continue
        print(f"\n  Loading {csv_name} → {table_name}...")
        load_csv_to_table(conn, csv_path, table_name)

    conn.close()

    marker = OUTPUT_DIR / ".db_loaded"
    marker.touch()
    print(
        f"\nDone ({marker.name}). Run `cd transform && uv run dbt build` to transform."
    )


if __name__ == "__main__":
    main()
