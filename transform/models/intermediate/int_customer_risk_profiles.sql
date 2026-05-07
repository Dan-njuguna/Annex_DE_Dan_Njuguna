SELECT
    c.loan_id,
    c.date_of_birth,
    c.gender,
    c.citizenship,
    c.loan_term,
    c.cash_price,
    c.loan_price,
    c.product_name,
    l.balance,
    l.arrears,
    l.days_past_due,
    l.risk_category,
    l.age_band,
    l.avg_monthly_income_band,
    l.snapshot_date AS last_snapshot_date,
    l.total_paid,
    l.total_due_today
FROM {{ ref('stg_customers') }} c
LEFT JOIN {{ ref('int_account_latest') }} l ON c.loan_id = l.loan_id
