-- ============================================================================
-- Example analytical queries - NYC property sales
-- ----------------------------------------------------------------------------
-- A guided tour from simple aggregates to window functions, showing the kinds
-- of questions the database can answer. Run these in a SQL client against the
-- nyc_property database.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. How many genuine sales, and what price range, per borough?
-- ----------------------------------------------------------------------------
SELECT
    g.borough_name,
    COUNT(*)                  AS num_sales,
    ROUND(AVG(s.sale_price))  AS avg_price
FROM sales s
JOIN geography g ON s.geo_id = g.geo_id
GROUP BY g.borough_name
ORDER BY avg_price DESC;

-- ----------------------------------------------------------------------------
-- 2. The 10 most expensive neighborhoods by average price per square foot,
--    restricted to neighborhoods with a meaningful number of sales.
--    WHERE filters individual rows (need gross_sqft to compute price/sqft);
--    HAVING filters the groups after aggregation (enough sales to trust).
-- ----------------------------------------------------------------------------
SELECT
    g.neighborhood,
    g.borough_name,
    COUNT(*)                        AS num_sales,
    ROUND(AVG(s.price_per_sqft), 2) AS avg_ppsf
FROM sales s
JOIN geography g ON s.geo_id = g.geo_id
WHERE s.price_per_sqft IS NOT NULL
GROUP BY g.neighborhood, g.borough_name
HAVING COUNT(*) >= 50
ORDER BY avg_ppsf DESC
LIMIT 10;

-- ----------------------------------------------------------------------------
-- 3. Year-over-year change in citywide average price, using a window function.
--    LAG() grabs the previous year's value in year order, so each row can
--    compare to the one before it without a self-join. The first year is NULL
--    because there's no prior period.
-- ----------------------------------------------------------------------------
SELECT
    sale_year,
    ROUND(AVG(sale_price))                                          AS avg_price,
    ROUND(AVG(sale_price) - LAG(AVG(sale_price)) OVER (ORDER BY sale_year)) AS yoy_change,
    ROUND(100.0 * (AVG(sale_price) - LAG(AVG(sale_price)) OVER (ORDER BY sale_year))
          / LAG(AVG(sale_price)) OVER (ORDER BY sale_year), 1)      AS yoy_pct
FROM sales
GROUP BY sale_year
ORDER BY sale_year;

-- ----------------------------------------------------------------------------
-- 4. Rank neighborhoods within each borough by average price.
--    RANK() OVER (PARTITION BY ...) restarts the ranking for each borough, so
--    you get "the priciest neighborhood in each borough" in one query.
-- ----------------------------------------------------------------------------
SELECT * FROM (
    SELECT
        g.borough_name,
        g.neighborhood,
        ROUND(AVG(s.sale_price)) AS avg_price,
        RANK() OVER (PARTITION BY g.borough_name
                     ORDER BY AVG(s.sale_price) DESC) AS price_rank
    FROM sales s
    JOIN geography g ON s.geo_id = g.geo_id
    GROUP BY g.borough_name, g.neighborhood
    HAVING COUNT(*) >= 30
) ranked
WHERE price_rank <= 3
ORDER BY borough_name, price_rank;

-- ----------------------------------------------------------------------------
-- 5. Did the market shift before vs after March 2020 (COVID)? A first look at
--    the causal question, comparing average price by borough in the two periods.
--    (The notebook does this rigorously with difference-in-differences.)
-- ----------------------------------------------------------------------------
SELECT
    g.borough_name,
    CASE WHEN s.sale_date < '2020-03-01' THEN 'pre_covid' ELSE 'post_covid' END AS period,
    COUNT(*)                 AS num_sales,
    ROUND(AVG(s.sale_price)) AS avg_price
FROM sales s
JOIN geography g ON s.geo_id = g.geo_id
GROUP BY g.borough_name, period
ORDER BY g.borough_name, period;

-- ----------------------------------------------------------------------------
-- 6. Average price by property age bucket - are older or newer buildings
--    pricier? CASE turns a continuous column into labelled buckets.
-- ----------------------------------------------------------------------------
SELECT
    CASE
        WHEN building_age <  10 THEN '0-9 yrs'
        WHEN building_age <  30 THEN '10-29 yrs'
        WHEN building_age <  60 THEN '30-59 yrs'
        WHEN building_age < 100 THEN '60-99 yrs'
        ELSE '100+ yrs'
    END                          AS age_bucket,
    COUNT(*)                     AS num_sales,
    ROUND(AVG(sale_price))       AS avg_price,
    ROUND(AVG(price_per_sqft), 2) AS avg_ppsf
FROM sales
WHERE building_age IS NOT NULL
GROUP BY age_bucket
ORDER BY MIN(building_age);
