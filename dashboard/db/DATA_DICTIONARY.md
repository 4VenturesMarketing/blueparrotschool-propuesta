# BPS Marketing Data Dictionary

Built: `2026-08-31T12:32:02`  
Database: `dashboard/db/bps.db`

## Trust layers

| Layer | Meaning | Tables |
|-------|---------|--------|
| **gold** | Business truth for decisions | `fact_wc_order`, `fact_meta_wc_match`, `kpi_period_channel` (WC), Google Ads WC UTM orders |
| **silver** | Platform metrics (correct in their system) | Meta/Google Ads/GA4/GSC facts |
| **bronze** | Staging / incomplete coverage | Older Meta months missing, Ads before 2026-04 |

## Google Ads: purchase vs lead

Account `1064441284` (login MCC `5963150101`):

| Class | conversion_action category | Primary actions |
|-------|----------------------------|-----------------|
| **purchase** | `PURCHASE` | Compra (GA4 purchase) |
| **lead** | `SUBMIT_LEAD_FORM` | form_submit, submit_lead_form, Lead form - Submit |

**Do not sum** purchase + lead into a single “CAC pedido”.  
Use purchase for ROAS/CPA compra; lead for CPL; WC `utm_medium=cpc` for business CAC.

## Meta: which order count?

| Metric | Use? |
|--------|------|
| Meta×WC match (`fact_meta_wc_match`) | **YES — canonical Meta→pedido** |
| Checkout UTM Meta Ads | NO (subregistro) |
| Meta pixel purchases | Campaign optimization only |

## Academic periods

| ID | Range |
|----|-------|
| sy-2024-25 | 2024-09-01 → 2025-08-31 |
| sy-2025-26 | 2025-09-01 → 2026-08-30 |
| sy-2026-27 | 2026-09-01 → 2027-08-31 |

## Rebuild

```bash
python3 scripts/build_bps_db.py
```

Requires local JSON under `dashboard/data/` (WC, Meta, matches, GA4, GSC, google-ads-conversions-raw).
