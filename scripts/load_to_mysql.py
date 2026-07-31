"""
Load the cleaned NYC property sales into a MySQL database.

Schema (two tables):
    geography  -- dimension: one row per (borough, neighborhood) area
    sales      -- fact:      one row per property transaction, FK -> geography

Why this shape: borough/neighborhood is a small, repeating hierarchy (~260 areas)
that shouldn't be duplicated across 566k sale rows, so it's normalized into a
dimension. Everything about an individual transaction lives in the sales fact.

At 566k rows the database does real work - indexes on the columns we filter and
group by (borough, neighborhood, sale_year) keep aggregate queries fast.

After loading it applies the analysis views and runs data-quality checks.

SETUP (one time):
    pip install pandas sqlalchemy pymysql
    Set MYSQL_PASSWORD in your environment (or edit below).

Usage (run from repo root):
    python scripts/load_to_mysql.py
"""

import os
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

MYSQL_USER = os.environ.get("MYSQL_USER", "root")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "YOUR_PASSWORD_HERE")
MYSQL_HOST = os.environ.get("MYSQL_HOST", "localhost")
MYSQL_PORT = os.environ.get("MYSQL_PORT", "3306")
DB_NAME = "nyc_property"

DATA_FILE = Path("data/processed/nyc_sales_clean.csv")
SQL_DIR = Path("sql")


def get_server_engine():
    url = f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}"
    return create_engine(url)


def get_db_engine():
    url = f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{DB_NAME}"
    return create_engine(url)


def run_sql_file(conn, path: Path):
    if not path.exists():
        print(f"  (skipping {path.name} - not found)")
        return
    raw = path.read_text(encoding="utf-8")
    lines = [ln for ln in raw.splitlines() if not ln.lstrip().startswith("--")]
    sql = "\n".join(lines)
    for stmt in [s.strip() for s in sql.split(";") if s.strip()]:
        conn.execute(text(stmt))
    print(f"  Applied {path.name}")


