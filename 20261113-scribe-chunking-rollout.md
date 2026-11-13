# scribe_chunking rollout, 2026-11-12 (UTC)

Source: Normandy prod read replica. Share of scribes created on 2026-11-12 whose account resolves `scribe_chunking` to on.

| Client | Scribes | On | Off | Accounts on / off |
|---|---|---|---|---|
| iOS | 44,000 | 95.9% | 4.1% (1,783) | 3,707 / 153 |
| Android | 4,148 | 97.3% | 2.7% (112) | 376 / 14 |
| Chrome extension | 5,225 | 99.6% | 0.4% (21) | 491 / 4 |
| Web app | 19,062 | 99.6% | 0.4% (83) | 1,844 / 13 |
| **Total of the four** | 72,433 | **97.2%** | 2.8% (1,999) | |

| Other client | Scribes | On | Off |
|---|---|---|---|
| PatientKeeper | 5,572 | 71.8% | 28.2% (1,573) |
| Augmedix | 9,166 | 1.1% | 98.9% (9,065) |
| Auto-run | 611 | 0.8% | 99.2% (606) |
| Internal | 171 | 56.1% | 43.9% (75, no account) |

## Notes

- Measures flag eligibility (account-level `scribe_chunking` resolves on), not whether each recording was chunked.
- `scribe_chunking_autorollout` is a separate client gate (GCS probe); it has about 5k user grants.
- Exclusions are omitted: prod has none on `scribe_chunking`.
- Account counts are per device type, so an account on two clients appears in both rows.
- One day only, not a trend.

## SQL

```sql
WITH ff AS (
  SELECT id FROM feature_flags WHERE name = 'scribe_chunking' AND is_active IS TRUE
),
s AS (
  SELECT scribe_account_id, device_type, count(*) AS scribes
  FROM scribe
  WHERE created_at >= '2026-11-12' AND created_at < '2026-11-13'
  GROUP BY scribe_account_id, device_type
),
acc AS (
  SELECT DISTINCT s.scribe_account_id, sa.provider_id, p.site_id
  FROM s
  LEFT JOIN scribe_accounts sa ON sa.id = s.scribe_account_id
  LEFT JOIN providers p ON p.id = sa.provider_id
),
ug AS (
  SELECT DISTINCT x.scribe_account_id
  FROM scribe_account_feature_flags x
  JOIN ff ON ff.id = x.feature_flag_id
  WHERE x.scribe_account_id IN (SELECT scribe_account_id FROM acc)
),
sg AS (
  SELECT DISTINCT acc.scribe_account_id
  FROM acc
  JOIN scribe_site_or_facility_level_feature_flags t
    ON t.site_id = acc.site_id AND t.is_disabled IS FALSE
  JOIN ff ON ff.id = t.feature_flag_id
),
fg AS (
  SELECT DISTINCT acc.scribe_account_id
  FROM acc
  JOIN provider_facility_mappings m ON m.provider_id = acc.provider_id
  JOIN scribe_site_or_facility_level_feature_flags t
    ON t.facility_id = m.facility_id AND t.is_disabled IS FALSE
  JOIN ff ON ff.id = t.feature_flag_id
),
r AS (
  SELECT s.*,
    (ug.scribe_account_id IS NOT NULL
     OR sg.scribe_account_id IS NOT NULL
     OR fg.scribe_account_id IS NOT NULL) AS chunking_on
  FROM s
  LEFT JOIN ug USING (scribe_account_id)
  LEFT JOIN sg USING (scribe_account_id)
  LEFT JOIN fg USING (scribe_account_id)
)
SELECT device_type, chunking_on,
       sum(scribes) AS scribes,
       count(DISTINCT scribe_account_id) AS accounts,
       round(100.0 * sum(scribes) / sum(sum(scribes)) OVER (PARTITION BY device_type), 1) AS pct_of_platform_scribes
FROM r
GROUP BY device_type, chunking_on
ORDER BY device_type, chunking_on DESC
LIMIT 50;
```
