-- Gravity Fitness verified membership pricing and receipt/photo support release.
-- Historical memberships retain their own plan/price/duration snapshots.
UPDATE membership_plans
SET code = CASE id
        WHEN 'plan-basic-monthly' THEN 'one-month'
        WHEN 'plan-pro-monthly' THEN 'three-months'
        WHEN 'plan-elite-monthly' THEN 'one-year'
        ELSE code END,
    name = CASE id
        WHEN 'plan-basic-monthly' THEN '1 Month'
        WHEN 'plan-pro-monthly' THEN '3 Months'
        WHEN 'plan-elite-monthly' THEN '1 Year'
        ELSE name END,
    description = NULL,
    price_paise = CASE id
        WHEN 'plan-basic-monthly' THEN 120000
        WHEN 'plan-pro-monthly' THEN 300000
        WHEN 'plan-elite-monthly' THEN 1000000
        ELSE price_paise END,
    currency = 'INR',
    duration_months = CASE id
        WHEN 'plan-basic-monthly' THEN 1
        WHEN 'plan-pro-monthly' THEN 3
        WHEN 'plan-elite-monthly' THEN 12
        ELSE duration_months END,
    status = 'active',
    sort_order = CASE id
        WHEN 'plan-basic-monthly' THEN 10
        WHEN 'plan-pro-monthly' THEN 20
        WHEN 'plan-elite-monthly' THEN 30
        ELSE sort_order END,
    updated_at = strftime('%s','now')
WHERE id IN ('plan-basic-monthly','plan-pro-monthly','plan-elite-monthly');