def main():
    if not DATA_FILE.exists():
        raise FileNotFoundError(
            f"Can't find {DATA_FILE}. Run clean_property_data.py first, from repo root."
        )
    if "YOUR_PASSWORD_HERE" in MYSQL_PASSWORD:
        raise SystemExit("Set MYSQL_PASSWORD (env var or edit the file) first.")

    print(f"Reading {DATA_FILE} ...")
    df = pd.read_csv(DATA_FILE, low_memory=False)
    print(f"  {len(df):,} sales loaded")

    # sale_date comes back from CSV as a string in M/D/YYYY form; MySQL's DATE
    # type needs real dates (ISO). Parse it here so inserts don't get rejected.
    df["sale_date"] = pd.to_datetime(df["sale_date"], errors="coerce").dt.date

    # --- Create the database ------------------------------------------------
    with get_server_engine().begin() as conn:
        conn.execute(text(f"CREATE DATABASE IF NOT EXISTS {DB_NAME}"))
    print(f"Database '{DB_NAME}' ready.")

    engine = get_db_engine()

    # --- Build the geography dimension --------------------------------------
    # One row per distinct (borough, neighborhood). We assign a surrogate
    # integer key so the fact table can reference it compactly.
    geo = (df[["borough", "borough_name", "neighborhood"]]
           .drop_duplicates()
           .sort_values(["borough", "neighborhood"])
           .reset_index(drop=True))
    geo.insert(0, "geo_id", range(1, len(geo) + 1))
    print(f"  geography dimension: {len(geo):,} areas")

    # Map the surrogate key back onto the sales rows
    df = df.merge(geo[["geo_id", "borough", "neighborhood"]],
                  on=["borough", "neighborhood"], how="left")

    # The sales fact keeps geo_id (not the text columns, which live in the dim)
    fact_cols = [c for c in df.columns
                 if c not in ("borough_name", "neighborhood")]  # borough kept as raw code is fine to drop too
    # Drop the redundant text geography from the fact; keep geo_id
    drop_from_fact = ["borough", "borough_name", "neighborhood"]
    sales = df.drop(columns=[c for c in drop_from_fact if c in df.columns]).copy()
    sales.insert(0, "sale_id", range(1, len(sales) + 1))
    print(f"  sales fact: {len(sales):,} transactions")

    # --- Create schema (MySQL) ----------------------------------------------
    with engine.begin() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        conn.execute(text("DROP TABLE IF EXISTS sales"))
        conn.execute(text("DROP TABLE IF EXISTS geography"))
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))

        conn.execute(text("""
            CREATE TABLE geography (
                geo_id        INT PRIMARY KEY,
                borough       INT,
                borough_name  VARCHAR(30),
                neighborhood  VARCHAR(80)
            )
        """))

        conn.execute(text("""
            CREATE TABLE sales (
                sale_id                        INT PRIMARY KEY,
                geo_id                         INT,
                building_category              VARCHAR(80),
                type_code                      VARCHAR(5),
                tax_class_at_time_of_sale      VARCHAR(5),
                building_class_at_time_of_sale VARCHAR(10),
                address                        VARCHAR(200),
                zip_code                       VARCHAR(10),
                residential_units              INT,
                commercial_units               INT,
                total_units                    INT,
                land_sqft                      DOUBLE,
                gross_sqft                     DOUBLE,
                year_built                     INT,
                building_age                   DOUBLE,
                sale_price                     BIGINT,
                price_per_sqft                 DOUBLE,
                sale_date                      DATE,
                sale_year                      INT,
                sale_month                     INT,
                latitude                       DOUBLE,
                longitude                      DOUBLE,
                community_board                VARCHAR(10),
                council_district               VARCHAR(10),
                FOREIGN KEY (geo_id) REFERENCES geography(geo_id)
            )
        """))
    print("Schema created.")

    # --- Insert data (chunked - 566k rows) ----------------------------------
    # NaN -> None so MySQL accepts nulls in INT columns
    geo_ins = geo.astype(object).where(pd.notnull(geo), None)
    geo_ins.to_sql("geography", engine, if_exists="append", index=False)

    # Align sales columns to the table definition, dropping any extras
    table_cols = ["sale_id", "geo_id", "building_category", "type_code",
                  "tax_class_at_time_of_sale", "building_class_at_time_of_sale",
                  "address", "zip_code", "residential_units", "commercial_units",
                  "total_units", "land_sqft", "gross_sqft", "year_built",
                  "building_age", "sale_price", "price_per_sqft", "sale_date",
                  "sale_year", "sale_month", "latitude", "longitude",
                  "community_board", "council_district"]
    sales_ins = sales[[c for c in table_cols if c in sales.columns]].copy()
    sales_ins = sales_ins.astype(object).where(pd.notnull(sales_ins), None)

    print(f"  inserting {len(sales_ins):,} sales (chunked)...")
    sales_ins.to_sql("sales", engine, if_exists="append", index=False,
                     chunksize=5000, method="multi")

    # --- Indexes on the columns we filter / group by ------------------------
    with engine.begin() as conn:
        conn.execute(text("CREATE INDEX idx_sales_geo ON sales(geo_id)"))
        conn.execute(text("CREATE INDEX idx_sales_year ON sales(sale_year)"))
        conn.execute(text("CREATE INDEX idx_sales_type ON sales(type_code)"))
    print("Data inserted and indexed.")

    # --- Views + checks ------------------------------------------------------
    print("Applying SQL files:")
    with engine.begin() as conn:
        run_sql_file(conn, SQL_DIR / "analysis_views.sql")

    print("\nRunning data-quality checks:")
    run_quality_checks(engine)

    print(f"\nDone. Database '{DB_NAME}' built on your MySQL server.")


def run_quality_checks(engine):
    checks = {
        "sale_price_in_range":
            "SELECT sale_id FROM sales WHERE sale_price < 10000 OR sale_price > 50000000",
        "negative_sqft":
            "SELECT sale_id FROM sales WHERE gross_sqft < 0 OR land_sqft < 0",
        "sale_year_in_range":
            "SELECT sale_id FROM sales WHERE sale_year < 2016 OR sale_year > 2025",
        "impossible_building_age":
            "SELECT sale_id FROM sales WHERE building_age < 0",
        "orphan_sales":  # every sale must map to a geography row
            "SELECT s.sale_id FROM sales s "
            "LEFT JOIN geography g ON s.geo_id = g.geo_id WHERE g.geo_id IS NULL",
        "duplicate_sale_ids":
            "SELECT sale_id FROM sales GROUP BY sale_id HAVING COUNT(*) > 1",
    }
    all_pass = True
    with engine.connect() as conn:
        for name, q in checks.items():
            rows = conn.execute(text(q)).fetchall()
            if rows:
                all_pass = False
                print(f"  [FAIL] {name}: {len(rows)} problem row(s)")
            else:
                print(f"  [PASS] {name}")
    if all_pass:
        print("  All data-quality checks passed.")


if __name__ == "__main__":
    main()
