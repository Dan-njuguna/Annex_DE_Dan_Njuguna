SELECT
    n.loan_id,
    n.submitted_at,
    n.nps_score,
    n.main_reason,
    n.happy_device,
    n.happy_service,
    n.payment_delay,
    l.risk_category,
    l.age_band,
    l.days_past_due,
    l.arrears
FROM {{ ref('stg_nps_responses') }} n
LEFT JOIN {{ ref('int_account_latest') }} l ON n.loan_id = l.loan_id
