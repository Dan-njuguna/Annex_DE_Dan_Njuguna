SELECT
    snapshot_date,
    total_accounts,
    ROUND(delinquent_count::NUMERIC / NULLIF(total_accounts, 0) * 100, 2) AS delinquency_rate_pct,
    ROUND(arrears_count::NUMERIC / NULLIF(total_accounts, 0) * 100, 2) AS par_rate_pct,
    ROUND(critical_count::NUMERIC / NULLIF(total_accounts, 0) * 100, 2) AS loss_rate_pct,
    ROUND((total_paid::NUMERIC / NULLIF(total_due, 0) * 100)::NUMERIC, 2) AS collection_rate_pct,
    ROUND(low_count::NUMERIC / NULLIF(total_accounts, 0) * 100, 1) AS low_risk_pct,
    ROUND(medium_count::NUMERIC / NULLIF(total_accounts, 0) * 100, 1) AS medium_risk_pct,
    ROUND(high_count::NUMERIC / NULLIF(total_accounts, 0) * 100, 1) AS high_risk_pct,
    ROUND(critical_count::NUMERIC / NULLIF(total_accounts, 0) * 100, 1) AS critical_risk_pct,
    ROUND(total_balance::NUMERIC, 2) AS total_balance
FROM {{ ref('int_portfolio_daily_metrics') }}
ORDER BY snapshot_date
