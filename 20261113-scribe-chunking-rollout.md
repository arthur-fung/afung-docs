# scribe_chunking rollout

Source: Normandy prod read replica, Thursday 2026-11-12 UTC and the three Thursdays before it.

## 1. Rollout by site, week by week

A site is counted if one of its accounts created a scribe that day on iOS, Android, Chrome extension or web app. Grants count only if created before the end of that day.

| Day | Active sites | All accounts on | Partial | None | Any on | Accounts on |
|---|---|---|---|---|---|---|
| 2026-10-22 | 566 | 381 (**67.3%**) | 86 | 99 | 82.5% | 2,991 / 5,622 (53.2%) |
| 2026-10-29 | 572 | 421 (**73.6%**) | 53 | 98 | 82.9% | 3,337 / 5,763 (57.9%) |
| 2026-11-05 | 566 | 421 (**74.4%**) | 52 | 93 | 83.6% | 3,405 / 5,940 (57.3%) |
| 2026-11-12 | 574 | 469 (**81.7%**) | 79 | 26 | 95.5% | 4,906 / 6,069 (80.8%) |

- Most of the rollout happened in the last week: sites with no account on fell from 93 to 26.
- Depends on each grant row's `created_at`. Grants deleted later are missed, and prod has no exclusions on this flag so they are ignored.

## 2. When the flags were granted

User-level grants per week (`scribe_account_feature_flags.created_at`, weeks start Monday).

| Week of | `scribe_chunking` | `scribe_chunking_autorollout` |
|---|---|---|
| 2026-09-07 | 8,590 | |
| 2026-09-14 | 3,783 | |
| 2026-09-21 | 1 | |
| 2026-09-28 | 7 | |
| 2026-10-05 | 692 | |
| 2026-10-12 | 1,127 | |
| 2026-10-19 | 2,973 | |
| 2026-10-26 | 1,078 | 648 |
| 2026-11-02 | 336 | 1,205 |
| 2026-11-09 (to 11-13) | 2,976 | 3,227 |

- `scribe_chunking_autorollout` is a gate, not a grant: chunking needs `scribe_chunking` on, and with autorollout on it is used only after a GCS probe succeeds. It cannot speed up the rollout.
- Autorollout grants started the week of 2026-10-26; the jump in `scribe_chunking` grants in the week of 11-09 matches the jump in section 1.

## 3. Share of scribes by client (current grants)

Uses today's grants for every day, so past days are overstated. Use section 1 for trends.

Scribes created on 2026-11-12 whose account resolves `scribe_chunking` to on.

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

### By site (section 1; one file per date, change the two dates)

```sql
-- Sites using scribe on the day, and how many have scribe_chunking on
-- as of the end of that day (grants counted only if created before then).
-- Clients: iOS, Android, Chrome extension, web app.
WITH ff AS (
  SELECT id FROM feature_flags WHERE name = 'scribe_chunking' AND is_active IS TRUE
),
s AS (
  SELECT DISTINCT scribe_account_id
  FROM scribe
  WHERE created_at >= '2026-11-12' AND created_at < '2026-11-13'
    AND device_type IN ('MOBILE_IOS', 'MOBILE_ANDROID', 'WEB_CHROME', 'WEB_APP')
),
acc AS (
  SELECT s.scribe_account_id, sa.provider_id, p.site_id
  FROM s
  JOIN scribe_accounts sa ON sa.id = s.scribe_account_id
  JOIN providers p ON p.id = sa.provider_id
  WHERE p.site_id IS NOT NULL
),
ug AS (
  SELECT DISTINCT x.scribe_account_id
  FROM scribe_account_feature_flags x
  JOIN ff ON ff.id = x.feature_flag_id
  WHERE x.created_at < '2026-11-13'
    AND x.scribe_account_id IN (SELECT scribe_account_id FROM acc)
),
sg AS (
  SELECT DISTINCT acc.scribe_account_id
  FROM acc
  JOIN scribe_site_or_facility_level_feature_flags t
    ON t.site_id = acc.site_id AND t.is_disabled IS FALSE AND t.created_at < '2026-11-13'
  JOIN ff ON ff.id = t.feature_flag_id
),
fg AS (
  SELECT DISTINCT acc.scribe_account_id
  FROM acc
  JOIN provider_facility_mappings m ON m.provider_id = acc.provider_id
  JOIN scribe_site_or_facility_level_feature_flags t
    ON t.facility_id = m.facility_id AND t.is_disabled IS FALSE AND t.created_at < '2026-11-13'
  JOIN ff ON ff.id = t.feature_flag_id
),
per_site AS (
  SELECT acc.site_id,
         count(DISTINCT acc.scribe_account_id) AS accts,
         count(DISTINCT acc.scribe_account_id) FILTER (
           WHERE ug.scribe_account_id IS NOT NULL
              OR sg.scribe_account_id IS NOT NULL
              OR fg.scribe_account_id IS NOT NULL) AS on_accts,
         bool_or(sg.scribe_account_id IS NOT NULL) AS has_site_grant
  FROM acc
  LEFT JOIN ug USING (scribe_account_id)
  LEFT JOIN sg USING (scribe_account_id)
  LEFT JOIN fg USING (scribe_account_id)
  GROUP BY acc.site_id
)
SELECT '2026-11-12' AS day,
       count(*) AS sites,
       count(*) FILTER (WHERE on_accts = accts) AS sites_all_on,
       count(*) FILTER (WHERE on_accts > 0 AND on_accts < accts) AS sites_partial,
       count(*) FILTER (WHERE on_accts = 0) AS sites_none,
       count(*) FILTER (WHERE has_site_grant) AS sites_with_site_grant,
       round(100.0 * count(*) FILTER (WHERE on_accts = accts) / count(*), 1) AS pct_sites_all_on,
       round(100.0 * count(*) FILTER (WHERE on_accts > 0) / count(*), 1) AS pct_sites_any_on,
       sum(accts) AS accounts,
       sum(on_accts) AS accounts_on
FROM per_site;
```

### Weekly grants (section 2)

```sql
SELECT date_trunc('week', x.created_at)::date AS week_start,
       ff.name,
       count(*) AS user_grants
FROM scribe_account_feature_flags x
JOIN feature_flags ff ON ff.id = x.feature_flag_id
WHERE ff.name IN ('scribe_chunking', 'scribe_chunking_autorollout')
  AND x.created_at >= now() - interval '10 weeks'
GROUP BY 1, 2
ORDER BY 1, 2
LIMIT 50;
```

### Scribes by client (section 3)

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
