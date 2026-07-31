-- ============================================================================
-- Data-quality checks for the NYC property sales database
-- ----------------------------------------------------------------------------
-- Each query is written to return rows ONLY when something is wrong, so an
-- empty result means the check passed. The loader runs equivalent checks in
-- Python automatically; this file lets you re-run them by hand in a SQL client.
-- ============================================================================

-- 1. Sale prices should be within the filtered market range ($10k - $50M).
--    (The cleaning step enforces this; this confirms nothing slipped through.)
SELECT sale_id, sale_price
FROM sales
WHERE sale_price < 10000 OR sale_price > 50000000;

-- 2. Square footage should never be negative.
SELECT sale_id, gross_sqft, land_sqft
FROM sales
WHERE gross_sqft < 0 OR land_sqft < 0;

-- 3. Sale years should fall within the dataset's coverage (2016-2025).
SELECT sale_id, sale_year
FROM sales
WHERE sale_year < 2016 OR sale_year > 2025;

-- 4. Building age can't be negative (built after it sold = data error).
SELECT sale_id, year_built, sale_year, building_age
FROM sales
WHERE building_age < 0;

-- 5. Referential integrity: every sale must reference a real geography row.
SELECT s.sale_id
FROM sales s
LEFT JOIN geography g ON s.geo_id = g.geo_id
WHERE g.geo_id IS NULL;

-- 6. Primary key uniqueness: no duplicated sale_id.
SELECT sale_id, COUNT(*) AS n
FROM sales
GROUP BY sale_id
HAVING COUNT(*) > 1;

-- 7. price_per_sqft should only exist where gross_sqft is positive.
--    (A price/sqft with zero or null sqft would be a divide-by-zero artifact.)
SELECT sale_id, gross_sqft, price_per_sqft
FROM sales
WHERE price_per_sqft IS NOT NULL AND (gross_sqft IS NULL OR gross_sqft <= 0);
