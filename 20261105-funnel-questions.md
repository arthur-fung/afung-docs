# Questions the funnel must answer

2026-11-05. The starting point for the funnel logging diagrams and the dashboard: every view should answer one of these.

Each question lists:
- **Answered by:** the outcome number(s) or flag in the PRD (`docs/20261102-reliability-funnel-prd.md` §6.3–6.4);
- **Evidence:** the events behind it (details in `docs/20261105-recording-journey-event-index.md`);
- **Today:** ✅ answerable now / 🟡 partly / ❌ needs new logging, with the tasks (T1–T34 in the event index, §5) that close it.

All counts are recordings attempted in the Mon–Sun UTC week, shown as a rate with the raw count.

### Top line

**Of all recording attempts this week, how many became a note the provider got, and is that getting better?** (reliability rate, week over week, by platform and version)
- **Answered by:** outcomes 1–2 ÷ (all attempts − 8 expected exits − 16 telemetry gaps)
- **Evidence:** every outcome below
- **Today:** 🟡 Approximated from today's events (legacy path); full once the new events ship. T30.

### Phase 1: Start

**How many attempts never started, and why?** Blocked by pre-checks (permission, paywall, no template…) or the user cancelled.
- **Answered by:** outcome 8 (expected exit), split by reason
- **Evidence:** `ATTEMPTED` → `PREFLIGHT_BLOCKED{reason}`
- **Today:** ❌ Only low battery / storage is logged; every other blocked start leaves no trace. T1, T2.

**How many failed to start or resume, and why?**
- **Answered by:** outcome 9 (start failed, incl. resume failed)
- **Evidence:** `START_FAILED{error_code, on_resume}`
- **Today:** 🟡 `SCRIBE_FAILED / ON_START` and `START_RECORDING_ERROR` exist, but the reasons are free text or hard-coded, and some failures go to Sentry only. T5.

### Phase 2: Recording

**How many failed mid-recording, and why?**
- **Answered by:** outcome 10 (recording failed)
- **Evidence:** `RECORDING_FAILED{stage, error_code}`
- **Today:** 🟡 `MID_RECORDING_ERROR` and `SCRIBE_FAILED` exist, but early errors are mislabelled and save failures are partly Sentry only. T5, T9.

**How many were killed unexpectedly, at which stage, and how many were recovered afterwards? Did the provider still get a note, and was it complete?**
- **Answered by:** outcome 14 (killed, never handed off); flags `ever_killed`, `recovered_after_kill`, `audio_discrepancy`
- **Evidence:** `TERMINATED_UNEXPECTEDLY{last_phase}` at the next launch; Sentry watchdog kill tagged with the recording id; `SCRIBE_CREATED` afterwards; app vs. server audio length
- **Today:** 🟡 `APP_KILLED_DETECTED` only catches kills after the mic starts, with no stage or reason, and crashes aren't tied to recordings. T11, T12, T20.

**How many were paused and never resumed, by the user vs. auto-paused after a kill?**
- **Answered by:** outcome 12 (paused by user) vs. 14 (auto-paused after a kill)
- **Evidence:** `PARALLEL_RECORDING_PAUSED{reason}`; `auto_paused` cache state
- **Today:** ❌ Every pause looks the same, and killed recordings are restored as plain "paused". T6, T12.

**Was all the audio saved and uploaded?**
- **Answered by:** flags `partial_submit`, `audio_discrepancy`; chunks created vs. uploaded per recording
- **Evidence:** `CHUNK_ADDED` (with chunk_index, bytes), `CHUNK_UPLOADED`, `SESSION_SUMMARY`, `FINALIZE_PARTIAL`; app vs. server audio length
- **Today:** 🟡 Chunking only (`SESSION_SUMMARY`, `FINALIZE_*`); `CHUNK_ADDED` carries no chunk number or size, and single-file recordings have no equivalent. T8, T17.

### Phase 3: End and upload

**How many uploads failed or got stuck, at which step, and how many were recovered later?**
- **Answered by:** outcome 11 (upload stuck); flag `recovered_after_stuck` (today's recovery rate)
- **Evidence:** `FINALIZE_FAILED{stage}`, `TRIGGER_FAILED`, `AUDIO_CACHE_ERROR{reason}`, later `SCRIBE_CREATED`
- **Today:** 🟡 Chunking finalize events are good, but a cache moving to error is silent, and recoveries by the background retry or the recovery pop-up don't report a scribe. T16, T17.

### Lost

**How many recordings are lost, and which kind?** Vanished on the device, the device not seen since, or a telemetry gap (we lost the logs, not the recording).
- **Answered by:** outcomes 17 (vanished on device), 18 (device not seen since), 16 (telemetry gap)
- **Evidence:** `install_id` (did the phone come back?), the cache-health list (was the recording still on it?), `TERMINATED_UNEXPECTEDLY`, event sequence gaps
- **Today:** 🟡 Lost scribes can be counted, but without a phone id the account is the stand-in, so a provider who switched devices looks "vanished". T11, T18, T19.

### Phase 4: Backend

**How many are incomplete, and why?** (no mic? hardware problem?)
- **Answered by:** outcomes 4 (not enough info) and 5 (no speech), split by ≥30 s of near-silent audio
- **Evidence:** `scribe.task_status = INCOMPLETE`, `error_message`, audio length
- **Today:** ✅ From Postgres, as in the weekly report.

**How many failed or got stuck in the backend?**
- **Answered by:** outcomes 6 (backend failed), 7 (backend stuck)
- **Evidence:** status-change events, a stuck event per scribe, a failure event instead of a hard delete
- **Today:** 🟡 A failed audio combine deletes the scribe with no event, so it looks lost; transcription failure has no event. T25–T28.

**How many notes were ready but never delivered or used?**
- **Answered by:** outcome 2 (note ready, not delivered) vs. 1 (delivered)
- **Evidence:** `task_status` SYNCED / COPIED / MDS, `NOTE_COPIED`, a future "note viewed" event
- **Today:** 🟡 Delivery results exist only in `task_status`, which later updates can overwrite; there's no "note viewed", so outcome 2 is inflated. T25, T28.

### Across all stages

**Which crashes cost us recordings?** Ranked by recordings lost, not crash count.
- **Answered by:** the crash band: per crash issue, sessions affected, recordings affected, recordings lost
- **Evidence:** crashes tagged with `recording_id` and `app_session_id`
- **Today:** ❌ Crashlytics and Sentry crashes have no recording id. T20, T32.

**Is it concentrated? Which platform, app version, account or site drives each number?**
- **Answered by:** the dimensions stored on every outcome (platform, browser, version, account, site)
- **Evidence:** fields on every event and the scribe row
- **Today:** ✅ Already how the weekly report finds drivers (e.g. site 2471, iOS 3.41.1, account 314787).
