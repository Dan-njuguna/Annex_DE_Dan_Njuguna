"""
Load cleaned CSV outputs into PostgreSQL for dbt transformations.

Usage:
    uv run python -m scripts.load_to_db

Requires PostgreSQL running (see docker-compose.yml) and env vars configured.
"""

import os
import pandas as pd
from pathlib import Path
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
    "cleaned_summary.csv": "cleaned_credit_data",
    "customer_master.csv": "customer_master",
    "nps_responses.csv": "nps_responses",
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

    # Drop and recreate to ensure schema matches CSV exactly
    with conn.cursor() as cur:
        cur.execute(f'DROP TABLE IF EXISTS "{table_name}"')
    conn.commit()

    ddl = infer_schema(df, table_name)
    with conn.cursor() as cur:
        cur.execute(ddl)
    conn.commit()
    print(f"  Created table: {table_name}")

    # Convert DataFrame rows to list of tuples
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
            print(f"\n  SKIP: {csv_name} not found (run data_cleaning first)")
            continue
        print(f"\n  Loading {csv_name} → {table_name}...")
        load_csv_to_table(conn, csv_path, table_name)

    conn.close()

    # DVC tracking marker
    marker = OUTPUT_DIR / ".db_loaded"
    marker.touch()
    print(
        f"\nDone ({marker.name}). Run `cd transform && uv run dbt build` to transform."
    )


if __name__ == "__main__":
    main()
