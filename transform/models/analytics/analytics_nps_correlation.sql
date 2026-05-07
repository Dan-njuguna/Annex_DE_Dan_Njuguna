SELECT
    risk_category,
    COUNT(*) AS response_count,
    ROUND(AVG(nps_score)::NUMERIC, 2) AS mean_nps,
    ROUND((PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY nps_score))::NUMERIC, 2) AS median_nps,
    MIN(nps_score) AS min_nps,
    MAX(nps_score) AS max_nps
FROM {{ ref('int_nps_enriched') }}
WHERE nps_score IS NOT NULL
GROUP BY risk_category
ORDER BY mean_nps DESC
