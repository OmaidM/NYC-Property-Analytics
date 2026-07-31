"""
Clean and prepare the NYC Annualized Property Sales dataset (2016-2025).

Source: NYC Department of Finance / data.gov - real property sales records.

This is the extract-and-shape step. Raw NYC property data has well-known quirks
that must be handled before any modeling:

  1. SALE PRICE is text with dollar signs, commas, trailing spaces ("$1,590,000 ")
  2. ~31% of rows are $0 "sales" - these are NON-MARKET transfers (deeds between
     family members, LLCs, estates), not real sales. They must be excluded.
  3. BUILDING CLASS CATEGORY has inconsistent spacing ("01 ONE FAMILY" vs
     "01  ONE FAMILY") that splits the same category into two.
  4. Square footage and other numerics are text or missing for many rows.
  5. BOROUGH is coded 1-5; mapping to names makes everything readable.

Output: a cleaned CSV of genuine market sales, ready for modeling.

Usage (run from repo root):
    python scripts/clean_property_data.py

Requires: pip install pandas numpy
"""

from pathlib import Path

import numpy as np
import pandas as pd

RAW_FILE = Path("data/raw/export.csv")
OUT_FILE = Path("data/processed/nyc_sales_clean.csv")

BOROUGH_NAMES = {
    1: "Manhattan",
    2: "Bronx",
    3: "Brooklyn",
    4: "Queens",
    5: "Staten Island",
}

# Minimum plausible market sale. Below this are almost always non-arms-length
# transfers ($0, $1, $10 deed transfers) rather than real sales.
MIN_SALE_PRICE = 10_000
# Upper guard against data-entry errors / mega commercial outliers that would
# distort a residential price model. $50M is generous for residential NYC.
MAX_SALE_PRICE = 50_000_000


def parse_money(series: pd.Series) -> pd.Series:
    """'$1,590,000 ' -> 1590000.0 ; blanks/dashes -> NaN."""
    cleaned = (series.astype(str)
               .str.replace(r"[\$,]", "", regex=True)
               .str.strip())
    return pd.to_numeric(cleaned, errors="coerce")


def parse_numeric(series: pd.Series) -> pd.Series:
    """Generic numeric parse for columns stored as text with stray characters."""
    cleaned = series.astype(str).str.replace(r"[\$,]", "", regex=True).str.strip()
    return pd.to_numeric(cleaned, errors="coerce")


def main():
    if not RAW_FILE.exists():
        raise FileNotFoundError(
            f"Can't find {RAW_FILE}. Put the exported CSV there and run from repo root."
        )

    print(f"Reading {RAW_FILE} ...")
    df = pd.read_csv(RAW_FILE, low_memory=False)
    n_raw = len(df)
    print(f"  {n_raw:,} raw rows")

    # --- Standardize column names to snake_case -----------------------------
    df.columns = (df.columns.str.strip().str.lower()
                  .str.replace(r"[^\w]+", "_", regex=True).str.strip("_"))

    # --- Parse the key numerics ---------------------------------------------
    df["sale_price"] = parse_money(df["sale_price"])
    df["sale_date"] = pd.to_datetime(df["sale_date"], errors="coerce")
    df["gross_sqft"] = parse_numeric(df["gross_square_feet"])
    df["land_sqft"] = parse_numeric(df["land_square_feet"])
    df["year_built"] = parse_numeric(df["year_built"])
    df["residential_units"] = parse_numeric(df["residential_units"])
    df["commercial_units"] = parse_numeric(df["commercial_units"])
    df["total_units"] = parse_numeric(df["total_units"])

    # --- Readable borough + normalized category -----------------------------
    df["borough_name"] = df["borough"].map(BOROUGH_NAMES)

    # Collapse the double-space inconsistency ("01  ONE FAMILY" -> "01 ONE FAMILY")
    df["building_category"] = (df["building_class_category"]
                               .astype(str).str.replace(r"\s+", " ", regex=True)
                               .str.strip())

    # --- Filter to genuine market sales -------------------------------------
    before = len(df)
    zero_or_blank = df["sale_price"].fillna(0).le(0).sum()
    df = df[df["sale_price"].between(MIN_SALE_PRICE, MAX_SALE_PRICE)]
    print(f"\nFiltering to genuine market sales:")
    print(f"  removed {zero_or_blank:,} $0 / blank transfers (non-market deeds)")
    print(f"  removed {before - len(df) - zero_or_blank:,} outside "
          f"${MIN_SALE_PRICE:,}-${MAX_SALE_PRICE:,} range")
    print(f"  {len(df):,} genuine sales remain")

    # --- Derived features for modeling --------------------------------------
    df["sale_year"] = df["sale_date"].dt.year
    df["sale_month"] = df["sale_date"].dt.month

    # Price per square foot - the standard real-estate normalization.
    # Only meaningful where gross sqft is a real positive number.
    df["price_per_sqft"] = np.where(
        df["gross_sqft"] > 0,
        (df["sale_price"] / df["gross_sqft"]).round(2),
        np.nan,
    )

    # Building age at time of sale (guard against bogus year_built like 0)
    df["building_age"] = np.where(
        (df["year_built"] > 1800) & (df["year_built"] <= df["sale_year"]),
        df["sale_year"] - df["year_built"],
        np.nan,
    )

    # Simplified property type from the category code (first 2 chars)
    df["type_code"] = df["building_category"].str[:2].str.strip()

    # --- Report + save ------------------------------------------------------
    print("\nCleaned dataset summary:")
    print(f"  date range : {df['sale_date'].min().date()} to {df['sale_date'].max().date()}")
    print(f"  boroughs   : {df['borough_name'].value_counts().to_dict()}")
    print(f"  median sale: ${df['sale_price'].median():,.0f}")
    print(f"  rows with gross sqft: {df['gross_sqft'].gt(0).sum():,}")
    print(f"  rows with price/sqft: {df['price_per_sqft'].notna().sum():,}")

    keep_cols = [
        "borough", "borough_name", "neighborhood", "building_category", "type_code",
        "tax_class_at_time_of_sale", "building_class_at_time_of_sale",
        "address", "zip_code",
        "residential_units", "commercial_units", "total_units",
        "land_sqft", "gross_sqft", "year_built", "building_age",
        "sale_price", "price_per_sqft", "sale_date", "sale_year", "sale_month",
        "latitude", "longitude", "community_board", "council_district",
    ]
    keep_cols = [c for c in keep_cols if c in df.columns]
    out = df[keep_cols]

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_FILE, index=False)
    print(f"\nSaved {OUT_FILE}  ({len(out):,} rows, {len(out.columns)} columns)")


if __name__ == "__main__":
    main()
