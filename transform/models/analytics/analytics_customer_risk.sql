SELECT
    loan_id,
    date_of_birth,
    gender,
    citizenship,
    loan_term,
    cash_price,
    balance,
    arrears,
    days_past_due,
    risk_category,
    age_band,
    avg_monthly_income_band,
    last_snapshot_date,
    CASE
        WHEN risk_category IN ('Critical', 'High') THEN 'watchlist'
        WHEN days_past_due > 0 THEN 'monitor'
        ELSE 'healthy'
    END AS portfolio_segment
FROM {{ ref('int_customer_risk_profiles') }}
