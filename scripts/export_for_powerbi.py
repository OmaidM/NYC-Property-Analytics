"""
Export NYC property analysis views to CSV for the Power BI dashboard.

Same pattern as the NFL project: dump the MySQL views to flat files so the
dashboard is self-contained and portable (opens anywhere, no live database).

This project's dashboard uses MAP visuals, so we export borough/neighborhood
aggregates with representative coordinates, plus the trend and type summaries.

Usage (run from repo root, MySQL password set):
    python scripts/export_for_powerbi.py
"""

import os
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine

MYSQL_USER = os.environ.get("MYSQL_USER", "root")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "YOUR_PASSWORD_HERE")
MYSQL_HOST = os.environ.get("MYSQL_HOST", "localhost")
MYSQL_PORT = os.environ.get("MYSQL_PORT", "3306")
DB_NAME = "nyc_property"

OUT_DIR = Path("dashboard/data")


def main():
    if "YOUR_PASSWORD_HERE" in MYSQL_PASSWORD:
        raise SystemExit("Set MYSQL_PASSWORD (env var or edit the file) first.")

    engine = create_engine(
        f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{DB_NAME}"
    )
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    exports = {
        # Borough x year trend - the market evolution charts
        "price_by_borough_year.csv":
            "SELECT * FROM v_price_by_borough_year ORDER BY borough_name, sale_year",

        # Neighborhood summary WITH coordinates for the map visual.
        # Representative point = average lat/long of that neighborhood's sales.
        "neighborhood_map.csv": """
            SELECT g.borough_name,
                   g.neighborhood,
                   COUNT(*)                        AS num_sales,
                   ROUND(AVG(s.sale_price))        AS avg_price,
                   ROUND(AVG(s.price_per_sqft), 2) AS avg_ppsf,
                   AVG(s.latitude)                 AS lat,
                   AVG(s.longitude)                AS lng
            FROM sales s
            JOIN geography g ON s.geo_id = g.geo_id
            WHERE s.latitude IS NOT NULL AND s.longitude IS NOT NULL
            GROUP BY g.borough_name, g.neighborhood
            HAVING COUNT(*) >= 30
        """,

        # Property-type summary
        "price_by_type.csv":
            "SELECT * FROM v_price_by_type ORDER BY num_sales DESC",

        # Full price table for accurate median trends: borough, year, price for
        # ALL sales (no sqft filter). The sqft filter used elsewhere excludes
        # co-ops, which skews boroughs like Manhattan toward luxury condos and
        # inflates the median. This table keeps every genuine sale.
        "price_trend.csv": """
            SELECT g.borough_name, s.sale_year, s.sale_price
            FROM sales s
            JOIN geography g ON s.geo_id = g.geo_id
        """,

        # A sample of individual sales for point-map / scatter use.
        # Full 566k is too heavy for Power BI; a stratified sample keeps it light.
        "sales_sample.csv": """
            SELECT g.borough_name, g.neighborhood,
                   s.sale_price, s.price_per_sqft, s.gross_sqft,
                   s.building_age, s.sale_year, s.building_category,
                   s.latitude, s.longitude
            FROM sales s
            JOIN geography g ON s.geo_id = g.geo_id
            WHERE s.latitude IS NOT NULL
              AND s.gross_sqft > 0
              AND MOD(s.sale_id, 10) = 0
        """,
    }

    for filename, query in exports.items():
        df = pd.read_sql(query, engine)
        path = OUT_DIR / filename
        df.to_csv(path, index=False)
        print(f"  {filename}: {len(df):,} rows")

    print(f"\nExported to {OUT_DIR}/")


if __name__ == "__main__":
    main()
