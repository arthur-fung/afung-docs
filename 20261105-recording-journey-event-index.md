# Recording journey: event index (scribe_events + Mixpanel)

2026-11-05. An index of the events a recording sends today, from the tap through to delivery. Use it to look up a stage, then go to the code.

- **Read from code, not data:** scribe-mobile `c87c9fe7a`, normandy `030f82a7ca`.
- **Stages** match the funnel PRD (`docs/20261102-reliability-funnel-prd.md`): C0 Attempted → C1 Mic live → C2 Recording & saving → C3 Ended → C4a All audio uploaded → C4b Handed off → B1 Audio received → B2 Transcribed → B3 Note ready → B4 Delivered.
- **Main path:** mobile chunking. Native (non-chunking) and web differences are noted per stage.

## How to read this

- **`scribe_events` row** = `tag` + `action`.
  - When the app passes no action, it's stored as `Open`. These show as "(no action)" below.
  - Backend journey events all use tag `SCRIBE_JOURNEY`, with the `NORMANDY_*` name in **action**.
- **`uuid` column, as used in this file:**
  - **rec:** the recording uuid. Chunking is a plain dashed v4; non-chunking is `scribe_audio_workflows_<hex>`.
  - **random:** the app made up a v4 because none was passed. It can't be joined to anything.
  - **`''`:** empty string.
  - **none:** not set.
- **`scribe_id`** is null on every app event before C4b, unless noted.
- **Ordering:** `created_at` is when the server received the event, not when it happened.
  - The app writes events to local SQLite and uploads them every 30 s, in batches of up to 100 (`lib/services/tracking/batching_event_tracker_service.dart`).
  - The client's time is in `timestamp`.
  - There's no sequence number and no session id on scribe_events.
- **Every app event carries:** `tag, action, payload, device_type, operating_system, browser_name, version, scribe_account_id, scribe_id, timestamp, uuid, client_event_id` (`lib/services/tracking/event_tracker_service.dart:234-284`).
- **PHI flag:** ⚠️ means the payload contains `patient_name` or `patient_email`.
- **Paths:**
  - app paths are under `scribe-mobile/lib/src/features/` unless they start with `lib/`;
  - backend paths are under `normandy/app/api/v1/`.
- **Mixpanel** runs on live (release, prod) builds only. Super properties: `app_version`, `device_type`, `device_id` (the install id).

---

## Stage map, at a glance

| Stage | First scribe event | Proof the stage finished | Mixpanel |
|---|---|---|---|
| C0 Attempted | `RESOURCE_MONITORING / RECORDING_INITIATED` (random uuid) | `SCRIBE_JOURNEY / RECORDING_INITIALIZED` (rec) | `start_recording_tapped` |
| C1 Mic live | `SCRIBE_JOURNEY / PARALLEL_RECORDING_STARTED` (sent *before* the mic starts) | `RESOURCE_MONITORING / RECORDING_IN_PROGRESS` | `chunking_recording_started` (unreliable) |
| C2 Recording & saving | `SCRIBE_AUDIO_CACHE_SYNC_V2 / CHUNK_ADDED` (~30 s in) | `SCRIBE_AUDIO_CACHE_SYNC_V2 / CHUNK_UPLOADED` per chunk | pause / resume taps |
| C3 Ended | `SCRIBE_JOURNEY / PARALLEL_RECORDING_ENDED` | `SCRIBE_AUDIO_CACHE_SYNC_V2 / AUDIO_CACHE_STOPPED` | `end_visit_tapped`, `chunking_recording_stopped` |
| C4a Uploaded | `SCRIBE_CHUNKING / FINALIZE_*` | `FINALIZE_SUCCESS` / `FINALIZE_PARTIAL` | none |
| C4b Handed off | `SCRIBE_CHUNKING / SCRIBE_CREATED` (has scribe_id) | `AUDIO_CACHE_DELETED` | none |
| B1 Audio received | `SCRIBE_JOURNEY / NORMANDY_WORKFLOWS_SCRIBE_JOURNEY_START` | `NORMANDY_WORKFLOWS_TRIGGERED_ERRANDS_FOR_ALL_TRANSCRIPTIONS` | none |
| B2 Transcribed | `SCRIBE_JOURNEY / TRANSCRIPTION_CALLBACK_START` | `NORMANDY_WORKFLOWS_TRANSCRIPTIONS_AND_OCRS_COMPLETED`; `scribe.audio_length_in_seconds` | none |
| B3 Note ready | `SCRIBE_JOURNEY / POST_NOTE_GENERATION_CALLBACK_START` | `NORMANDY_WORKFLOWS_ALL_TASKS_COMPLETED`; `scribe.task_status`, `processing_completed_timestamp` | `scribe_card_tapped` (closest to "viewed") |
| B4 Delivered | `EHR_SYNC_PRESSED` / `NOTE_COPIED` | `scribe.task_status` SYNCED / COPIED (**no event**) | `scribe_copy_note`, `scribe_sync_to_ehr` |

---

## 1. scribe_events by stage, in firing order

### C0: Attempted (tap → pre-checks → recording created)

Most blocked starts send **nothing**.

| # | Tag / action | uuid | Important metadata | Where | Notes |
|---|---|---|---|---|---|
| 0.1 | *(another recording already open → STOP)* | | | `visits/providers/start_visit_controller.dart:71` | No event |
| 0.2 | `RESOURCE_MONITORING / RECORDING_INITIATED` | random | memory_info, disk_space_info, image_cache_* | `start_visit_controller.dart:75`; `record/services/resource_monitoring_service.dart:82-192` | **Repeats every 30 s** until the next monitor start or stop. Nothing stops it on a blocked path. |
| 0.3 | *(duplicate tab, web → STOP)* | | | `start_visit_controller.dart:91` | No event |
| 0.4 | `LOW_WARNING_DIALOG_SHOWN` (no action) | random | is_low_battery, is_low_storage, proceeded_anyway | `lib/src/services/low_warning_service.dart:171-180` | Only when battery < 10% or storage < 500 MB, at most once a day. Not on web. |
| 0.5 | *(mic permission denied → STOP)* | | | `start_visit_controller.dart:101`; `visits/providers/audio_permission_provider.dart:56-95` | No event. iOS does request permission (record_ios). |
| 0.6 | *(rate limit → paywall → STOP)* | | | `start_visit_controller.dart:105` | No event |
| 0.7 | *(no template → STOP)* | | | `start_visit_controller.dart:111` | No event |
| 0.8 | `SCRIBE_CHUNKING / RECORDING_MODE_SELECTED` | random | mode_selected (chunking / native), reason, platform, patch_version | `start_visit_controller.dart:324`; `record/services/chunking_analytics.dart:336` | |
| 0.9 | `SCRIBE_JOURNEY / RECORDING_INITIALIZED` | rec | ⚠️ patient_name, template_id | `record/providers/chunking_recording_state_notifier.dart:383-390` | First event with the recording uuid |
| 0.10 | `SCRIBE_AUDIO_CACHE_SYNC_V2 / AUDIO_CACHE_START` | rec | scribeCache{state = **paused**, duration, …}, fileParts[] | `record/data/cache_repository.dart:348-355` | Means "cache row created". Also fires when the row already exists. |
| 0.11 | `SCRIBE_FEATURE_OPTION_SYNC / FEATURE_OPTION_INSERTED` | rec | optionName, optionValueAsString (carry-forward, patient_age, patient_gender) | `cache_repository.dart:2379-2452` | Several rows |
| — | *any start exception* → `SCRIBE_FAILED / ON_START` | rec | recording_length = 0, failure_reason, stack_trace, ⚠️ patient_name | `chunking_recording_state_notifier.dart:1013-1059` | Also goes to Sentry. The user sees "Couldn't start recording", which logs no event. |

**Native:**
- uuid is `scribe_audio_workflows_…`;
- `CARRY_FORWARD_PREFERENCE` always fires;
- `PRIOR_RECORDING_START` is sent twice, the second time with uuid `''`;
- `FILE_ADDED` fires in initialize, **before the mic starts**.

**Web:** the duplicate-tab check is active and the storage warning is skipped.

### C1: Mic live

