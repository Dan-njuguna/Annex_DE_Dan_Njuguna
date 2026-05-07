SELECT
    snapshot_date,
    COUNT(*) AS total_accounts,
    COUNT(*) FILTER (WHERE days_past_due > 0) AS delinquent_count,
    COUNT(*) FILTER (WHERE arrears > 0) AS arrears_count,
    COUNT(*) FILTER (WHERE risk_category = 'Critical') AS critical_count,
    COUNT(*) FILTER (WHERE risk_category = 'High') AS high_count,
    COUNT(*) FILTER (WHERE risk_category = 'Medium') AS medium_count,
    COUNT(*) FILTER (WHERE risk_category = 'Low') AS low_count,
    SUM(balance) AS total_balance,
    SUM(total_paid) AS total_paid,
    SUM(total_due_today) AS total_due
FROM {{ ref('stg_credit_accounts') }}
GROUP BY snapshot_date
