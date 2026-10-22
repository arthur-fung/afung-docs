# "Unable to retrieve stored file": what's behind the spike

Analysis date: 2026-10-22. Weeks are Mon–Sun UTC: previous = 10/05–10/11,
current = 10/12–10/18. All SQL is in the [Appendix](#appendix-sql); results are
the CSVs in this folder (`20261020-output-001/002.csv`, `20261022-d1…d5.csv`).

## Conclusion

The error jumped from 1 to 25 a week on the Chrome extension
(`WEB_CHROME - CHROME`), the biggest single cause of that platform's rise in
failures (27 → 80). But most of these failures didn't lose any audio.

The error is logged when a visit ends and the app can't find the **backup
("parallel") recording's** stored file. Across all 42 occurrences on every
platform over both weeks:

| What actually happened | Count | Audio lost? |
|---|---|---|
| The visit was saved with full audio seconds later; only the backup file was missing | 22 | No (likely; see [how sure we are](#how-sure-are-we-about-the-22-saved)) |
| The recording never started properly (mic / start errors), so there was nothing to save | 10 | No audio was captured |
| An empty (0 s) recording had just been discarded | 2 | No |
| **A paused recording was resumed and ended, often after an app crash or reload, and no scribe followed** | **7** | **Probably yes, about 71 min in total** |
| Not enough context | 1 | Unknown |

In short:
1. **The failure metric overstates the problem.** About half of these
   "failures" are cases where the note was saved fine.
2. **The 3.02.1 spike is mostly three accounts** (317470 / 317474 / 317475)
   whose recordings keep failing to start or detect a microphone. The
   stored-file error is a side effect there, not the cause.
3. **The real bug is ending a recording after resuming it following a reload
   or crash** (7 cases). It's on the extension (3.02.0 and 3.02.1) and the web
   app, so it isn't new in 3.02.1.

## 1. Where and when it happens

| Platform | Version | Prev week | Current week |
|---|---|---|---|
| Extension (`WEB_CHROME - CHROME`) | 3.02.1 | — | **22** (12 accounts) |
| Extension | 3.02.0 | 0 | 3 |
| Extension | 3.01.2 | 1 | — |
| Web app (`WEB_APP`, Chrome / Edge) | 7.10.0 | 5 | 6 |
| Web app | 7.09.2 | — | 2 |
| iOS | 3.41.1+2 | — | 3 (1 account, within 23 s) |
| **Total** | | **6** | **36** |

- The web app has had it at a steady 5–6 a week. The jump is on the extension.
- Every row has the same message and `cache: null`; the payload is only the
  message and a stack trace.
- The earlier split (`20261020-web-chrome-failure-reason-split.md`) only
  covered the extension, so it saw 1 → 25.

**Where in the code.** The iOS stack trace is readable:

```
RecordingStateNotifier.stopParallelRecording   (recording_state_notifier.dart:1542)
RecordingStateNotifier._conditionallyStop      (:1448)
RecordingStateNotifier.conditionallyStop       (:1384)
_RecordingScreenState._endVisit                (recording_screen.dart:879)
```

The web stack traces are minified but have the same shape on every build, and
the extension and web app ship the same Dart code, so they're most likely the
same path. Confirming that needs a source map for 3.02.1 (`main.dart.js` line
342496). In the event data, every failure lands in the same second as a
"recording ended" event, which fits a failure at stop time.

## 2. Is 3.02.1 actually worse?

Failures per recordings started on the extension:

| Version | Week | Recordings started | Failures | Rate |
|---|---|---|---|---|
| 3.02.1 | current | 12,172 | 22 | 0.18% |
| 3.02.0 | current | 9,924 | 3 | 0.03% |
| 3.02.0 | prev | 15,436 | 0 | 0% |
| 3.01.2 | prev | 5,208 | 1 | 0.02% |

- On its face 3.02.1 is about 6× worse than 3.02.0, and the difference is
  statistically significant (z ≈ 3.3).
- **12 of the 22 come from three accounts with consecutive IDs** (317470,
  317474, 317475), probably one newly onboarded group, each failing
  repeatedly within minutes. Without them, 3.02.1 is 0.08% (10 failures, 9
  accounts) and the difference from 3.02.0 isn't significant (z ≈ 1.6).

## 3. Was audio lost?

The failure is logged under its own random ID, not the recording's ID, so it
can't be joined to a recording or scribe directly. Instead, each failure was
matched to the same account's scribes and events around the failure time.

### 22 saved: a full-audio scribe right after

For each of these, the same account got a scribe on the same platform
shortly after the failure, and its server audio matched the length the
client recorded (e.g. 234 s vs 233.7 s, 494 s vs 493.3 s):

| Timing of the scribe | Count |
|---|---|
| 6–108 s after the failure (most within 20 s) | 17 |
| About 35 s before the failure | 2 |
| iOS, 9–38 s after, with *more* audio than recorded (425 vs 239 s, 791 vs 235 s) | 3 |

#### How sure are we about the 22 saved?

Fairly, but it isn't proven:
- **The match is by account and time, not by recording ID.** If an account had
  two recordings close together, a failure could be paired with the wrong
  scribe.
- **These 22 weren't checked event by event.** The detailed timeline (D5) only
  covered the other 20.
- **The 3 iOS cases are odd.** The scribe has more audio than the client
  recorded, which may be a separate problem.
- **"Saved" means the note was complete,** not that nothing is wrong. The
  backup file still went missing.

To confirm, run the D5 timeline for these 22 and check that the recording
that ended at the failure is the same one that became the scribe.

### 20 without a scribe right after

The account's event timeline (15 min before to 5 min after each failure)
shows three patterns.

**A. After a failed start: 10, all on 3.02.1, all on accounts 317470 / 317474 /
317475.** The recording failed to start ("Recording failed to start properly.
Please refresh the app and try again.") 15–160 s before the failure, often
with "No microphone detected", "Microphone disconnected" or "Audio length too
short" around it. No audio was being captured, so the stored-file error is a
side effect of stopping a recording that never really started. One of these
(317470, 10/15 14:53) recovered and uploaded 123 s. The root cause is likely
the same microphone problem behind this week's rise in "No microphone
detected".

**B. After an empty recording was discarded: 2, web app.** A 0-second
recording was thrown away as too short 39–239 s before. There was no audio
to lose.

**C. Resumed, ended, then failed, with no scribe: 7.** A recording with real
length was resumed and ended within seconds, then the failure fired, and no
scribe appeared for that recording within 2 hours. Several came right after
the app was killed or relaunched:

| Failure (UTC) | Account | Client | What happened just before | Recording length |
|---|---|---|---|---|
| 10/12 16:03 | 281955 | web 7.09.2 | paused, mic input changed, restarted and ended | 585 s |
| 10/13 15:30 | 109097 | ext 3.02.0 | resumed and ended within 4 s | 2,295 s |
| 10/13 18:31 | 302921 | web 7.10.0 | resumed, ended 80 s later; app killed twice right after | 123 s |
| 10/14 13:04 | 275604 | ext 3.02.1 | resumed and ended within 1 s | 120 s |
| 10/14 16:34 | 114210 | ext 3.02.1 | app killed earlier; resumed and ended within 1 s | 96 s |
| 10/14 18:00 | 269564 | ext 3.02.1 | app relaunched; resumed and ended within 2 s | 960 s |
| 10/16 17:47 | 271062 | ext 3.02.1 | resumed and ended within 1 s | 60 s |

A likely explanation is that the recording's state survives the reload but its
backup audio file doesn't, so ending it fails and no scribe is created. That
needs confirming in the client code.

The remaining one (296833, 3.01.2) had too little context in the window to
classify.

**Caveats for the 20:**
- "No scribe" means none within 2 hours. A recording recovered on a later app
  launch wouldn't show up.
- Recording lengths are the client's own numbers at the end of the recording.
- Whether the dashboard also counts the pattern C recordings as lost scribes
  hasn't been checked.

## Next steps

- **Client team:** check ending a recording that was resumed after a reload
  or crash (pattern C). That's where audio is lost. Also check whether a
  missing backup file should ever block a scribe when the main audio exists.
- **Metric:** stop counting this error as a failure when a full-audio scribe
  follows within a minute, or have the client not send `SCRIBE_FAILED` in
  that case. That removes about half of these.
- **Accounts 317470 / 317474 / 317475:** follow up on their microphone or setup
  (repeated failed starts and "No microphone detected").
- **To confirm:** look up the 7 pattern C recordings in `scribe` with no time
  limit, and run the D5 timeline for the 22 "saved" cases.

## How this was done

1. The dashboard showed the extension's failure rate rising (27 → 80). Its
   failure query was split by version and failure reason for both weeks
   (`20261020-output-001/002.csv`, query Q0). That showed this error going
   from 1 to 25, mostly on 3.02.1.
2. **D1** listed every occurrence on every platform with its full payload and
   checked for a scribe under the failure's ID (none). **D2** pulled all events
   under those IDs and found only the failure itself, which showed the ID
   isn't the recording's.
3. **D3** counted recordings started per version to get rates.
4. **D4** listed each account's scribes from 2 h before to 2 h after each
   failure, with server audio length and client recording length, to see
   whether a full-audio scribe followed.
5. **D5** pulled each account's events from 15 min before to 5 min after the
   20 failures without a matching scribe, to see what the user was doing.
   The first version timed out in Retool; the version in the appendix lists
   the failures and accounts directly.

Times in this doc are server receive times (`created_at`, UTC). Internal
accounts (commure / getathelas / athelas / augmedix) are excluded throughout.

## Appendix: SQL

All queries are read-only and run in Retool on prod StarRocks
(`ops_bronze_normandy_production`).

### Q0. Extension failures by version × failure reason

Current week shown; the previous week is the same with `2026-10-05` /
`2026-10-12`. "Unable to retrieve stored file" matches none of the `LIKE`
patterns, so its category is the raw message.

```sql
WITH filtered_accounts AS (
    SELECT id
    FROM ops_bronze_normandy_production.scribe_accounts
    WHERE LOWER(email) NOT LIKE '%commure%'
      AND LOWER(email) NOT LIKE '%getathelas%'
      AND LOWER(email) NOT LIKE '%athelas%'
      AND LOWER(email) NOT LIKE '%augmedix%'
),
failed_events AS (
    SELECT
        et.scribe_account_id,
        et.uuid,
        et.version,
        get_json_string(et.payload, '$.failure_reason') AS failure_reason
    FROM ops_bronze_normandy_production.scribe_events et
    WHERE et.created_at >= CAST('2026-10-12 00:00:00' AS DATETIME)
      AND et.created_at <  CAST('2026-10-19 00:00:00' AS DATETIME)
      AND et.tag = 'SCRIBE_FAILED'
      AND et.device_type = 'WEB_CHROME'
      AND et.browser_name = 'CHROME'
),
per_scribe AS (
    SELECT
        fe.version,
        CASE
            WHEN fe.failure_reason LIKE '%unable to open database file (code 14)%'
                THEN 'unable to open database file (code 14)'
            WHEN fe.failure_reason LIKE '%database is locked (code 5)%'
                THEN 'database is locked (code 5)'
            WHEN fe.failure_reason LIKE '%out of memory (code 7)%'
                THEN 'out of memory (code 7)'
            WHEN fe.failure_reason LIKE '%disk I/O error (code 10)%'
                THEN 'disk I/O error (code 10)'
            WHEN fe.failure_reason LIKE 'Recording failed: stop() returned null or empty path%'
                THEN 'stop() returned null or empty path'
            ELSE fe.failure_reason
        END AS failure_reason_category,
        fe.scribe_account_id,
        fe.uuid,
        COUNT(*) AS cnt
    FROM failed_events fe
    JOIN filtered_accounts sa ON fe.scribe_account_id = sa.id
    WHERE fe.failure_reason NOT IN (
        'Audio length too short',
        'For the best outputs, we recommend having a recording that is at least 20-30 seconds. Click Resume to continue your Scribe'
    )
    GROUP BY 1, 2, 3, 4
)
SELECT
    version,
    failure_reason_category,
    SUM(cnt) AS cnt,
    COUNT(DISTINCT scribe_account_id) AS accounts,
    COUNT(uuid) AS recordings
FROM per_scribe
GROUP BY 1, 2
ORDER BY cnt DESC;
```

### D1. Every occurrence, with payload and scribe by failure ID → `20261022-d1.csv`

```sql
WITH filtered_accounts AS (
    SELECT id
    FROM ops_bronze_normandy_production.scribe_accounts
    WHERE LOWER(email) NOT LIKE '%commure%'
      AND LOWER(email) NOT LIKE '%getathelas%'
      AND LOWER(email) NOT LIKE '%athelas%'
      AND LOWER(email) NOT LIKE '%augmedix%'
),
failures AS (
    SELECT
        et.created_at,
        et.timestamp,
        et.scribe_account_id,
        et.uuid,
        et.device_type,
        et.browser_name,
        et.version,
        get_json_string(et.payload, '$.failure_reason') AS failure_reason,
        substr(CAST(et.payload AS STRING), 1, 1500)     AS payload
    FROM ops_bronze_normandy_production.scribe_events et
    WHERE et.created_at >= CAST('2026-10-05 00:00:00' AS DATETIME)
      AND et.created_at <  CAST('2026-10-19 00:00:00' AS DATETIME)
      AND et.tag = 'SCRIBE_FAILED'
      AND et.device_type IN ('MOBILE_IOS', 'MOBILE_ANDROID', 'WEB_CHROME', 'WEB_APP')
      AND get_json_string(et.payload, '$.failure_reason') LIKE '%retrieve stored file%'
),
scribes AS (
    SELECT uuid, id AS scribe_id, created_at AS scribe_created_at, audio_length_in_seconds
    FROM ops_bronze_normandy_production.scribe
    WHERE created_at >= CAST('2026-10-04 00:00:00' AS DATETIME)
      AND created_at <  CAST('2026-10-23 00:00:00' AS DATETIME)
)
SELECT
    CASE WHEN f.created_at < CAST('2026-10-12 00:00:00' AS DATETIME) THEN 'prev' ELSE 'current' END AS week_bucket,
    f.created_at,
    f.timestamp,
    f.scribe_account_id,
    f.uuid,
    f.device_type,
    f.browser_name,
    f.version,
    f.failure_reason,
    s.scribe_id,
    s.scribe_created_at,
    s.audio_length_in_seconds,
    f.payload
FROM failures f
JOIN filtered_accounts sa ON f.scribe_account_id = sa.id
LEFT JOIN scribes s ON s.uuid = f.uuid
ORDER BY f.created_at;
```

### D2. All events under the failure IDs → `20261022-d2.csv`

```sql
WITH failed_uuids AS (
    SELECT DISTINCT et.uuid
    FROM ops_bronze_normandy_production.scribe_events et
    WHERE et.created_at >= CAST('2026-10-05 00:00:00' AS DATETIME)
      AND et.created_at <  CAST('2026-10-19 00:00:00' AS DATETIME)
      AND et.tag = 'SCRIBE_FAILED'
      AND et.device_type IN ('MOBILE_IOS', 'MOBILE_ANDROID', 'WEB_CHROME', 'WEB_APP')
      AND get_json_string(et.payload, '$.failure_reason') LIKE '%retrieve stored file%'
      AND et.uuid IS NOT NULL
)
SELECT
    et.uuid,
    et.timestamp,
    et.created_at,
    et.tag,
    et.action,
    et.device_type,
    et.browser_name,
    et.version,
    et.scribe_id,
    et.scribe_account_id,
    substr(CAST(et.payload AS STRING), 1, 400) AS payload
FROM ops_bronze_normandy_production.scribe_events et
JOIN failed_uuids fu ON fu.uuid = et.uuid
WHERE et.created_at >= CAST('2026-10-04 00:00:00' AS DATETIME)
  AND et.created_at <  CAST('2026-10-23 00:00:00' AS DATETIME)
  AND et.tag NOT IN ('BATCH_SCRIBE_EVENTS_CONTROLLER', 'SCRIBE_AUDIO_CACHE_HEALTH_V3')
ORDER BY et.uuid, et.timestamp, et.created_at
LIMIT 5000;
```

### D3. Recordings started per version → `20261022-d3.csv`

Counts recording starts, which is a bit broader than the dashboard's
denominator (the `scribe` table), but fine for comparing versions.

```sql
SELECT
    CASE WHEN et.created_at < CAST('2026-10-12 00:00:00' AS DATETIME) THEN 'prev' ELSE 'current' END AS week_bucket,
    et.version,
    COUNT(DISTINCT et.uuid) AS recordings_started
FROM ops_bronze_normandy_production.scribe_events et
JOIN ops_bronze_normandy_production.scribe_accounts sa
  ON sa.id = et.scribe_account_id
 AND LOWER(sa.email) NOT LIKE '%commure%'
 AND LOWER(sa.email) NOT LIKE '%getathelas%'
 AND LOWER(sa.email) NOT LIKE '%athelas%'
 AND LOWER(sa.email) NOT LIKE '%augmedix%'
WHERE et.created_at >= CAST('2026-10-05 00:00:00' AS DATETIME)
  AND et.created_at <  CAST('2026-10-19 00:00:00' AS DATETIME)
  AND et.action IN ('RECORDING_STARTED', 'PARALLEL_RECORDING_STARTED')
  AND et.device_type = 'WEB_CHROME'
  AND et.browser_name = 'CHROME'
GROUP BY 1, 2
ORDER BY 1, 3 DESC;
```

### D4. Account's scribes within 2 h of each failure → `20261022-d4.csv`

```sql
WITH failures AS (
    SELECT
        et.uuid              AS failed_uuid,
        et.scribe_account_id,
        et.created_at        AS failed_at,
        et.device_type,
        et.version
    FROM ops_bronze_normandy_production.scribe_events et
    WHERE et.created_at >= CAST('2026-10-05 00:00:00' AS DATETIME)
      AND et.created_at <  CAST('2026-10-19 00:00:00' AS DATETIME)
      AND et.tag = 'SCRIBE_FAILED'
      AND et.device_type IN ('MOBILE_IOS', 'MOBILE_ANDROID', 'WEB_CHROME', 'WEB_APP')
      AND get_json_string(et.payload, '$.failure_reason') LIKE '%retrieve stored file%'
),
scribes AS (
    SELECT id, uuid, scribe_account_id, created_at, device_type, version, audio_length_in_seconds
    FROM ops_bronze_normandy_production.scribe
    WHERE created_at >= CAST('2026-10-04 20:00:00' AS DATETIME)
      AND created_at <  CAST('2026-10-19 02:00:00' AS DATETIME)
),
ended AS (
    SELECT uuid, MAX(CAST(NULLIF(get_json_string(payload, '$.recording_length'), 'null') AS DECIMAL(20,6))) AS recording_length
    FROM ops_bronze_normandy_production.scribe_events
    WHERE created_at >= CAST('2026-10-04 20:00:00' AS DATETIME)
      AND created_at <  CAST('2026-10-19 02:00:00' AS DATETIME)
      AND action = 'PARALLEL_RECORDING_ENDED'
      AND scribe_account_id IN (SELECT scribe_account_id FROM failures)
    GROUP BY uuid
)
SELECT
    f.failed_uuid,
    f.scribe_account_id,
    f.failed_at,
    f.device_type,
    f.version,
    s.id          AS scribe_id,
    s.uuid        AS scribe_uuid,
    s.created_at  AS scribe_created_at,
    timestampdiff(SECOND, f.failed_at, s.created_at) AS secs_after_failure,
    s.device_type AS scribe_device_type,
    s.audio_length_in_seconds,
    e.recording_length
FROM failures f
LEFT JOIN scribes s
       ON s.scribe_account_id = f.scribe_account_id
      AND s.created_at >= date_sub(f.failed_at, INTERVAL 2 HOUR)
      AND s.created_at <  date_add(f.failed_at, INTERVAL 2 HOUR)
LEFT JOIN ended e ON e.uuid = s.uuid
ORDER BY f.failed_at, s.created_at;
```

### D5. Account's events around the 20 failures without a scribe → `20261022-d5.csv`

The first version, which found the failures by scanning payloads and used a
±15 min window, timed out. This version lists the 20 failures and 13 accounts
directly, limits to the failure days, and uses 15 min before to 5 min after.

```sql
-- 20 failures, 13 accounts
WITH failures AS (
    SELECT '47c4ebfd-19f4-49f2-94fb-d9675c2bd973' AS failed_uuid, 296833 AS scribe_account_id, CAST('2026-10-05 21:29:29.812' AS DATETIME) AS failed_at
    UNION ALL
    SELECT 'e3cb3991-fe8f-403d-9c2e-4a8954d90292' AS failed_uuid, 276092 AS scribe_account_id, CAST('2026-10-06 22:36:29.466' AS DATETIME) AS failed_at
    UNION ALL
    SELECT '02d4486d-e86c-4ec7-9198-ec6717d8c25c' AS failed_uuid, 281955 AS scribe_account_id, CAST('2026-10-12 16:03:37.789' AS DATETIME) AS failed_at
    UNION ALL
    SELECT '78c5b315-6fa2-4238-bd3e-69b6369b486d' AS failed_uuid, 109097 AS scribe_account_id, CAST('2026-10-13 15:30:48.467' AS DATETIME) AS failed_at
    UNION ALL
    SELECT '46f1db0a-2965-40fa-b8d9-c4e34383523d' AS failed_uuid, 302921 AS scribe_account_id, CAST('2026-10-13 18:31:27.734' AS DATETIME) AS failed_at
    UNION ALL
    SELECT '28491d34-dc23-4b32-8447-f9683b1f3980' AS failed_uuid, 275604 AS scribe_account_id, CAST('2026-10-14 13:04:12.406' AS DATETIME) AS failed_at
    UNION ALL
    SELECT '9d3f1729-3ceb-4332-90fc-9bfa1ee7ebb4' AS failed_uuid, 317475 AS scribe_account_id, CAST('2026-10-14 15:44:31.472' AS DATETIME) AS failed_at
    UNION ALL
    SELECT '0586c30a-69c2-482f-b126-ecf3eae22daa' AS failed_uuid, 317475 AS scribe_account_id, CAST('2026-10-14 16:13:24.808' AS DATETIME) AS failed_at
    UNION ALL
    SELECT 'b3f2bd53-50b1-4220-962f-83e76a31bec7' AS failed_uuid, 114210 AS scribe_account_id, CAST('2026-10-14 16:34:49.537' AS DATETIME) AS failed_at
    UNION ALL
    SELECT '0ded52a5-6845-4182-8dd5-a09ad32c2c59' AS failed_uuid, 317475 AS scribe_account_id, CAST('2026-10-14 16:47:30.564' AS DATETIME) AS failed_at
    UNION ALL
    SELECT '677232d4-b68a-4785-9693-bfa8d6d0f330' AS failed_uuid, 317475 AS scribe_account_id, CAST('2026-10-14 17:44:29.610' AS DATETIME) AS failed_at
    UNION ALL
    SELECT 'f88f45ff-0f3f-4685-8376-a462e38ca801' AS failed_uuid, 269564 AS scribe_account_id, CAST('2026-10-14 18:00:40.978' AS DATETIME) AS failed_at
    UNION ALL
    SELECT 'dc2a5979-9d53-4b30-8141-4cbcea61cdef' AS failed_uuid, 317470 AS scribe_account_id, CAST('2026-10-14 18:03:00.895' AS DATETIME) AS failed_at
    UNION ALL
    SELECT '80ce80e4-ba5d-467a-8af3-8ce8c6058ed3' AS failed_uuid, 317475 AS scribe_account_id, CAST('2026-10-14 18:04:31.351' AS DATETIME) AS failed_at
    UNION ALL
    SELECT 'a31ffbdf-3b4f-4f95-9077-9ac685cf3758' AS failed_uuid, 273880 AS scribe_account_id, CAST('2026-10-14 20:46:04.486' AS DATETIME) AS failed_at
    UNION ALL
    SELECT '05f0b4a9-8218-4868-b612-074248f5ef76' AS failed_uuid, 317470 AS scribe_account_id, CAST('2026-10-15 14:53:51.914' AS DATETIME) AS failed_at
    UNION ALL
    SELECT 'f771ab53-7791-420c-a2ac-8ff2805ec4d7' AS failed_uuid, 317470 AS scribe_account_id, CAST('2026-10-15 16:47:11.501' AS DATETIME) AS failed_at
    UNION ALL
    SELECT '953995ac-5cd9-43c3-975f-29a5eee35deb' AS failed_uuid, 317470 AS scribe_account_id, CAST('2026-10-15 16:58:26.980' AS DATETIME) AS failed_at
    UNION ALL
    SELECT '340822d7-c9ca-439c-9931-8841e9208c29' AS failed_uuid, 317474 AS scribe_account_id, CAST('2026-10-15 19:15:07.016' AS DATETIME) AS failed_at
    UNION ALL
    SELECT '07bc3958-1e8a-454e-b6f9-53cfb3c2f25d' AS failed_uuid, 271062 AS scribe_account_id, CAST('2026-10-16 17:47:52.450' AS DATETIME) AS failed_at
),
events AS (
    SELECT scribe_account_id, uuid, created_at, timestamp, tag, action, device_type, version, scribe_id,
           get_json_string(payload, '$.recording_length') AS recording_length,
           substr(CAST(payload AS STRING), 1, 200)        AS payload
    FROM ops_bronze_normandy_production.scribe_events
    WHERE created_at >= CAST('2026-10-05 00:00:00' AS DATETIME)
      AND created_at <  CAST('2026-10-17 00:00:00' AS DATETIME)
      AND date(created_at) IN ('2026-10-05', '2026-10-06', '2026-10-12', '2026-10-13', '2026-10-14', '2026-10-15', '2026-10-16')
      AND scribe_account_id IN (109097, 114210, 269564, 271062, 273880, 275604, 276092, 281955, 296833, 302921, 317470, 317474, 317475)
      AND tag NOT IN ('BATCH_SCRIBE_EVENTS_CONTROLLER', 'SCRIBE_AUDIO_CACHE_HEALTH_V3', 'SCRIBE_WORKFLOW_STEP_TIMING')
)
SELECT
    f.failed_uuid,
    f.failed_at,
    timestampdiff(SECOND, f.failed_at, e.created_at) AS secs_from_failure,
    e.*
FROM failures f
JOIN events e
  ON e.scribe_account_id = f.scribe_account_id
 AND e.created_at >= date_sub(f.failed_at, INTERVAL 15 MINUTE)
 AND e.created_at <  date_add(f.failed_at, INTERVAL 5 MINUTE)
ORDER BY f.failed_at, e.created_at
LIMIT 5000;
```
