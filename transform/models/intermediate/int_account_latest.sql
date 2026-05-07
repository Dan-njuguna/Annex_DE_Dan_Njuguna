SELECT DISTINCT ON (loan_id)
    loan_id,
    snapshot_date,
    balance,
    arrears,
    days_past_due,
    risk_category,
    age_band,
    avg_monthly_income_band,
    total_paid,
    total_due_today,
    account_status_l1,
    account_status_l2
FROM {{ ref('stg_credit_accounts') }}
ORDER BY loan_id, snapshot_date DESC