| # | Tag / action | uuid | Important metadata | Where | Notes |
|---|---|---|---|---|---|
| 1.1 | `SCRIBE_JOURNEY / PARALLEL_RECORDING_STARTED` | rec | ⚠️ patient_name, template_id | `chunking_recording_state_notifier.dart:740-747` | Sent **before** the mic starts. **Re-sent on every resume.** |
| 1.2 | `SCRIBE_MONITORING / PRIOR_RECORDING_START` | rec | device diagnostics, app_version, normandy_device_type | `lib/services/diagnostics.dart:251-304` | Re-sent on resume |
| 1.3 | *(mic start fails)* → Sentry `deviceRetryException`, then `SCRIBE_FAILED / ON_START` | rec | effectiveDeviceId, triedDeviceIds | `chunking_recording_state_notifier.dart:798-813` | Mobile makes one attempt; web loops over devices |
| 1.4 | *(cache paused → started; uuid saved for kill detection)* | | | `:935-955` | **No event.** A kill before this point is never detected. |
| 1.5 | `RESOURCE_MONITORING / RECORDING_IN_PROGRESS` | rec | memory_info, disk_space_info | `:993-998` | Sent once, then every 30 s. Stops the 0.2 timer. **First reliable sign the mic is running.** |
| — | `SCRIBE_JOURNEY / START_RECORDING_ERROR` | rec | error (**hard-coded text**), stack_trace (always null) | `main/views/main_screen.dart:287-301` | Only when the recorder errors within 5 s with the "failed to start properly" message. Other early errors are logged as `MID_RECORDING_ERROR`. |

### C2: Recording & saving

Recurring events while recording:

| # | Tag / action | uuid | Important metadata | Where | Cadence |
|---|---|---|---|---|---|
| 2.1 | `RESOURCE_MONITORING / RECORDING_IN_PROGRESS` | rec | memory, disk | as 1.5 | every 30 s; stops on pause |
| 2.2 | `SCRIBE_MONITORING / DURING_RECORDING` | rec | diagnostics_<platform> | `diagnostics.dart:298`; timer `record/providers/recording_state_notifier.dart:1208` | every 5 min |
| 2.3 | `SCRIBE_AUDIO_CACHE_SYNC_V2 / CHUNK_ADDED` | rec | filePartId **only** | `cache_repository.dart:1397-1400` | per chunk (30 s). **First proof audio was saved.** |
| 2.4 | `SCRIBE_CHUNKING / FLUSHED` | rec | chunk_index, bytes, packet_count, is_final | `chunking_analytics.dart:58` | per chunk, right after 2.3 |
| 2.5 | `SCRIBE_AUDIO_CACHE_SYNC_V2 / CHUNK_UPLOADED` | rec | filePartId, chunkFilename | `record/providers/chunk_upload_provider.dart:532` | per chunk, async (this is "upload success") |
| 2.6 | `SCRIBE_CHUNKING / FLUSH_EMPTY` | rec or `''` | reason (timer_already_flushed / buffer_empty / combine_empty), chunk_index | `chunking_analytics.dart:77` | per empty flush |
| 2.7 | `SCRIBE_CHUNKING / CONSECUTIVE_FLUSH_EMPTIES` | rec | consecutive_count, elapsed_seconds, recording_state, tab_inactive, tab_frozen | `chunking_analytics.dart:101` | at the 3rd empty in a row. **Triggers the no-audio auto-pause** (see 2.15). |
| 2.8 | `SCRIBE_CHUNKING / FLUSH_DEFERRED` | rec or `''` | reason, tab_inactive, tab_frozen | `chunking_analytics.dart:128` | per deferral |

Upload problems:

| # | Tag / action | uuid | Important metadata | Where |
|---|---|---|---|---|
| 2.9 | `SCRIBE_AUDIO_CACHE_SYNC_V2 / CHUNK_UPLOAD_RETRY_BACKOFF` | **none** | chunkFilename, retryCount, delayMs | `chunk_upload_provider.dart:1061` |
| 2.10 | `SCRIBE_AUDIO_CACHE_SYNC_V2 / CHUNK_UPLOAD_FAILED` | rec | filePartId, error | `chunk_upload_provider.dart:1021` (skipped for auth and offline failures) |
| 2.11 | `SCRIBE_AUDIO_CACHE_SYNC_V2 / CHUNK_UPLOAD_SHED` | rec | outstanding | `chunk_upload_provider.dart:1080` |
| 2.12 | `SCRIBE_AUDIO_CACHE_SYNC_V2 / FILE_PART_INSERT_FAILED`, `AUDIO_CACHE_UPDATE_FAILED` | rec | error, attempts, elapsed_ms | `cache_repository.dart:1343`, `:586` |

Pause, resume and interruptions:

| # | Tag / action | uuid | Important metadata | Where | Notes |
|---|---|---|---|---|---|
| 2.13 | User pause: `RESOURCE_MONITORING / PARALLEL_RECORDING_PAUSED` → `SCRIBE_JOURNEY / PARALLEL_RECORDING_PAUSED` → final `CHUNK_ADDED` + `FLUSHED` → `SCRIBE_AUDIO_CACHE_SYNC_V2 / AUDIO_CACHE_PAUSED` | rec | PAUSED: recording_length, template_id, amplitude stats. CACHE_PAUSED: cache JSON. | `chunking_recording_state_notifier.dart:1644-1694`; `cache_repository.dart:560` | **No reason field.** User, auto, call and interruption pauses all look the same. |
| 2.14 | Resume: `RESOURCE_MONITORING / PARALLEL_RECORDING_RESUMED` → re-runs `start()`, so 1.1, 1.2 and 1.5 fire again | rec | | `recording_state_notifier.dart:1625`; `chunking_recording_state_notifier.dart:741`, `:994` | There's no `SCRIBE_JOURNEY / PARALLEL_RECORDING_RESUMED` |
| 2.15 | No-audio auto-pause | | | `chunking_recording_state_notifier.dart:1215-1254` | No own event: 2.7 followed by 2.13 |
| 2.16 | Android phone call | | | `recording_state_notifier.dart:855-875` | No own event: looks like 2.13 |
| 2.17 | iOS audio interruption: no event at the start; at the end `SCRIBE_JOURNEY / PHONE_CALL_<type>` | rec | none | `recording_state_notifier.dart:1000-1008` | Only if it was recording before |
| 2.18 | `SCRIBE_JOURNEY / MIC_INPUT_CHANGE` (+ `MIC_CHANGE_RESCHEDULE*`, `MIC_CHANGE_SKIPPED_STOP_IN_PROGRESS`) | rec | device_id | `chunking_recording_state_notifier.dart:336`; `recording_state_notifier.dart:392-581` | |
| 2.19 | `SCRIBE_JOURNEY / PAUSE_RECORDING`, `RESUME_RECORDING` | rec | | `chunking_recording_state_notifier.dart:1589`, `:1617` | In-place pause; no UI caller found |

Warnings, lifecycle and errors:

| # | Tag / action | uuid | Important metadata | Where | Notes |
|---|---|---|---|---|---|
| 2.20 | `SCRIBE_JOURNEY / LOW_AUDIO_DETECTED` | ⚠️ the uuid of `cacheProvider.first`, which may not be the current recording | volume_threshold | `record/views/recording_screen.dart:1159` | after 10 s of low volume, repeating |
| 2.21 | `SCRIBE_JOURNEY / MUTED_RECORDING` | rec | error | `recording_state_notifier.dart:509` | |
| 2.22 | `IOS_LOW_MEMORY_WARNING / MEMORY_PRESSURE` | none | sequence, memory, trigger, app_lifecycle | `lib/src/services/ios_low_memory_diagnostic.dart:216` | iOS only; also goes to Sentry (SCRIBE-MOBILE-QD6) |
| 2.23 | `SCRIBE_JOURNEY / LOW_MEMORY_DURING_RECORDING` | rec | ⚠️ patient_name, session_id, recording_state, phys_footprint_mb, device_free_ram_mb, navigation_stack | `ios_low_memory_diagnostic.dart:290-310` | Only if a recording is active when 2.22 fires |
| 2.24 | `APP_LIFECYCLE / BACKGROUND_RECORDING`, `FOREGROUND_RECORDING`, `DETACHED_APP` | rec | platform, timestamp | `main/providers/app_lifecycle_provider.dart:736-780` | Per lifecycle change while recording |
| 2.25 | `SCRIBE_JOURNEY / MID_RECORDING_ERROR` | rec | error, stack_trace | `main/views/main_screen.dart:322-331` | "Disconnected microphone" dialog |
| 2.26 | `SCRIBE_JOURNEY / RECORDER_OWNER_REPLACED`, `RECORDER_OWNER_LIVE_DETACHED` | rec | log | `recording_state_notifier.dart:2483` | Also sent to Sentry |
| 2.27 | `SCRIBE_FAILED` (no action), auto-stop at 3 h | rec | recording_length, failure_reason, ⚠️ patient_name | `recording_state_notifier.dart:2171-2190` | `autoStop()` has no caller found, and `stop()` is empty on chunking, so this may never run (G19) |

