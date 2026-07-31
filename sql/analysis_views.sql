-- ============================================================================
-- Analysis views for the NYC property sales database
-- ----------------------------------------------------------------------------
-- Views are saved queries that behave like virtual tables. Putting the joins
-- and filters here means the notebooks and dashboard all read from the same
-- clean, consistent definitions instead of re-deriving them each time.
-- Applied automatically by load_to_mysql.py after the data loads.
-- ============================================================================

-- Drop first so the script is safely re-runnable
DROP VIEW IF EXISTS v_sales_enriched;
DROP VIEW IF EXISTS v_price_by_borough_year;
DROP VIEW IF EXISTS v_price_by_neighborhood;
DROP VIEW IF EXISTS v_price_by_type;

-- ----------------------------------------------------------------------------
-- v_sales_enriched
-- The main analysis view: every sale joined to its borough/neighborhood names.
-- This is what the modeling notebooks read - one clean, denormalized row per
-- sale with the geography text attached.
-- ----------------------------------------------------------------------------
CREATE VIEW v_sales_enriched AS
SELECT
    s.sale_id,
    g.borough_name,
    g.neighborhood,
    s.building_category,
    s.type_code,
    s.building_class_at_time_of_sale,
    s.residential_units,
    s.commercial_units,
    s.total_units,
    s.land_sqft,
    s.gross_sqft,
    s.year_built,
    s.building_age,
    s.sale_price,
    s.price_per_sqft,
    s.sale_date,
    s.sale_year,
    s.sale_month,
    s.latitude,
    s.longitude
FROM sales s
JOIN geography g ON s.geo_id = g.geo_id;

-- ----------------------------------------------------------------------------
-- v_price_by_borough_year
-- Median-style summary of prices per borough per year. MySQL has no built-in
-- median, so we report average and count alongside min/max as a robust summary.
-- The source for the market-trend charts in the dashboard.
-- ----------------------------------------------------------------------------
CREATE VIEW v_price_by_borough_year AS
SELECT
    g.borough_name,
    s.sale_year,
    COUNT(*)                         AS num_sales,
    ROUND(AVG(s.sale_price))         AS avg_price,
    MIN(s.sale_price)                AS min_price,
    MAX(s.sale_price)                AS max_price,
    ROUND(AVG(s.price_per_sqft), 2)  AS avg_price_per_sqft
FROM sales s
JOIN geography g ON s.geo_id = g.geo_id
GROUP BY g.borough_name, s.sale_year;

-- ----------------------------------------------------------------------------
-- v_price_by_neighborhood
-- Neighborhood-level price summary, restricted to areas with enough sales to be
-- meaningful (HAVING COUNT(*) >= 30 filters out thin, noisy neighborhoods).
-- ----------------------------------------------------------------------------
CREATE VIEW v_price_by_neighborhood AS
SELECT
    g.borough_name,
    g.neighborhood,
    COUNT(*)                         AS num_sales,
    ROUND(AVG(s.sale_price))         AS avg_price,
    ROUND(AVG(s.price_per_sqft), 2)  AS avg_price_per_sqft
FROM sales s
JOIN geography g ON s.geo_id = g.geo_id
GROUP BY g.borough_name, g.neighborhood
HAVING COUNT(*) >= 30;

-- ----------------------------------------------------------------------------
-- v_price_by_type
-- Average price and size by property type (one/two-family homes, condos, etc.)
-- ----------------------------------------------------------------------------
CREATE VIEW v_price_by_type AS
SELECT
    building_category,
    COUNT(*)                         AS num_sales,
    ROUND(AVG(sale_price))           AS avg_price,
    ROUND(AVG(gross_sqft))           AS avg_gross_sqft,
    ROUND(AVG(price_per_sqft), 2)    AS avg_price_per_sqft
FROM sales
GROUP BY building_category
HAVING COUNT(*) >= 30;