**Web:**
- `WEB_LIFECYCLE / TAB_FROZEN` and `TAB_UNFROZEN` (`chunking_recording_state_notifier.dart:2521`);
- `SCRIBE_JOURNEY / EXTENSION_MINIMIZED_DURING_RECORDING`;
- background and foreground events come from blur and focus;
- no phone-call or iOS memory events.

**Native:** no per-chunk events. On each pause or stop it sends `FILE_UPDATED` (`cache_repository.dart:1445`) instead of `CHUNK_ADDED`.

### C2 → next launch: the app was killed

| # | Tag / action | uuid | Important metadata | Where | Notes |
|---|---|---|---|---|---|
| K.1 | `APP_LIFECYCLE / APP_KILLED_DETECTED` | rec (saved uuid) | last_app_state, last_active_timestamp, time_since_last_active_minutes, last_session_id, current_session_id, was_recording_when_killed (always true) | `app_lifecycle_provider.dart:328-363`; conditions `lib/src/services/lifecycle/app_lifecycle_service.dart:134-186` | See the caveats below the table |
| K.2 | `APP_LIFECYCLE / DURATION_NORMALIZED_AFTER_KILL` | rec | previous/normalized_duration_seconds, kill_timestamp, recording_started_at | `app_lifecycle_provider.dart:547` | **Never fires for chunking** (returns early at :443) |
| K.3 | `APP_LIFECYCLE / ORPHANED_AUDIO_FILE_RECOVERED` (+ `FILE_ADDED`) | rec | filename, file_size_bytes | `cache_repository.dart:1938` | Native only |
| K.4 | `APP_LIFECYCLE / APP_RESUMED_AFTER_BREAK` | rec | time_since_last_active_minutes, session_continuity | `app_lifecycle_provider.dart:375` | Effectively never fires |
| — | *(cache started → paused on launch)* | | | `cache_repository.dart:1975`; `lib/src/services/sqlite_migration_service.dart:270` | **No event** when it succeeds |

Caveats on K.1:
- **Delivery:** sent durably, so `created_at` is the delivery time and it can be sent twice.
- **Not the kill time:** `last_active_timestamp` is device-local with no timezone, from the last lifecycle change.
- **Possible session-key collision:** `last_session_id` may be the current session's id because of a shared prefs key (inferred from code).
- **Detection window:** a kill is only detected after uuid save (1.4). Before that, nothing.

Web: plain `trackEvent` with `kill_uuid`; `last_app_state` is hard-coded to `active`.

### C3: Ended

| # | Tag / action | uuid | Important metadata | Where | Notes |
|---|---|---|---|---|---|
| 3.1 | `SCRIBE_JOURNEY / PARALLEL_RECORDING_ENDED` | rec | **recording_length** (seconds, from the app timer), template_id, amplitude stats | `chunking_recording_state_notifier.dart:1762-1767` | Used by the audio discrepancy metric |
| 3.2 | Final `CHUNK_ADDED` + `FLUSHED` (is_final = true), or `FLUSH_EMPTY` (is_final) | rec | | as in C2 | |
| 3.3 | `SCRIBE_CHUNKING / SESSION_SUMMARY` | rec | duration_seconds, chunks_created, chunks_uploaded, chunks_pending | `chunking_analytics.dart:148` | Chunking only |
| 3.4 | `SCRIBE_AUDIO_CACHE_SYNC_V2 / AUDIO_CACHE_STOPPED` | rec | cache JSON | `cache_repository.dart:560` | Normal stop |
| 3.5 | `RESOURCE_MONITORING / RECORDING_ENDED` | rec | memory, disk | `recording_state_notifier.dart:1461` | The only "RECORDING_ENDED" |
| 3a | **Too short** (< 20 s): `SCRIBE_FAILED_TOO_SHORT` (no action) → `ORPHANED_UPLOAD_RECOVERY / SHORT_RECORDING_SESSION_DELETED` → `AUDIO_CACHE_DELETED` → **also** `SCRIBE_FAILED` | rec | recording_length, failure_reason; SCRIBE_FAILED has ⚠️ patient_name | `recording_state_notifier.dart:1428-1480` | Logs both TOO_SHORT and FAILED. **No `PARALLEL_RECORDING_ENDED`** (G19). |
| 3b | **Zero chunks** (#6363): `SHORT_RECORDING_SESSION_DELETED` → `AUDIO_CACHE_DELETED` | rec | | `chunking_recording_state_notifier.dart:1858-1891` | `NoAudioChunksException` goes to **Sentry only**. No discard event. |
| 3c | User delete: `FILE_DELETED` → `AUDIO_CACHE_DELETED` | rec | file_path, file_size; cache JSON | `cache_repository.dart:1716`, `:1751` | No "user deleted" reason |
| 3d | `PAUSED_CACHE_DELETE / DELETE_STARTED`, `DELETE_CACHE_SUCCESS`, `DELETE_CACHE_ERROR`, `DELETE_COMPLETED` | rec or none | counts | `record/widgets/paused_caches_dialog.dart:366-484` | From the paused-caches dialog |
| — | `SCRIBE_FAILED` (no action), stop error | rec | failure_reason, stack_trace, ⚠️ patient_name | `recording_state_notifier.dart:1499-1510` | |

**Native** order: `PARALLEL_RECORDING_ENDED` → pause pair → `FILE_UPDATED` → `AUDIO_CACHE_PAUSED` → `AUDIO_CACHE_READY_TO_UPLOAD` → `RECORDING_ENDED`. It has no `SESSION_SUMMARY`.

### C4a: All audio uploaded (chunking finalize, up to 15 s wait)

| # | Tag / action | uuid | Important metadata | Where | When |
|---|---|---|---|---|---|
| 4.1 | `SCRIBE_CHUNKING / WAIT_TIMEOUT` → `FINALIZE_TIMEOUT` | rec | pending_count, uploading_count, timeout_ms; pending_at_stop | `chunking_analytics.dart:168`, `:272` | Wait over 15 s |
| 4.2 | `SCRIBE_CHUNKING / FINALIZE_SKIPPED` | rec | reason = offline, wait_ms | `chunking_analytics.dart:263` | Offline. The cache moves to error with **no event**. |
| 4.3 | `SCRIBE_AUDIO_CACHE_SYNC_V2 / MANIFEST_FAILED` | rec | error_class | `chunking_analytics.dart:281` | Just before 4.5 with stage = manifest |
| 4.4 | `SCRIBE_AUDIO_CACHE_SYNC_V2 / TRIGGER_FAILED` | rec | error_class, force_combine | `chunking_analytics.dart:294` | Each failed trigger; the first failure retries with force_combine |
| 4.5 | `SCRIBE_CHUNKING / FINALIZE_FAILED` | rec | **stage** (claim / signed_urls / chunks / manifest / trigger), error_class, wait_ms | `chunking_analytics.dart:248`; stages in `chunk_upload_provider.dart:1307-1730` | |
| 4.6 | `SCRIBE_CHUNKING / FINALIZE_PARTIAL` + `SCRIBE_AUDIO_CACHE_SYNC_V2 / PARTIAL_SUBMIT` | rec | uploaded_count, failed_count | `chunking_analytics.dart:216`, `:234` | Trigger succeeded but some chunks failed. The cache moves to error with no event. |
| 4.7 | `SCRIBE_CHUNKING / FINALIZE_SUCCESS` | rec | wait_ms, manifest_ms, trigger_ms, force_combine, chunks_uploaded, chunks_failed, chunks_pending_at_stop | `chunking_analytics.dart:191` | **Fires after** the C4b events |

**Native (full file):** `AUDIO_CACHE_UPLOADING`, then the `UPLOAD_ERROR_HANDLER_VALIDATE_AUDIO_*` checks (`record/services/upload_error_handler_service.dart`), then trigger, then `AUDIO_CACHE_UPLOAD_ENDED`, `FILE_DELETED` and `AUDIO_CACHE_DELETED`.
- On error: `SCRIBE_UPLOAD_ERROR / UPLOAD_ERROR` | `RETRY_UPLOAD_ERROR` | `UPLOAD_UNAUTHORIZED` | `FORBIDDEN` | `UNPROCESSABLE_ENTITY` | `RATE_LIMIT` | `RECORDING_INVALID` | `SERVER_ERROR`. Payload: is_retry, error, audio_cache, processing_time. Then `AUDIO_CACHE_ERROR` (`record/providers/cache_upload_provider.dart:132-144`).

### C4b: Handed off

| # | Tag / action | uuid | Important metadata | Where |
|---|---|---|---|---|
| 5.1 | `SCRIBE_CHUNKING / SCRIBE_CREATED` | rec | **scribe_id in the column**, template_ids | `chunking_analytics.dart:307`; `chunk_upload_provider.dart:1875` |
| 5.2 | `SCRIBE_AUDIO_CACHE_SYNC_V2 / AUDIO_CACHE_UPLOAD_ENDED` | rec | cache JSON | `chunk_upload_provider.dart:1883` |
| 5.3 | `FILE_DELETED` (usually absent on chunking) → `AUDIO_CACHE_DELETED` | rec | cache JSON | `cache_repository.dart:1751` |
| 5.4 | `SCRIBE_CHUNKING / FINALIZE_SUCCESS` | rec | see 4.7 | |

- **Native:** sends **no SCRIBE_CREATED** to scribe_events (only Segment "Scribe Created", `record/data/recording_repository.dart:190`). The recording ↔ scribe link comes from the scribe row's `uuid`.
- **Never emitted:** `GENERATING_SCRIBE` and `SCRIBE_GENERATED` are defined but never sent.

### Recovery, cleanup and cache health (any time, often the next launch)

| Tag / action | uuid | Important metadata | Where | Cadence |
|---|---|---|---|---|
| `SCRIBE_AUDIO_CACHE_HEALTH_V3` (no action) | none | total_caches, errored_scribes, all_caches[] (each with scribeCache.state, isChunking) | `main/providers/health_check_provider.dart:72-86` | 5 s after load, then every 30 min. No paused count field; derive it from all_caches[].state. Used by the stuck-in-cache metric. |
| `CHUNK_UPLOAD_RECOVERY / SCAN_STARTED`, `ATTEMPTED`, `FAILED`, `RECOVERED` | ATTEMPTED / FAILED = rec | caches_scanned, file_parts_count, error_class, recovered_count | `record/services/chunk_upload_recovery_service.dart:34-65` | On launch. Each attempt re-runs finalize, so C4a/C4b events fire again. Skips paused caches. |
| `BACKGROUND_CHUNK_RETRY / RUN_STARTED`, `CACHE_ATTEMPTED`, `CACHE_SUCCESS`, `CACHE_FAILED`, `RUN_COMPLETED`, `RUN_SKIPPED` | CACHE_* = rec | chunks_uploaded, error_class, rss_*_mb | `record/services/background_upload_retry_service.dart:375-494` | Mobile, every 2 h. **Success sends no SCRIBE_CREATED or AUDIO_CACHE_DELETED.** |
| `ORPHANED_UPLOAD_RECOVERY / FETCHED`, `POPUP_SHOWN`, `RECOVER_STARTED`, `RECOVERED` (has scribe_id), `RECOVER_FAILED`, `DISCARDED`, … | **none** (upload_session_id in payload) | upload_session_id, error_class | `record/services/orphan_recovery_analytics.dart:17-203` | Server-side orphan popup |
| `SCRIBE_CACHE_CLEANUP / DELETE` | none | counts plus uuid lists (old_uuids, ended_uuids, empty_uuids, …) | `lib/src/services/sqlite_migration_service.dart:213-234` | On launch, if anything was deleted. Used by lost-scribes exclusions. |
| `SCRIBE_CACHE_CLEANUP` (no action) | none | days_old, result | `cache_repository.dart:1138` | DB init; entries older than 30 days |
| `SCRIBE_CACHE_FILE_DELETED`, `SCRIBE_CACHE_FILE_DELETE_ERROR` | none (cache_uuid in payload) | file_path, file_size | `cache_repository.dart:1227`, `:1246` | During cleanup |
| `SCRIBE_CACHE_PAUSED_NORMALIZATION_ERROR / SET_PAUSED`, `SCRIBE_CACHE_ERROR_STATE_ERROR / SET_ERROR` | none | error | `sqlite_migration_service.dart:284`, `:302` | On failure only |
| `SCRIBE_AUDIO_CACHE_CLEARED` | none | | `cache_repository.dart:2042` | Logout |

### B1–B3: Backend (normandy)

- **Tag:** always `SCRIBE_JOURNEY`. These are written via `track_scribe_event_from_object` (`app/utils/tracking.py:61`), which sets scribe_id, account, device, version and uuid = `scribe.uuid`.
- **Payload:** none, except the spellcheck END events.
- **Dropped:** `SCRIBE_JOURNEY` events with no uuid are dropped (`tracking.py:121`).

| # | Stage | Action | Where | Notes |
|---|---|---|---|---|
| 6.1 | B1 | `NORMANDY_WORKFLOWS_SCRIBE_JOURNEY_START` | `scribe/workflows/controllers.py:806` | uuid set, **scribe_id = None** |
| 6.2 | B1 | `NORMANDY_WORKFLOWS_DB_CHECKS_PASSED` | `scribe/workflows/controllers.py:956` | scribe_id = None |
| 6.3 | B1 | `NORMANDY_WORKFLOWS_AUDIO_UPLOAD_START` → `NORMANDY_WORKLFOWS_AUDIO_UPLOAD_COMPLETED` (typo) | `scribe/workflows/services.py:1916`, `:1930` | Full-file upload path |
| 6.4 | B1 | `NORMANDY_WORKFLOWS_COMBINE_AUDIO_CHUNKS_START` → `_COMPLETED` | `scribe/workflows/services.py:1954`, `:2056` | Chunked path. **The async combine sends no COMPLETED.** If the combine fails, `cleanup_scribe_data` hard-deletes the scribe with **no event**. |
| 6.5 | B1 | `NORMANDY_WORKFLOWS_UPLOAD_MANIFEST_START` / `_COMPLETED` | `scribe/combine/services.py:335`, `:349` | Multi-file combine |
| 6.6 | B1 | `NORMANDY_WORKFLOWS_TRIGGERED_ERRANDS_FOR_ALL_TRANSCRIPTIONS` | `scribe/workflows/services.py:911`, `:962` | Transcription dispatched. `task_status` → IN_PROGRESS (`:2064`). |
| 6.7 | B2 | `TRANSCRIPTION_CALLBACK_START` → `TRANSCRIPTION_CALLBACK_END` | `workflows/controllers.py:252`, `:448` | Sets `scribe.audio_length_in_seconds` (`scribe/workflows/services.py:5946`, called from `workflows/controllers.py:382`) |
| 6.8 | B2 | `MEDICAL_SPELLCHECK_START/END`, `ENGLISH_SPELLCHECK_START/END` | `workflows/services.py:1426-1669` | END payload: elapsed_ms, correction_count, … |
| 6.9 | B2 | `NORMANDY_WORKFLOWS_TRANSCRIPTIONS_AND_OCRS_COMPLETED` | `workflows/services.py:287` | All transcripts done. **No event when transcription fails** (only task_status = ERROR). |
| 6.10 | B2→B3 | `NORMANDY_WORKFLOWS_TRIGGERED_ERRANDS_FOR_ALL_TASKS` (or `NORMANDY_WORKFLOWS_SCRIBE_COMPLETED_NO_TASKS`) | `workflows/services.py:426`, `:409` | Note generation dispatched |
| 6.11 | B3 | `POST_NOTE_GENERATION_CALLBACK_START` → (`POST_NOTE_GENERATION_ADDITIONAL_TASKS_START/END`, `NOTE_LEVEL_CORRECTIONS_START/END`) → `POST_NOTE_GENERATION_CALLBACK_END` | `workflows/controllers.py:735-1327`; `workflows/services.py:1214`, `:1251` | |
| 6.12 | B3 | `NORMANDY_WORKFLOWS_ALL_TASKS_COMPLETED` | `scribe/workflows/services.py:4583` | **Can repeat** (fires on each qualifying status update). `task_status` → COMPLETED / ERROR (`:4490-4575`); `processing_completed_timestamp` set (`:4480`). |
| — | ops | tag `SCRIBE_STUCK_AUTO_BACKFILL` / action `TRIGGERED` | `openai/alerts.py:741` | Stuck for more than 15 min. Payload: workflow_id. |

- **Legacy flow** (`openai/controllers.py`): the same idea, but the actions drop `WORKFLOWS_`: `NORMANDY_SCRIBE_JOURNEY_START`, `NORMANDY_FILE_UPLOAD_*`, `NORMANDY_CALLBACK_FOR_NEW_TRANSCRIPTION`, `NORMANDY_CLINICAL_DOCUMENTATION_GENERATED`, …
- **Not written by the backend at all:** `SCRIBE_FAILED` and `SCRIBE_STUCK`. There's also no status-history table or event.

### B4: Delivered

| # | Tag / action | uuid / id | Important metadata | Where | Notes |
|---|---|---|---|---|---|
| 7.1 | `SCRIBE_JOURNEY / SCRIBE_AUTO_SYNC_STARTED` → `SCRIBE_AUTO_SYNC_TRIGGERED` (backend) | scribe | | `normandy/app/colossus/scribe_integrations/ehr_sync/auto_sync.py:142`, `:180` | Auto-sync |
| 7.2 | `SCRIBE_JOURNEY / SCRIBE_AUTO_SYNC_ENDPOINT_CALLED` (backend) | scribe | | `scribe/workflows/controllers.py:3829` | |
| 7.3 | `EHR_SYNC_PRESSED` (no action) | scribe_id column | scribe_id | `lib/services/ehr_sync_utils.dart:25` | App, manual sync |
| 7.4 | `EHR_SYNC_FAILED` (no action) | scribe_id column | error, stack, workflow_id | `scribe/views/note_page/note_page_button_bar.dart:367` | App |
| 7.5 | `NOTE_COPIED` (no action) | scribe_id column, **no uuid** | scribe_id, workflow_id, workflow_task_id | `note_page_button_bar.dart:566`; `scribe/views/widgets/text_output.dart:154`, `:203` | App |
| 7.6 | `SEND_TO_MDS_SUCCESS` / `SEND_TO_MDS_FAILED` | scribe_id in payload | workflow_id, error | `scribe/use_cases/send_to_mds_use_case.dart:121-164` | App |
| 7.7 | `ACCESSIBILITY_SERVICE_SYNC_SUCCESS` / `_FAILED` | scribe_id column | | `lib/src/diva/services/diva_sync_service.dart:78`, `:293` | Android accessibility sync |
| 7.8 | `WORKFLOW_TAB_VIEWED` (no action); `SCRIBE_JOURNEY / AFTER_VISIT_SUMMARY_VIEWED` | none; scribe uuid | tab_info, template_name, scribe_id | `scribe/views/details/scribe_tab_bar.dart:427`; `scribe/views/widgets/email_page.dart:118` | Closest to "note viewed" |
| 7.9 | `SCRIBE_JOURNEY / EMAIL_COPIED`, `EMAIL_SENT`, `EMAIL_SEND_DIALOG_OPENED` | scribe uuid | ⚠️ patient_email, patient_name | `email_page.dart:141-236` | |
| — | **SYNCED / SYNC_ERROR / COPIED** | | | `task_status` only: `scribe/scribe_ehr_services.py:142-147`; `scribe/services.py:10393`; SYNCING `normandy/app/colossus/scribe_integrations/ehr_sync/sync_record.py:341` | **No scribe_events row** |

---

## 2. Mixpanel by stage, in user order

All events go through `TrackingService.trackUserEvent` (`tracking/services/tracking_services.dart:160`), on live builds only.
- **Button events:** come from the button's `trackingTag` (`lib/src/ui/buttons/base_parent_button.dart:184`) and carry no properties unless noted.
- **"Scribe fields":** `scribe_id`, `scribe_uuid`, `scribe_status`.
- **No PHI found** in Mixpanel properties.

| # | Stage | Event | Properties | Where |
|---|---|---|---|---|
| M1 | C0 | `start_recording_tapped` | none | `visits/views/visit_info_screen.dart:2400`; `visits/views/widgets/patient360_visit_widgets.dart:1597` |
| M2 | C0 | `start_recording_split_menu_tapped`, `start_recording_smart_update_selected` (inpatient) | none | `patient360_visit_widgets.dart:1646`, `:1657` |
| M3 | C0 | `new_scribe_button_tapped`; other entry points (`noaccessui_record_a_new_scribe_tapped`, `carecues_start_a_new_recording_tapped`, `nursing_smart_update_picker_start_new_recording_tapped`) | none | `scribe/views/history_screen.dart:301`; see the agent notes |
| M4 | C0 blocked | `snackbar_shown` ("A recording is in progress…", "Couldn't start recording") | message, type | `visit_info_screen.dart:2582`, `:2637` |
| M5 | C1 | `chunking_recording_started` / `native_recording_started` | duration_seconds, template_id, **device_id (audio input; overwrites the install id)**, recording_mode, session_type, headphones_worn, **uuid** | `record/providers/recording_analytics_provider.dart:119`, `:158`. **Can be missed** if the screen opens during `initializing`. |
| M6 | C1/C2 | `patient_consent_checkbox_toggled`, `telehealth_wearing_headphones_checkbox_toggled` | none | `record/views/widgets/patient_consent_checkbox.dart:57`; `telehealth_message.dart:35` |
| M7 | C2 | `pause_recording_tapped`, `minimized_pause_tapped`, `pip_pause_action` | `source` (pip) | `record/views/recording_screen_layout.dart:544`; `minimized_recording_widget.dart:105`; `lib/src/services/document_pip/pip_analytics_service.dart:52` |
| M8 | C2 | `chunking_recording_paused` / `native_recording_paused` | same as M5 | `recording_analytics_provider.dart:122` |
| M9 | C2 | `resume_recording_tapped` ⚠️ also used in the short-recording dialog; `resume_visit_tapped`, `minimized_resume_tapped`, `pip_resume_action` / `pip_resume_failed` | `source`, error_message | `recording_screen_layout.dart:552`; `record/views/recording_screen.dart:372`; `pip_analytics_service.dart:64`, `:81` |
| M10 | C2 | `chunking_recording_resumed` / `native_recording_resumed` | same as M5 | `recording_analytics_provider.dart:117` |
| M11 | C2 | `back_to_visits_tapped`, `start_another_visit_tapped` (leaves the recording paused) | none | `recording_screen.dart:399` |
| M12 | C2 | `toast_shown` (low-audio warning) | title, message, type | `recording_screen.dart:1228` |
| M13 | C3 | `end_visit_tapped`, `minimized_end_tapped`, `pip_end_action` / `pip_end_failed` | `source`, error_message | `recording_screen_layout.dart:577`; `recording_screen.dart:385`; `minimized_recording_widget.dart:134`; `pip_analytics_service.dart:93` |
| M14 | C3 | Short-recording dialog: `resume_recording_tapped` / `end_recording_tapped`; `second_scribe_confirm_tapped` | none | `recording_screen.dart:909`, `:910`, `:457` |
| M15 | C3 | `chunking_recording_stopped` / `native_recording_stopped` | same as M5, with the final duration_seconds | `recording_analytics_provider.dart:124` |
| M16 | C4a error | `toast_shown` with the upload/finalize error text | title (free text, no uuid) | `record/providers/cache_upload_provider.dart:104`; `chunk_upload_provider.dart:1668`, `:1719` |
| M17 | C4a recovery | `cache_screen_try_again_tapped`, `_contact_us_tapped`, `_download_audio_tapped` | none | `visits/views/cache_in_queue_screen.dart:183-203` |
| M18 | C4a recovery | `paused_caches_dialog_upload_tapped`, `_skip_tapped`, `_delete_tapped`, `_delete_confirmed`, `_delete_cancelled` | none | `record/widgets/paused_caches_dialog.dart:231-335` |
| M19 | C4a recovery | `orphaned_upload_recovery_not_now_tapped`, `_recover_all_tapped`, `_recover_tapped`, `_discard_tapped` | none | `record/views/widgets/orphaned_upload_recovery_dialog.dart:197-816` |
| M20 | Discard | `cache_screen_delete_visit_tapped` → `_confirmed` → `visit_cache_deleted` | none | `cache_in_queue_screen.dart:197`, `:326`, `:358` |
| — | C4b | *(upload done / scribe created)* | | **Not in Mixpanel** |
| M21 | C4b/B3 | `scribe_status_viewed_in_cache`, `scribe_status_viewed_<status>`, `visit_status_viewed_<taskStatus>` | Scribe fields (empty for a cache; none for the visit variant) | `scribe/views/history/eclipse_history_tile.dart:62`, `:70`; `visits/views/visit_list_item.dart:292` |
| M22 | B3 | `scribe_card_tapped` (closest to "note opened") | Scribe fields | `eclipse_history_tile.dart:199` |
| M23 | B3 | `scribe_<tab>_tab_selected` | template_id, template_name | `scribe/views/details/scribe_tab_bar.dart:436` |
| M24 | B3 error | `scribe_error_contact_us_tapped`, `scribe_error_rate_scribe_tapped` | none | `lib/src/ui/widgets/eclipse_scribe_generation_error.dart:42` |
| M25 | B3 | Regenerate: `ai_action_<title>_selected`, `ai_action_change_template_regenerate_tapped`, `ai_action_smart_edit_regenerate_tapped` | not checked | `scribe/views/widgets/eclipse_ai_action_button.dart:289` and others |
| M26 | B4 | `scribe_copy_note` (fires even when copy is disabled) | Scribe fields | `note_page_button_bar.dart:1424` |
| M27 | B4 | `copy_transcript_tapped` | none | `scribe/views/details/transcriptions_body.dart:393` |
| M28 | B4 | `scribe_sync_note`, `scribe_sync_to_ehr`, `scribe_select_sections_to_sync` → `ehr_sync_section_selection_confirm` | Scribe fields | `note_page_button_bar.dart:1356`, `:1407`, `:1456` |
| M29 | B4 | `scribe_send_to_mds`, `send_to_mds_tapped` | Scribe fields | `note_page_button_bar.dart:1376`; `scribe/views/widgets/send_to_mds_button.dart:49` |
| M30 | B4 error | `snackbar_shown` ("Note failed to send to MDS", …) | message, type | `note_page_button_bar.dart:471`, `:607`, `:656` |
| — | B4 | *(EHR sync result)* | | **Not in Mixpanel** |
| M31 | After delivery | `delete_scribe_tapped` → `delete_scribe_confirmed` → `scribe_deleted` | `scribe_deleted`: {scribe_id} | `scribe/views/widgets/menu_button.dart:109-183` |

**Joining Mixpanel to scribe_events:** use `uuid` on the M5 / M8 / M10 / M15 events, or `scribe_uuid` / `scribe_id` on the scribe events. Tap events have neither.

---

## 3. Gaps and agreed fixes

Fixes agreed on 11/5 are explained in section 4.

| # | Gap | Stage | Fix (agreed 11/5) |
|---|---|---|---|
| G1 | Blocked starts send no event (active recording, duplicate tab, permission denied, paywall, no template, cancelled, Safari on iOS, "Couldn't start recording") | C0 | New `ATTEMPTED` + one `PREFLIGHT_BLOCKED{reason}` or `START_FAILED` per exit (4.2) |
| G2 | Events before the uuid exists use a random uuid (`RECORDING_INITIATED`, `LOW_WARNING_DIALOG_SHOWN`, `RECORDING_MODE_SELECTED`); no session or attempt id | C0 | Mint the recording id at ATTEMPTED and pass it to every C0 event (4.2) |
| G3 | `RECORDING_INITIATED` keeps pinging every 30 s after a blocked start (and after a failed native start) | C0 | Send it once (no timer); native reset also stops the monitor (4.2) |
| G4 | `PARALLEL_RECORDING_STARTED` fires before the mic starts; there's no "first audio packet" event | C1 | New `MIC_LIVE` on the first audio packet (4.3) |
| G5 | A kill before uuid save (1.4) is never detected | C0–C1 | "Open recording" entry with a phase from ATTEMPTED; `TERMINATED_UNEXPECTEDLY{last_phase}` on next launch (4.4) |
| G6 | Pause events have no reason; interruptions aren't logged except the end of an iOS one | C2 | `reason` on `PARALLEL_RECORDING_PAUSED` from all 9 callers; `INTERRUPTED` only for OS-signalled interruptions (4.5) |
| G7 | Cache started → paused on launch sends no event | C2/K | New `auto_paused` state, reported on `TERMINATED_UNEXPECTEDLY{restored_as}` (4.4) |
| G8 | `APP_KILLED_DETECTED`: kill time is the last lifecycle save, `was_recording_when_killed` is constant, possible session-id key collision, no exit reason; `DURATION_NORMALIZED_AFTER_KILL` is skipped for chunking | K | Replaced by `TERMINATED_UNEXPECTEDLY` (4.4); exact cause via Sentry watchdog + recording id (AFEP-3003) |
| G9 | `CHUNK_ADDED` payload has only filePartId; `CHUNK_UPLOAD_RETRY_BACKOFF` has no uuid | C2 | Add `chunk_index`, `bytes` to `CHUNK_ADDED` (it becomes "audio saved"); add the uuid to retry backoff |
| G10 | **When an upload gets stuck, the app doesn't say so.** If the upload fails after a recording ends (offline, some pieces failed, pieces missing), the app quietly marks it "error" and sends nothing. We only see it later in the 30-minute health check, so we know it's stuck but not when or why. | C4a | Send an event when the cache moves to error, with the reason (offline / partial / missing chunks) |
| G11 | **Older-style recordings never confirm the hand-off.** Chunked recordings send "done, here's the scribe id"; single-file recordings send nothing, so we have to look for a scribe with the same recording id. | C4a/C4b | Send the same `SCRIBE_CREATED` from the single-file path (4.7) |
| G12 | **Recordings rescued later look like they were never rescued.** The background retry doesn't send "scribe created" or "removed from phone" when it succeeds, and the recovery pop-up's events have no recording id. | Recovery | Send `SCRIBE_CREATED` from the background retry and the recovery pop-up; add the recording id to recovery events (4.7) |
| G13 | Backend: async combine has no COMPLETED; combine failure hard-deletes the scribe with no event; transcription failure has no event; no status history | B1–B3 | Not discussed yet |
| G14 | SYNCED / SYNC_ERROR / COPIED are task_status only; `ALL_TASKS_COMPLETED` can repeat | B3–B4 | Not discussed yet |
| G15 | ⚠️ PHI in payloads: `patient_name` in RECORDING_INITIALIZED, PARALLEL_RECORDING_STARTED, SCRIBE_FAILED, LOW_MEMORY_DURING_RECORDING; `patient_email` + `patient_name` in EMAIL_* | — | Flag to the app team; remove from payloads |
| G16 | Mixpanel: `device_id` overwritten by the audio device id on recording events; `resume_recording_tapped` has two meanings; `*_recording_started` can be missed; no upload, hand-off or sync-result events | All | Not discussed yet |
| G17 | `START_RECORDING_ERROR` has hard-coded error text and a null stack; early errors are mislabelled `MID_RECORDING_ERROR` | C1 | `START_FAILED{error_code}` from one sender (4.3) |
| G18 | `LOW_AUDIO_DETECTED` uses the first cache's uuid, which may not be the current recording | C2 | Use the current recording's id |
| G19 | Too-short recordings (< 20 s) never send `PARALLEL_RECORDING_ENDED` (the check exits first, `recording_state_notifier.dart:1403-1459`); `autoStop()` has no caller and `stop()` is empty on chunking | C3 | Fire `PARALLEL_RECORDING_ENDED{reason}` on every ending; confirm auto-stop with the app team (4.6) |

---

## 4. Proposed changes (agreed 11/5)

### 4.1 Rule: reuse existing events first

Add a missing field, or make an existing event fire on every path. Add a new `RECORDING_LIFECYCLE` event only where nothing exists today.

| Funnel step | Event | Kind of change |
|---|---|---|
| Attempt | `RECORDING_LIFECYCLE / ATTEMPTED` | **New** |
| Blocked before start | `RECORDING_LIFECYCLE / PREFLIGHT_BLOCKED{reason}` | **New** |
| Mic producing audio | `RECORDING_LIFECYCLE / MIC_LIVE` | **New** |
| Start failed | `RECORDING_LIFECYCLE / START_FAILED{error_code}` | **New** (old events kept for old dashboards) |
| Audio saved on the phone | first `SCRIBE_AUDIO_CACHE_SYNC_V2 / CHUNK_ADDED` | **Add fields** `chunk_index`, `bytes`. New signal only for non-chunking mobile and web non-chunking. |
| Save failed | DB: existing `FILE_PART_INSERT_FAILED`, `AUDIO_CACHE_UPDATE_FAILED`. File / encrypt / decrypt: `RECORDING_LIFECYCLE / PERSIST_ERROR` | **New** only for the non-DB steps |
| Paused | `SCRIBE_JOURNEY / PARALLEL_RECORDING_PAUSED` | **Add field** `reason` |
| Interrupted by the OS | `RECORDING_LIFECYCLE / INTERRUPTED` + `INTERRUPTION_ENDED` | **New**, OS-signalled only |
| Ended | `SCRIBE_JOURNEY / PARALLEL_RECORDING_ENDED` | **Add field** `reason`; **fire on more paths** (too short) |
| App died mid-journey | `RECORDING_LIFECYCLE / TERMINATED_UNEXPECTEDLY` | **New** (replaces `APP_KILLED_DETECTED` for the funnel) |
| Handed off | `SCRIBE_CHUNKING / SCRIBE_CREATED` | **Fire on more paths** (non-chunking, background retry, recovery pop-up). `HANDED_OFF` and `LINKED` **dropped**. |
| Partial submit | `FINALIZE_PARTIAL`, `PARTIAL_SUBMIT` | Already exists |
| Memory at tap | `RESOURCE_MONITORING / RECORDING_INITIATED` | **Change**: send once, with the recording id |

### 4.2 C0: when ATTEMPTED fires and when the recording id is created

- **ATTEMPTED fires at the top of `StartVisitController.startVisit()`,** once per accepted tap:
  - after the double-tap lock, so double taps don't count;
  - **before** the active-recording check (0.1), so "tapped while another recording was open" counts as an attempt.
  - It covers every entry point (button, welcome tour, Smart Update).
  - The Safari-on-iOS block moves from the screen into the pre-checks.
- **The recording id is minted at ATTEMPTED,** in the right format for the mode (plain v4 for chunking, `scribe_audio_workflows_<hex>` for non-chunking), using the existing `recordingUuidProvider`.
  - `initialize()` then uses `cache?.uuid ?? provider ?? v4()`. Resume keeps the existing id.
  - A blocked attempt keeps an id that never becomes a recording. A new tap gets a new id.
- **The id goes on every C0 event:** `RECORDING_INITIATED`, `LOW_WARNING_DIALOG_SHOWN`, `RECORDING_MODE_SELECTED`.
- **`RECORDING_INITIATED` becomes one sample** (`track()` instead of `start()`), so nothing is left pinging after a blocked start (G3). Native `reset()` also stops the monitor.
- **Every exit of `startVisit()` sends exactly one closing event**, from one switch at the end:

| Result today | Event |
|---|---|
| ActiveRecording | `PREFLIGHT_BLOCKED{active_recording}` |
| (Safari on iOS, moved in) | `PREFLIGHT_BLOCKED{unsupported_browser}` |
| DuplicateTabBlocked | `PREFLIGHT_BLOCKED{duplicate_tab}` |
| MemoryLow (dialog cancelled) | `PREFLIGHT_BLOCKED{low_battery / low_storage}` |
| PermissionDenied | `PREFLIGHT_BLOCKED{permission_denied}` |
| PaywallRequired | `PREFLIGHT_BLOCKED{paywall}` |
| NeedsTemplate | `PREFLIGHT_BLOCKED{no_template}` |
| VisitStartCancelled | `PREFLIGHT_BLOCKED{user_cancelled}` |
| StartFailed / RecordingDidNotStart | `START_FAILED{error_code}` (from the notifier; no duplicate) |
| StartedOk | carries on to `MIC_LIVE` |

- **Resume** sends `ATTEMPTED{on_resume: true}` with the existing id, and the same blocked / failed events.

### 4.3 C1: MIC_LIVE and START_FAILED

- **`MIC_LIVE` fires on the first audio packet** in the recorder's stream handler (`chunking_recording_state_notifier.dart:878`), not when `startStream` returns, because the mic can "start" and deliver nothing.
  - Non-chunking: the first sound-level reading (`amplitudeSubscription`).
  - Payload: ms since ATTEMPTED, input device, sample rate / format, `on_resume`.
- **`START_FAILED{error_code}`** comes from one helper, at most once per attempt, called from four places:

| Where the start dies | Code | `error_code` example |
|---|---|---|
| Mic won't start on any device | `:798-813` | `mic_unavailable` |
| Recorder error before the first packet | `:493-543` | `recorder_error` (+ the real error) |
| Any other failure during start | `start()` catch `:1013-1059` | `cache_insert_failed`, `audio_format_unknown`, … |
| Mic started but no audio within 5 s | new watchdog after `startStream` | `no_audio_packets` |

- **On resume:** the same places, with `on_resume: true`. A failed resume is terminal only if no later `MIC_LIVE` arrives for that id.

### 4.4 Kills: the "open recording" entry (G5, G7, G8)

A kill can't be logged when it happens. So:

1. **Save an entry at ATTEMPTED:** recording id, `phase = preflight`, time. Wait for the write to finish.
2. **Update the phase at each step:** `initializing` (cache created), `recording` (`MIC_LIVE`), `paused` / `recording` (pause / resume), `uploading` (after stop). Each update stores the time.
3. **Clear it on every normal ending:** `PREFLIGHT_BLOCKED`, `START_FAILED`, `DISCARDED`, `SCRIBE_CREATED`.
4. **At the next launch, if an entry is still there:** send `TERMINATED_UNEXPECTEDLY{recording_id, last_phase, last_seen_at, restored_as, parts_saved, duration_saved}`, then clear it. Test for "leftover entry", not "session id changed" (that key collides).

| last_phase | What happened | Outcome |
|---|---|---|
| `preflight` | App closed during the pre-checks | Expected exit: gave up before starting |
| `initializing` | Killed after the cache was created, before the mic started | Killed before recording. Delete the empty cache, `ABANDONED{killed_before_mic}`. |
| `recording` / `paused` | Killed mid-recording | Killed unexpectedly. Restored as **`auto_paused`** (new state), not plain `paused`; `restored_as: auto_paused`. |
| `uploading` | Killed during finalize | Not a recording loss; upload recovery picks it up (C4a) |

- **A kill while already paused** stays a user pause: the cache was `paused`, not `started`.
- **Kill time:** bounded by the last `RECORDING_IN_PROGRESS` (every 30 s, phone time). Exact time and cause: the Sentry watchdog event tagged with the recording id (AFEP-3003); on Android, exit info.
- **Never reopened:** nothing is ever sent; the backend sees silence → "lost: device not reopened".
- **Web:** the same entry in local storage, written at ATTEMPTED.

### 4.5 C2: pause reasons and interruptions

All pauses go through `pauseParallelRecording()`. Add a `reason` argument and put it on `SCRIBE_JOURNEY / PARALLEL_RECORDING_PAUSED`:

| Caller | Code | reason |
|---|---|---|
| Pause button | `record/views/recording_screen.dart:844` | `user` |
| Picture-in-picture (mobile / Chrome) | `recording_pip_notifier.dart:190`, `chrome_recording_pip_notifier.dart:212` | `user_pip` |
| Onboarding script panel | `onboarding_core/widgets/mobile_script_panel.dart:227` | `user_tour` |
| No-audio auto-pause | `chunking_recording_state_notifier.dart:1246` | `no_audio_auto` |
| Android phone call | `recording_state_notifier.dart:869` | `phone_call` |
| iOS audio interruption | `recording_state_notifier.dart:963` | `interruption` |
| Mic / device change | `record/providers/device_change_mixin.dart:107` | `device_change` |
| End tapped while recording (pause before stop) | `recording_state_notifier.dart:1577` | `ending` |
| "Start another visit" | `recording_state_notifier.dart:1645` | `new_visit` |

- **A kill is not a pause event.** It's reported at the next launch (4.4).
- **`INTERRUPTED{source}` / `INTERRUPTION_ENDED`** only when the OS says the mic was taken: Android call, iOS interruption **begin** (today only the end is logged), route change. A call produces both `INTERRUPTED{call}` and `PAUSED{phone_call}`.
- **The no-audio auto-pause (2.15) is not an interruption.** It's `PAUSED{no_audio_auto}`, with `CONSECUTIVE_FLUSH_EMPTIES` as evidence.
- **Audio saved:** the first `CHUNK_ADDED` (with `chunk_index`, `bytes`). `FILE_ADDED` doesn't count: it fires before the mic.

### 4.6 C3: ended

- Reuse `SCRIBE_JOURNEY / PARALLEL_RECORDING_ENDED`, adding `reason` (user / auto_stop / max_length / too_short / discarded).
- Make it fire on every ending. Today too-short recordings skip it (G19).
- Confirm with the app team whether auto-stop at 3 h runs at all on chunking.
- The pause sent just before a normal stop gets `reason: ending`, so it can be filtered out.

### 4.7 C4a / C4b: upload and hand-off

- **`HANDED_OFF` and `LINKED` are dropped.**
  - `SCRIBE_CHUNKING / SCRIBE_CREATED` already is the hand-off (recording id + scribe id). Send it from **every** path that creates a scribe: chunking (today), single-file uploads (G11), the background retry (G12), the recovery pop-up (G12, with the recording id added).
  - The recording ↔ scribe link is already in `scribe.uuid` and the backend's `SCRIBE_JOURNEY / NORMANDY_WORKFLOWS_*` events.
  - Optional: a pre-chart / duplicate flag as a field on an existing backend event.
- **Partial submit** is already flagged (`FINALIZE_PARTIAL`, `PARTIAL_SUBMIT`).
- **Stuck uploads (G10):** send an event when the cache moves to error, with the reason (offline / partial / missing chunks).

---

## 5. Tasks

One row per piece of work (agreed 11/5); the same list is in the overview HTML, "Tasks" section. Phases: P0 now, P1 once P0 builds are in the field, P2 depth. Owners: "Recorder eng" = the app logging owner from the 11/2 meeting; backend owner TBD.

### App: start (C0–C1)

| # | Task | Gaps | Owner | Phase | Ticket | Done when |
|---|---|---|---|---|---|---|
| T1 | Create the recording id at ATTEMPTED and put it on every C0 event | G2 | Recorder eng | P0 | — | No C0 event has a random uuid |
| T2 | Send ATTEMPTED, then one PREFLIGHT_BLOCKED{reason} per blocked exit, from one switch in startVisit(); move the Safari-iOS check in | G1 | Recorder eng | P0 | — | Every startVisit() result produces exactly one closing event |
| T3 | Send RECORDING_INITIATED once (no 30 s timer); native reset() stops the monitor | G3 | Recorder eng | P0 | — | No RECORDING_INITIATED after a blocked start |
| T4 | Send MIC_LIVE on the first audio packet (non-chunking: first sound-level reading) | G4 | Recorder eng | P0 | — | MIC_LIVE count ≈ recordings with a first CHUNK_ADDED |
| T5 | Send START_FAILED{error_code} from one sender: mic won't start, early recorder error, start exception, 5 s no-audio check | G17 | Recorder eng | P0 | — | Every failed start has exactly one START_FAILED with a typed code |

### App: recording (C2)

| # | Task | Gaps | Owner | Phase | Ticket | Done when |
|---|---|---|---|---|---|---|
| T6 | Add reason to PARALLEL_RECORDING_PAUSED from all 9 callers | G6 | Recorder eng | P0 | — | No pause event without a reason |
| T7 | Send INTERRUPTED / INTERRUPTION_ENDED when the OS takes the mic (call, iOS interruption, route change) | G6 | Recorder eng | P0 | — | iOS interruption start is logged, not only the end |
| T8 | Add chunk_index and bytes to CHUNK_ADDED; add the recording id to CHUNK_UPLOAD_RETRY_BACKOFF | G9 | Recorder eng | P0 | — | First CHUNK_ADDED can stand in for “audio saved” |
| T9 | Send PERSIST_ERROR for file / encrypt / decrypt failures; AUDIO_PERSISTED for non-chunking | — | Recorder eng | P0 | — | Encrypt / decrypt failures show up as events, not only in Sentry |
| T10 | LOW_AUDIO_DETECTED: use the current recording's id | G18 | Recorder eng | P0 | — | Low-audio events match the recording they happened in |

### App: kills

| # | Task | Gaps | Owner | Phase | Ticket | Done when |
|---|---|---|---|---|---|---|
| T11 | Keep an open-recording entry (id + phase + time) from the tap; send TERMINATED_UNEXPECTEDLY{last_phase} at the next launch | G5, G8 | Recorder eng | P0 | — | Kills before the mic starts are detected; every kill has last_phase |
| T12 | Restore killed recordings as auto_paused, not paused (reported on TERMINATED_UNEXPECTEDLY) | G7 | Recorder eng | P0 | — | Stuck-in-cache splits into user-paused and auto-paused |
| T13 | **Decide:** should auto-paused recordings upload automatically or prompt the provider? | — | Recorder eng + product | P0 | — | Decision written in the PRD (§13 #13) |

### App: end and hand-off (C3–C4b)

| # | Task | Gaps | Owner | Phase | Ticket | Done when |
|---|---|---|---|---|---|---|
| T14 | Add reason to PARALLEL_RECORDING_ENDED and send it on every ending (incl. too-short); tag the pre-stop pause reason: ending | G19 | Recorder eng | P0 | — | Every ended recording has one ENDED event |
| T15 | **Confirm:** does the 3-hour auto-stop run on chunking? | G19 | Recorder eng | P0 | — | Answered; fixed if it doesn't run |
| T16 | Send AUDIO_CACHE_ERROR{reason} on chunking when a cache moves to error | G10 | Recorder eng | P0 | — | Stuck uploads show up when they happen, not only in the 30-min health check |
| T17 | Send SCRIBE_CREATED from single-file uploads, the background retry and the recovery pop-up; add the recording id to recovery events | G11, G12 | Recorder eng | P0 | — | Every scribe created from the app has a matching SCRIBE_CREATED |
| T18 | Add recording_phase to each cache in SCRIBE_AUDIO_CACHE_HEALTH_V3 | — | Recorder eng | P0 | — | Open recordings can be listed by phase |

### App: ids, crash tags, privacy

| # | Task | Gaps | Owner | Phase | Ticket | Done when |
|---|---|---|---|---|---|---|
| T19 | Add app_session_id and install_id to every event (no recording_seq, dropped 11/6) | — | Recorder eng | P0 | — | Every event has both ids; the install_id check separates "lost" from "not seen since" |
| T20 | Put recording id, phase and chunk index on Crashlytics and Sentry (Sentry watchdog kills carry them) | G8 | Recorder eng | P0 | AFEP-3003 | A watchdog kill links to the recording it interrupted |
| T21 | Remove patient names and emails from event payloads | G15 | Recorder eng | P0 | — | No patient_name / patient_email in scribe_events |
| T22 | Telemetry health: EVENTS_DROPPED, queue stats; web sendBeacon | — | Recorder eng | P1 | — | Dropped events are counted |
| T23 | Read the OS exit reason (Android ApplicationExitInfo, iOS MetricKit) onto TERMINATED_UNEXPECTEDLY | — | Recorder eng | P2 | — | Kills split by memory / crash / swipe |

### Backend

| # | Task | Gaps | Owner | Phase | Ticket | Done when |
|---|---|---|---|---|---|---|
| T24 | Optional: pre-chart / duplicate flag on an existing backend event at trigger time | — | Backend (TBD) | P0 | — | Promoted and duplicate scribes are flagged |
| T25 | STATUS_CHANGED on every task_status change, plus a status history table | G14 | Backend (TBD) | P0 | — | Delivery and error timing survive later status changes |
| T26 | Soft delete + failure event instead of hard delete when combine fails | G13 | Backend (TBD) | P0 | — | No scribe disappears without an event |
| T27 | A stuck event per scribe past N minutes at a stage | — | Backend (TBD) | P0 | — | Stuck is an explicit state |
| T28 | Missing stage events: transcription failed, async combine completed, delivery result | G13, G14 | Backend (TBD) | P1 | — | Each backend stage has a start and an end event |
| T29 | ALL_TASKS_COMPLETED once per scribe; X-Recording-Id header in logs | — | Backend (TBD) | P2 | — | — |

### Data, views, validation

| # | Task | Gaps | Owner | Phase | Ticket | Done when |
|---|---|---|---|---|---|---|
| T30 | recording_outcome on today's events (legacy path), in StarRocks | — | Arthur | P0 | — | Last week's recordings each have one outcome |
| T31 | Map 10–15 days of support tickets to outcomes (acceptance test) | — | Arthur | P0 | — | Every ticket lands in one outcome; misses become logging gaps |
| T32 | One row per crash, copied to StarRocks | — | Arthur + Prokash | P1 | — | Crashes join to sessions and recordings |
| T33 | Contract classifier, recording_trace, session_outcome | — | Arthur | P1 | — | New app versions use the contract path |
| T34 | Grafana alerts and data quality strip on StarRocks | — | Arthur | P1 | — | Alerts link to the recording list |
| T38 | Daily outcome job → recording_outcome + one RECORDING_OUTCOME event per recording (to Mixpanel) | — | Arthur | P1 | — | Mixpanel and Grafana show the same outcome counts |
| T39 | Grafana recording list, per-recording timeline, ops panels (replaces the Retool page) | — | Arthur | P0 | — | Any recording can be looked up and its timeline shown |

### Mixpanel pipeline (design: `docs/20261105-funnel-logging-design.md`)

| # | Task | Gaps | Owner | Phase | Ticket | Done when |
|---|---|---|---|---|---|---|
| T35 | Pub/Sub → Mixpanel subscriber: forward funnel events only, $insert_id = client_event_id, phone time, retry queue | — | Backend (TBD) | P0 | — | Funnel events appear in Mixpanel once each, grouped by recording |
| T36 | Keep client_event_id (in payload) on every app event | — | Backend (TBD) | P0 | — | Repeat sends can be deduped |
| T37 | **Check:** Mixpanel approval (BAA / security); project and Group Analytics on recording_id | — | Arthur | P0 | — | Approved before anything is sent |

**Reused as is:** chunk upload events, finalize events (FINALIZE_*), background / foreground events, the crash pipeline into BigQuery, and the cache health event as the open-recordings list.

G16 (Mixpanel) has no task yet: not discussed.
