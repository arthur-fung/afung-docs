# PRD: Ambient Scribe Reliability Funnel (v2, traceable to every recording)

| | |
|---|---|
| **Author** | Arthur Fung |
| **Status** | Draft for review |
| **Date** | 2026-11-02 |
| **Supersedes** | v1 (`docs/20261102-reliability-funnel-prd-v1.md`) |
| **Related** | [FE Metrics Definitions](https://app.notion.com/p/athelas-public/FE-Metrics-Definitions-232f92a633f280839e44c1f65ddd8fff), `README.md`, `docs/20261015-recording-funnel-diagram.html`, [LLM-21067](https://linear.app/commure/issue/LLM-21067) |

**What changed from v1:**
- v1 built the funnel by inferring outcomes from whatever events exist today, and it left crashes and some backend states as aggregates.
- v2 starts from one requirement: **every number on the view can be clicked down to the individual recordings (or app sessions) behind it, and each recording's full timeline can be seen.**
- We change the app and backend as needed to make that true, rather than working around today's telemetry.
- The inference from v1 stays only as a fallback for old app versions during rollout.

**Updated after the 11/2 "Recording Funnel Logging — Design & Gap Analysis" meeting** (transcript: `docs/20261102-recording-funnel-logging-transcript.txt`):
- three top-level phases (§1);
- the auto-paused state, resume failures, interruptions and save/encryption failures (§5.2);
- reuse of the existing finalize events, with C4 split in two (§6.2);
- one "killed unexpectedly" outcome instead of three (§6.3, now 17 outcomes);
- support-ticket validation (§10.4), owners (§14) and the reopened tool decision (§12).

**Updated 11/5 after tracing today's events in the code** (`docs/20261105-recording-journey-event-index.md`):
- **Reuse existing events first** (§5.2). `AUDIO_PERSISTED` (chunking) → first `CHUNK_ADDED`; `ENDED` → `PARALLEL_RECORDING_ENDED` + reason; `PAUSED` → `PARALLEL_RECORDING_PAUSED` + reason; `HANDED_OFF` and backend `LINKED` dropped in favour of `SCRIBE_CREATED` from every path; `STILL_OPEN` replaced by the existing cache health ping.
- **C0 pinned down:** `ATTEMPTED` fires before the active-recording check and mints the recording id; every exit maps to one event; `RECORDING_INITIATED` is sent once (§5.2.1).
- `MIC_LIVE` on the first audio packet; four sources for `START_FAILED` (§5.2.2); nine pause reasons (§5.2.3).
- Kills: an open-recording entry with a phase from the tap, reported at the next launch (§5.4).
- Corrected: iOS does ask for mic permission; interruptions aren't sent to Sentry; backend events use tag `SCRIBE_JOURNEY`.

---

## 1. Summary

We'll build one funnel that follows **each recording** from the provider tapping record to the note reaching the EHR. Every signal about that recording carries the recording's id: app events, upload attempts, backend status changes, errors, crashes and OS kills. So:

1. **Every aggregate is a count of rows.** Lost, unexpected failures, incomplete, crashes per 1k and every other metric is a filter over a per-recording table, never a separately computed number.
2. **Every recording has exactly one outcome**, and that outcome cites the event that decided it.
3. **Every recording has a timeline:** one ordered list of everything that happened to it, from the app, backend and crash reporters.
4. **Crashes that happen outside a recording** (e.g. at login) trace to an **app session** instead. Crash-free rates are computed from those sessions, so they can be drilled into too.

**Top-level phases** (as agreed on 11/2). The 10 stages in §6.2 are the detail underneath:

| Phase | What happens | Stages |
|---|---|---|
| **1. Start** (and every resume) | Tap record, pre-checks (permission, mic, storage, memory), mic goes live | C0–C1 |
| **2. Recording** | Audio is saved locally (encrypted) and, on the chunking path, uploaded in parallel. Pauses, interruptions and app kills happen here. | C2 |
| **3. End and handoff** | Stop, wait for in-flight uploads, retry pending chunks, upload the manifest, trigger the backend workflow | C3–C4b |
| **4. Backend** | Audio received, transcribed, note generated, delivered | B1–B4 |

The "~30 funnels" mentioned in the meeting are the outcomes in §6.3 × their reasons (e.g. Start failed × permission denied).

## 2. Traceability requirements

These are the acceptance criteria for the whole project.

| # | Requirement |
|---|---|
| R1 | Every recording has one `recording_id`, minted **when the provider taps record**, before any permission check. It is the same value in app events, backend rows, upload sessions, crash reports, handled errors, logs and HTTP requests. |
| R2 | Every app-side signal (event, crash, handled error, OS exit report) also carries `app_session_id` (one per app launch / page load) and `install_id` (one per install / browser profile). |
| R3 | Each recording's life is described by a small, versioned set of **lifecycle events**, each sent exactly once per transition, with a per-recording sequence number. **Every recording ends in an explicit terminal event**, or is classified as lost by a rule that names the last evidence seen. |
| R4 | The backend records every status change for a scribe as an event or a history row. **Nothing is hard-deleted** without first writing a terminal event. |
| R5 | Every dashboard number links to the list of recordings or sessions it counts. Every row in that list links to the recording's timeline. Every timeline entry links to its source: the event, scribe row, Sentry event or Crashlytics issue. |
| R6 | Missing telemetry is measurable. Dropped events are counted, so "lost" can be told apart from "we lost the events". |
| R7 | No patient data in any of this. Ids, codes, platform and version only. Patient names are removed from the existing event payloads (gap G14). |

## 3. Goals, non-goals, users

**Goals:**
- One end-to-end funnel covering:
  - frontend metrics: lost, unexpected failures, audio discrepancy, stuck in cache, recovery;
  - the backend funnel: incomplete, errored, stuck, delivery;
  - crashes: fatal, OOM, ANR, kills;
  - the client and backend lifecycles.
- A 5-week trend with OKR goals.
- Breakdowns by platform + browser and by app version.
- Drill-down to the recording, as R5 describes.
- Alerts.

**Non-goals:**
- Note quality.
- Minute-level real-time monitoring.
- Replacing the Sentry and Crashlytics consoles for debugging. We link to them.

**Users:**

| User | Uses |
|---|---|
| Leadership | Headline tiles vs goal, 5-week sparkline |
| FE / BE reliability owners | Funnel → outcome → recording list → timeline, for weekly review and root cause |
| On-call | Slack alerts linking straight to the affected recording list |
| Support | Look up one recording or account: "what happened to this visit?" |

## 4. Units of analysis

**Today:** ✅ exists · 🟡 partly exists (closest thing named) · ❌ new · ❓ not checked

| Unit | Id | Minted | Used for | Today |
|---|---|---|---|---|
| **Recording** | `recording_id` (UUID v4; `scribe_audio_workflows_<hex>` on non-chunking) | At `ATTEMPTED`: top of `StartVisitController.startVisit()`, before any pre-check (§5.2.1) | The funnel, every recording-level metric | 🟡 Sent as `uuid`, but created at recording start (after pre-flight), and events outside a recording get a random one |
| **App session** | `app_session_id` (UUID v4) | On app cold start / web page load | Crash-free rates, crashes outside recordings, "did the app come back" | ❌ |
| **Install** | `install_id` (UUID v4, kept on the device) | On first launch, per install or browser profile | "Did this device ever come back?", device-level crash history | ❌ No device id on any event (`identifierForVendor` is only shown on the diagnostics screen) |
| **Scribe** | `scribe_id` (backend) | When `/trigger` creates or promotes the scribe | The backend lifecycle. Linked to `recording_id` by `scribe.uuid` (no separate link event). | ✅ |

**Chunks are not a unit.** On the chunking path each chunk has its own save → encrypt → decrypt → upload steps, running in parallel with the recording. The 11/2 meeting agreed the recording is the unit; chunk detail lives in the timeline, chunk counts on the recording row, and `chunk_index` on errors and crashes.

**Recording ↔ scribe** is 1:1 by design.
- A pre-charted draft that receives a recording is *promoted*: the backend copies the recording uuid onto the existing scribe (`normandy/app/api/v1/scribe/workflows/services.py:702-733`). Its `created_at` stays older than the recording, which is the cause of LLM-21067.
- So the link comes from `scribe.uuid` (plus `SCRIBE_CREATED` on the app side), never from comparing timestamps.
- Duplicates caused by retries (`scribe.uuid` is not unique) and pre-chart promotions get a flag on an existing backend event (§5.3). Extra scribes are flagged.

## 5. Telemetry contract (app + backend changes)

### 5.1 Common fields on every app event

Add these to `DefaultEventTrackerService._buildEventData` (`scribe-mobile/lib/services/tracking/event_tracker_service.dart:233`), so **every** event carries them, legacy events included. Already sent today: `tag, action, payload, device_type, operating_system, browser_name, version, scribe_account_id, scribe_id, timestamp, uuid, client_event_id`.

| Field | Notes | Today |
|---|---|---|
| `app_session_id`, `install_id` | R2 | ❌ |
| `recording_id` | Taken from the active recording context. **Remove the random-UUID fallback**: no recording means null, not a fake id. | 🟡 Sent as `uuid`; falls back to a random UUID per event |
| `client_ts`, `monotonic_ms` | Wall clock (can be hours off, see LLM-21067) plus a monotonic clock for ordering within a session | 🟡 Wall clock sent as `timestamp`; no monotonic clock |
| `contract_version` | e.g. `1`. Lets the classifier pick the contract path or the legacy path (§10). | ❌ (`version` is the app version) |

The server adds `received_at` (exists today as `created_at`). **Cohorting uses `received_at`; ordering uses the client `timestamp` (with `monotonic_ms` inside a session), and `received_at` breaks ties.** There is no per-recording sequence number (decided 11/6): Mixpanel orders by `time` and dedupes by `client_event_id`, and a counter only helps for gaps in the middle of a recording's events.

### 5.2 App lifecycle events (reuse existing events first)

**Rule (agreed 11/5):**
- When an existing event already marks a step, add the missing field or make it fire on every path.
- Add a new event (tag `RECORDING_LIFECYCLE`) only where nothing exists today.
- Legacy events not listed here stay for debugging.

Full event-by-event trace of today's app and backend: `docs/20261105-recording-journey-event-index.md`.

**Change:**
- 🆕 new event;
- ➕ add a field to an existing event;
- 🔁 existing event, fire on more paths;
- ✅ keep as is;
- ⏸ not reviewed yet.

| Step | Event (tag / action) | When | Key payload | Terminal? | Change | Today |
|---|---|---|---|---|---|---|
| Attempt | `RECORDING_LIFECYCLE / ATTEMPTED` | Top of `StartVisitController.startVisit()`, after the double-tap lock and **before** the active-recording check. Once per accepted tap; covers every entry point. **Mints `recording_id`** (§5.2.1). | entry_point, recording_mode, `network`, `on_resume` | | 🆕 | ❌ `RESOURCE_MONITORING / RECORDING_INITIATED` fires after the first check, with a random uuid |
| Blocked before start | `RECORDING_LIFECYCLE / PREFLIGHT_BLOCKED` | Any pre-check exit, **on start and on resume**, from one switch at the end of `startVisit()` | `reason`: active_recording / unsupported_browser / duplicate_tab / low_battery / low_storage / permission_denied / paywall / no_template / user_cancelled; `on_resume` | ✅ | 🆕 | ❌ Only `LOW_WARNING_DIALOG_SHOWN` (low battery / storage, max once a day). Every other blocked start logs nothing. Both apps do ask for mic permission. |
| Memory at tap | `RESOURCE_MONITORING / RECORDING_INITIATED` | At ATTEMPTED | memory, disk; **recording_id** | | ➕ Send **once** (`track()`, not `start()`); native `reset()` also stops the monitor | 🟡 Repeats every 30 s with a random uuid, even after a blocked start |
| Mic producing audio | `RECORDING_LIFECYCLE / MIC_LIVE` | **First audio packet** in the stream listener (`chunking_recording_state_notifier.dart:878`), not when `startStream` returns. Non-chunking: first amplitude sample. | ms since ATTEMPTED, input device, sample rate / format, `on_resume` | | 🆕 | 🟡 `PARALLEL_RECORDING_STARTED` fires *before* the mic starts; first `RECORDING_IN_PROGRESS` is the closest |
| Start failed | `RECORDING_LIFECYCLE / START_FAILED` | Between ATTEMPTED (or a resume) and MIC_LIVE. One sender, at most once per attempt (§5.2.2). | `error_code` (typed, §5.7), `on_resume`, `sentry_event_id` | ✅ (on resume: unless resumed later) | 🆕 Old `SCRIBE_FAILED / ON_START` and `START_RECORDING_ERROR` stay for old dashboards | 🟡 `START_RECORDING_ERROR` has hard-coded text and no stack; other start failures go to Sentry or a server log only |
| Audio saved on the phone | first `SCRIBE_AUDIO_CACHE_SYNC_V2 / CHUNK_ADDED` (chunking). Non-chunking mobile / web: `RECORDING_LIFECYCLE / AUDIO_PERSISTED` | First chunk written to the local database; non-chunking: first audio data on disk / in the browser | `chunk_index`, `bytes` (added) | | ➕ chunking; 🆕 non-chunking only | 🟡 `CHUNK_ADDED` has only `filePartId`. `FILE_ADDED` fires before the mic starts, so it proves nothing. Web non-chunking: nothing. |
| Save failed | DB: `FILE_PART_INSERT_FAILED`, `AUDIO_CACHE_UPDATE_FAILED`. Others: `RECORDING_LIFECYCLE / PERSIST_ERROR` | A local save step failed (may be retried, so not terminal). Giving up → `RECORDING_FAILED{stage: persist}`. | `step`: file_write / encrypt / decrypt; `storage`; `chunk_index`; `error_code`; `will_retry` | | ✅ DB; 🆕 file / encrypt / decrypt | 🟡 DB failures have events; encrypt / decrypt mostly Sentry only |
| Interrupted by the OS | `RECORDING_LIFECYCLE / INTERRUPTED` / `INTERRUPTION_ENDED` | **Only when the OS says the mic was taken:** Android call (`recording_state_notifier.dart:855`), iOS interruption begin (`:955`), route change | `source`: call / interruption | | 🆕 (route change and mic loss go to `MIC_LOST`, below) | 🟡 Not logged, except the *end* of an iOS interruption (`SCRIBE_JOURNEY / PHONE_CALL_<type>`). On iOS, telling a call apart needs CallKit. |
| Mic dropped | `RECORDING_LIFECYCLE / MIC_LOST` | Input went away mid-recording: Bluetooth / headset disconnect, route change, another app took the mic, or packets stop for more than a few seconds. Web: `MIC_CHANGE_*`. | `source`: bluetooth_disconnect / route_change / mic_taken / unknown; `recovered`; `ms_without_audio` | | 🆕 | ❌ Only `MIC_CHANGE_*` timeline events |
| Audio level | Rolling fields on the 30 s `RECORDING_IN_PROGRESS` heartbeat; `RECORDING_LIFECYCLE / AUDIO_QUALITY` once per recording (at ENDED, or at TERMINATED_UNEXPECTEDLY from the last heartbeat) | Level sampled per audio packet / amplitude sample | `silent_seconds`, `peak_dbfs`, `avg_dbfs`, `clipped_pct`, `input_device`. Raw numbers only: the outcome job sets the flags (§6.4). | | 🆕 | ❌ Nothing tells a silent mic from a quiet room until the backend says `no_speech` |
| Paused | `SCRIBE_JOURNEY / PARALLEL_RECORDING_PAUSED` | Every call to `pauseParallelRecording()` (§5.2.3) | **`reason`** (added) + existing recording_length, amplitude stats | | ➕ | 🟡 Same event for every pause; no reason |
| Resumed | `ATTEMPTED{on_resume}` → `MIC_LIVE{on_resume}` | Resume re-runs `start()` | | | 🆕 (covered by the two above) | 🟡 `RESOURCE_MONITORING / PARALLEL_RECORDING_RESUMED`; resume also re-sends `PARALLEL_RECORDING_STARTED` |
| Background / foreground | `APP_LIFECYCLE / BACKGROUND_RECORDING`, `FOREGROUND_RECORDING`; web `WEB_LIFECYCLE / TAB_FROZEN`, `TAB_UNFROZEN` | Visibility changes while recording | | | ✅ | ✅ |
| Ended | `SCRIBE_JOURNEY / PARALLEL_RECORDING_ENDED` | Recording stopped, **on every ending** | **`reason`** (added): user / auto_stop / max_length / too_short / discarded; existing `recording_length` | | ➕ + 🔁 | 🟡 Too-short recordings skip it (the check exits first, `recording_state_notifier.dart:1403-1459`). The pause just before a normal stop gets `reason: ending`. |
| Recording failed | `RECORDING_LIFECYCLE / RECORDING_FAILED` | Unrecoverable error after MIC_LIVE | `stage`: capture / persist / finalize; `error_code`; `sentry_event_id` | ✅ unless later recovered | ⏸ | 🟡 `MID_RECORDING_ERROR`, some `SCRIBE_FAILED` |
| Discarded | `RECORDING_LIFECYCLE / DISCARDED` | Intentionally not submitted | `reason`: too_short / user_deleted / user_discarded / no_audio (zero chunks, #6363) | ✅ (expected) | ⏸ | 🟡 `SCRIBE_FAILED_TOO_SHORT`; zero-chunk stop is Sentry only; user delete has no reason |
| Chunk uploads | `CHUNK_UPLOADED`, `CHUNK_UPLOAD_FAILED`, `BACKGROUND_CHUNK_RETRY`, `CHUNK_UPLOAD_RECOVERY` | Each chunk upload / retry / recovery | add `recording_id` where missing (`CHUNK_UPLOAD_RETRY_BACKOFF`) | | ✅ / ➕ | ✅ Well covered |
| Single-file upload | `UPLOAD_ATTEMPT` / `UPLOAD_FAILED` | Each full-file upload attempt (non-chunking) | `attempt_n`, `trigger`, `http_status`, `error_code`, `will_retry` | | ⏸ | 🟡 `SCRIBE_UPLOAD_ERROR` on failure; attempts not logged |
| Finalize (C4a) | `SCRIBE_CHUNKING / FINALIZE_SUCCESS / _PARTIAL / _FAILED / _TIMEOUT / _SKIPPED`, `MANIFEST_FAILED`, `TRIGGER_FAILED`, `PARTIAL_SUBMIT` | End flow: wait ~15 s → retry pending chunks → manifest → trigger | existing payload | FAILED / TIMEOUT: ✅ unless retried later | ✅ | ✅ Chunking |
| Upload stuck | `SCRIBE_AUDIO_CACHE_SYNC_V2 / AUDIO_CACHE_ERROR` | The cache moves to error (offline, partial, missing chunks) | **`reason`** (added) | | 🔁 Fire on chunking too | 🟡 Sent on the single-file path only; on chunking the cache goes to error silently (G10) |
| Handed off (C4b) | `SCRIBE_CHUNKING / SCRIBE_CREATED` | Backend returned a scribe, **from every path that creates one**: chunking, single-file uploads, background retry, recovery pop-up | `scribe_id` (column), template_ids | ✅ (client side) | 🔁 | 🟡 Chunking only. Single-file, background retry and recovery send nothing (G11, G12). **`HANDED_OFF` dropped.** |
| Abandoned | `RECORDING_LIFECYCLE / ABANDONED` | Local cache removed without hand-off | `reason`: user_deleted_paused / cleanup_sweep / storage_evicted / logout / **killed_before_mic** | ✅ | ⏸ | 🟡 `SCRIBE_CACHE_CLEANUP` (sweep only) |
| Open recordings | `SCRIBE_AUDIO_CACHE_HEALTH_V3` (`all_caches[]`) | 5 s after load, then every 30 min | add `recording_phase` per cache; `auto_paused` state | | ➕ (replaces the proposed `STILL_OPEN`) | ✅ Lists every cache with its state and uuid |
| App died mid-journey | `RECORDING_LIFECYCLE / TERMINATED_UNEXPECTEDLY` | **Next launch** finds the open-recording entry (§5.4) still there. A kill can't be logged when it happens. | `last_phase`, `last_seen_at`, `restored_as` (auto_paused), `parts_saved`, `duration_saved`, `prior_app_session_id`; P2: `exit_reason`, `crash_event_id` | | 🆕 (replaces `APP_KILLED_DETECTED` for the funnel) | 🟡 `APP_KILLED_DETECTED` only works after the mic starts; times are the last lifecycle change; no phase or reason |
| Note viewed / copied | `NOTE_COPIED`; `NOTE_VIEWED` | Provider opens or copies the note | `scribe_id` | | ✅ / 🆕 viewed | 🟡 `NOTE_COPIED` exists (no uuid); no "viewed" |

#### 5.2.1 C0: when the attempt and the recording id are created

- **`ATTEMPTED` fires before the active-recording check,** so "tapped while another recording was open" counts as an attempt. It fires after the double-tap lock, so double taps don't.
- **The Safari-on-iOS block** moves from the screen into the pre-checks, so it's covered.
- **The recording id is minted at ATTEMPTED,** in the right format for the mode (plain v4 for chunking, `scribe_audio_workflows_<hex>` for non-chunking).
  - It's written to the existing `recordingUuidProvider`; `initialize()` uses `cache?.uuid ?? provider ?? v4()` (today `chunking_recording_state_notifier.dart:379` mints it).
  - Resume keeps the existing id.
  - A blocked attempt keeps an id that never becomes a recording; a new tap gets a new id.
  - The id goes on every C0 event: `RECORDING_INITIATED`, `LOW_WARNING_DIALOG_SHOWN`, `RECORDING_MODE_SELECTED`.
- **Every exit of `startVisit()` sends exactly one closing event:**

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
| StartFailed / RecordingDidNotStart | `START_FAILED` (from the notifier; the controller doesn't send a duplicate) |
| StartedOk | carries on to `MIC_LIVE` |

#### 5.2.2 C1: where START_FAILED comes from

| Where the start dies | Code (`chunking_recording_state_notifier.dart`) | `error_code` example |
|---|---|---|
| Mic won't start on any device | `:798-813` | `mic_unavailable` |
| Recorder error before the first packet | `:493-543` | `recorder_error` (+ the real error) |
| Any other failure during start | `start()` catch `:1013-1059` | `cache_insert_failed`, `audio_format_unknown`, … |
| Mic started but no audio within 5 s | new watchdog after `startStream` | `no_audio_packets` |

On resume: the same places, with `on_resume: true`. A failed resume is terminal only if no later `MIC_LIVE` arrives for that id.

#### 5.2.3 Pause reasons

Every pause goes through `pauseParallelRecording()`. Add a `reason` argument, passed by each caller:

| Caller | Code | `reason` |
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

- **A kill is not a pause event.** It's reported at the next launch on `TERMINATED_UNEXPECTEDLY{restored_as: auto_paused}` (§5.4).
- **A kill while already paused** stays a user pause: the cache was `paused`, not `started`, so startup doesn't touch it.
- **The no-audio auto-pause is not an interruption.** It's `PAUSED{no_audio_auto}`, with `CONSECUTIVE_FLUSH_EMPTIES` as evidence. A phone call produces both `INTERRUPTED{call}` and `PAUSED{phone_call}`.

**Other notes:**
- **Auto-paused.** On launch, the app finds caches still `started` (the app died mid-recording) and rewrites them to `paused` with no event (`cache_repository.dart:1975`, `sqlite_migration_service.dart:270`). Change it to a new `auto_paused` state, reported on `TERMINATED_UNEXPECTEDLY{restored_as}` (no separate event). We still can't know *why* the app died, and we don't need to: only user pauses are intentional.
- **Partial submit exists.** When the manifest and trigger succeed while some chunks failed, the app sends `FINALIZE_PARTIAL` + `PARTIAL_SUBMIT` and keeps the cache in `error` for retry (`chunk_upload_provider.dart` `_handlePartialSuccess`). The funnel treats it as handed off with a `partial_submit` flag. Confirm with the recorder owner when this path fires.
- **Web, non-chunking.** The recording lives in an in-memory blob until it's stored at the end, so a page refresh loses it. It shows up as `TERMINATED_UNEXPECTEDLY{last_phase: recording}` on the next load (from the local-storage entry), or as lost.
- **Where to emit.** Send these from the planned "recording session" object (this quarter's recorder cleanup), not from scattered call sites. If chunking reaches 100% this quarter, instrument the chunking path in depth and the old file path minimally.

### 5.3 Backend events and state (normandy)

Backend journey events today all use tag `SCRIBE_JOURNEY`, with the name in **action** (`NORMANDY_WORKFLOWS_*`, `TRANSCRIPTION_CALLBACK_*`, `POST_NOTE_GENERATION_CALLBACK_*`). They're written via `track_scribe_event_from_object` (`normandy/app/utils/tracking.py:61`), which sets scribe_id and uuid = `scribe.uuid`.

The backend items below weren't reviewed on 11/5, except the link: **no separate `LINKED` event.**

| Change | Why | Today |
|---|---|---|
| ~~`SCRIBE_LIFECYCLE:LINKED`~~ **Dropped.** Optional: add `promoted_from_pre_chart` and `duplicate_of` to an existing backend event at trigger time (e.g. `NORMANDY_WORKFLOWS_DB_CHECKS_PASSED`) | The recording ↔ scribe link is already in `scribe.uuid` and on every backend event; only promotions and duplicates need a flag | ✅ Link via `scribe.uuid`; ❌ no flag |
| Emit `SCRIBE_LIFECYCLE:STATUS_CHANGED{from, to, reason_code, stage}` on **every** `task_status` change, including INCOMPLETE / ERROR / SYNC*. Also keep a `scribe_status_history` table. | Today `task_status` is overwritten and failures emit nothing | ❌ |
| Stage events for B1–B4: `AUDIO_RECEIVED`, `TRANSCRIPTION_DONE` / `_FAILED`, `NOTE_READY` / `NOTE_INCOMPLETE`, `DELIVERY_*`. **Reuse first:** most stages already have `SCRIBE_JOURNEY` events. | Clean stages for B1–B4 | 🟡 B1–B3 have `NORMANDY_WORKFLOWS_*` / `TRANSCRIPTION_CALLBACK_*` / `ALL_TASKS_COMPLETED`. Missing: transcription failed, async combine completed, delivery result (SYNCED / COPIED are `task_status` only). |
| **Replace hard deletes in `cleanup_scribe_data`** with a soft delete + a failure event `{stage: combine / upload, reason}` | Today a failed combine erases the scribe with no event, so it looks "lost" | ❌ Hard delete today; the backend never writes `SCRIBE_FAILED` |
| A stuck timeout: a scheduled job emits `SCRIBE_STUCK{stage, minutes}` once per scribe past N minutes at a stage | Stuck becomes an explicit state, not something to infer | 🟡 `SCRIBE_STUCK_AUTO_BACKFILL / TRIGGERED` fires when the 15-min alert backfills, not for every stuck scribe |
| Emit `ALL_TASKS_COMPLETED` **once** per scribe. Fix the `WORKLFOWS` typo (keep the old name as an alias). | Clean stage timestamps | 🟡 Exists; can repeat |
| Accept an `X-Recording-Id` header on all scribe endpoints and log it | Backend logs and traces become searchable per recording | ❌ |
| Mirror to StarRocks bronze: `scribe_status_history`, `transcriptions`, `ai_workflow_tasks`, `scribe_upload_sessions`, `scribe_ehr_syncs` | Lets the backend join happen in one warehouse | ❓ Check which are already mirrored |

### 5.4 Open-recording entry (kills, and "lost" as a positive finding)

A kill can't be logged when it happens. So the app keeps an **open-recording entry** on the phone for every recording that isn't finished:

1. **Saved at ATTEMPTED:** recording id, `phase = preflight`, time. The write is awaited, so a kill right after the tap is still caught.
2. **Phase updated at each step:** `initializing` (cache created) → `recording` (`MIC_LIVE`) → `paused` / `recording` → `uploading` (after stop). Each update stores the time, so `last_seen_at` is never older than the current step.
3. **Cleared on every normal ending:** `PREFLIGHT_BLOCKED`, `START_FAILED`, `DISCARDED`, `SCRIBE_CREATED`, `ABANDONED`.
4. **At the next launch, any entry still there means the app died mid-journey:** send `TERMINATED_UNEXPECTEDLY{last_phase, last_seen_at, restored_as, …}`, then clear it.
   - Test for "leftover entry", not today's "session id changed". That key collides with SessionService.
   - Web: the same entry in local storage, written at ATTEMPTED (today only on unload, and only while recording).

| last_phase | What happened | Outcome (§6.3) |
|---|---|---|
| `preflight` | App closed during the pre-checks | 8 Expected exit (gave up before starting) |
| `initializing` | Killed after the cache was created, before the mic started | 13 Abandoned (`killed_before_mic`); the empty cache is deleted. Today it's kept silently for 30 days. |
| `recording` / `paused` | Killed mid-recording | 14 Killed unexpectedly. Restored as `auto_paused`. |
| `uploading` | Killed during finalize | Not a recording loss; upload recovery picks it up (C4a) |

- **When did it die?** Bounded by the last `RECORDING_IN_PROGRESS` (every 30 s, phone time). Exact time and cause: the Sentry watchdog event tagged with the recording id (§5.6, AFEP-3003) and, on Android, `ApplicationExitInfo`.
- **Open recordings over time** come from the existing cache health ping (`SCRIBE_AUDIO_CACHE_HEALTH_V3`, every 30 min, listing every cache with its uuid and state), with `recording_phase` added. No new periodic event.
- Bhanu Mantri's periodic watchdog events can refresh `last_seen_at`.

With the entry, the cache health ping and `install_id`, the classifier can split lost into:

| Lost sub-outcome | Rule | Meaning |
|---|---|---|
| **Vanished on device** | The install came back (events with a later `app_session_id`), but the recording is neither in the cache health list nor terminated | A real app bug: the recording disappeared from local storage. Highest priority. |
| **Device not seen since** | No events from the install after the recording's last event, by the horizon | The provider hasn't reopened the app; the audio may still be on the device |
| **Telemetry gap** | `EVENTS_DROPPED` from the session | We lost the events, not necessarily the recording |

Safety check (daily job): the share of "lost" recordings (vanished / not seen since) that have a later event from the same `install_id`. If it is high, per-recording sequence numbers are added back to detect gaps.

### 5.5 Telemetry health events

- `EVENTS_DROPPED{count, oldest_ts}` when the retry cache gives up on events. ❌ Today rows past `maxRetryCount` are dropped silently.
- `EVENT_QUEUE_STATS` on each launch: queue size and oldest pending event. ❌
- Web: send unload-time events with `navigator.sendBeacon`, not localStorage + next load. ❌ (only the bundled Mixpanel script uses it)

### 5.6 Crash and error reporters

Set on **both** Crashlytics (custom keys) and Sentry (scope tags), and update on every transition. Already set today, Crashlytics only: `build_environment`, `build_mode`, `app_version`, `device_type`, plus user keys such as `provider_id` and `site_id`.

| Key | Value | Today |
|---|---|---|
| `app_session_id`, `install_id` | Always set | ❌ |
| `recording_id` | The open recording. Kept through pause, background, end and upload. Cleared only at that recording's terminal event, or when the next recording starts. **Not cleared on `reset()`** (today `recording_state_notifier.dart:1017, 1287` clears it before upload). | ❌ The recording uuid goes only to GCP log labels (`RecordingLogContext`), not to Crashlytics or Sentry |
| `recording_phase` | preflight / initializing / recording / paused / uploading / idle (same values as the open-recording entry, §5.4) | ❌ |
| `open_recording_count` | Number of open-recording entries, so crashes during background recovery are attributable | ❌ |
| `chunk_index` | Chunk being saved or uploaded at crash time ("crashed while saving chunk 48") | ❌ |

- **One place to set them.** `RecordingLogContext` (`scribe-mobile/lib/src/services/recording_log_context.dart`) becomes the single source. Its setters update the crash reporters, the event tracker and GCP log labels together. `DualCrashReporter.setCustomKey` (`dual_crash_reporter.dart:470`) must write Sentry tags too; today it writes Crashlytics only.
- **Native crashes are covered.**
  - Crashlytics stores custom keys natively, so they appear on native crashes.
  - Sentry's scope sync copies tags to the native SDKs, so native crashes, ANRs and iOS watchdog (OOM) terminations carry them. Watchdog terminations are reported on the next launch with the previous scope.
- **Handled errors.** Every `SCRIBE_FAILED` / `START_FAILED` / `RECORDING_FAILED` / `UPLOAD_FAILED` event carries the `sentry_event_id` of the exception it reported, so the timeline links to the stack trace.
- **OS exit reasons.** These are read on the next launch and attached to `TERMINATED_UNEXPECTEDLY` with the recording id from the open-recording entry:
  - Android `ApplicationExitInfo` (API 30+): reason, importance, PSS/RSS;
  - iOS MetricKit `MXAppExitMetric` / `MXCrashDiagnostic`.

  This is what separates **OOM** from crash from user swipe.

### 5.7 Error codes

Today errors cross the Flutter / native boundary as free-form strings, and web, Android and iOS each send different ones, which the app then groups for the UI. Every `error_code` in this contract comes from the **typed-error enum** being built in the recorder (typed error handling PR), one value per failure, the same on all platforms, plus `error_domain` (permission / mic / storage / sqlite / encryption / network / backend). Until that lands, the classifier maps today's strings with a lookup table.

## 6. Funnel definition

### 6.1 Cohort, horizon, exclusions

- **Cohort:** recordings whose `ATTEMPTED` (legacy: first start event) was *received* in the Mon–Sun UTC week.
- **Horizon:** each outcome is judged at **ATTEMPTED + 48 h**. Anything later is recorded as `late_resolution_at` and shown separately, but doesn't change the outcome. A week becomes final on Wednesday; Monday numbers are marked provisional.
- **Exclusions:** internal accounts (the current `filtered_accounts` rule) and platforms outside MOBILE_IOS / MOBILE_ANDROID / WEB_CHROME / WEB_APP.
- **Dimensions** (platform, browser, version, account, recording mode) are frozen at ATTEMPTED.

### 6.2 Stages

| # | Stage | Reached when (contract) | Legacy fallback (old app versions) |
|---|---|---|---|
| C0 | Attempted | `ATTEMPTED` | first `PARALLEL_RECORDING_STARTED` / `AUDIO_CACHE_START` (so C0 = C1 for legacy) |
| C1 | Mic live | `MIC_LIVE` | first `RECORDING_IN_PROGRESS` (or `RECORDING_STARTED` for very old builds) |
| C2 | Audio saved | first `CHUNK_ADDED` (with `chunk_index`, `bytes`); non-chunking `AUDIO_PERSISTED` | first `CHUNK_ADDED`; non-chunking: `FILE_UPDATED` with size > 0 (`FILE_ADDED` fires before the mic, so it doesn't count) |
| C3 | Ended | `PARALLEL_RECORDING_ENDED{reason}` | `PARALLEL_RECORDING_ENDED`; too-short: `SCRIBE_FAILED_TOO_SHORT` |
| C4a | All audio uploaded | `FINALIZE_SUCCESS` / `FINALIZE_PARTIAL` (chunking: all chunks retried, manifest sent); `UPLOAD_ATTEMPT` succeeded (non-chunking) | same events exist today for chunking; non-chunking: `AUDIO_CACHE_UPLOAD_ENDED` |
| C4b | Handed off (workflow triggered) | `SCRIBE_CHUNKING / SCRIBE_CREATED` (every path) | `SCRIBE_CREATED` (chunking), or a `scribe` row with this uuid |
| B1 | Audio received | `AUDIO_RECEIVED` | scribe row exists, not deleted |
| B2 | Transcribed | `TRANSCRIPTION_DONE` | `audio_length_in_seconds` set / `TRANSCRIPTION_CALLBACK_END` |
| B3 | Note ready | `NOTE_READY` | `processing_completed_timestamp` or `task_status` COMPLETED / SYNC* / MDS |
| B4 | Delivered | `DELIVERY_SUCCEEDED`, or `NOTE_COPIED` / `NOTE_VIEWED` | `task_status` SYNCED / COPIED / UPLOADED_BY_MDS |

### 6.3 Terminal outcomes (mutually exclusive, each with cited evidence)

The classifier picks the first matching rule. It stores **`outcome_evidence`**: the event id or row that decided it, so a reviewer can always see *why* a recording got its outcome.

| Priority | Outcome | Group | Deciding evidence |
|---|---|---|---|
| 1 | Delivered | ✅ success | `DELIVERY_SUCCEEDED` / `NOTE_COPIED` / `NOTE_VIEWED` |
| 2 | Note ready, not delivered by horizon | ✅ success | `NOTE_READY` |
| 3 | Delivery failed | 🔴 backend | last `DELIVERY_FAILED`, no later success |
| 4 | Incomplete: not enough info | 🟡 incomplete | `NOTE_INCOMPLETE{not_enough_info}` |
| 5 | Incomplete: no speech (split ≥30 s audio) | 🟡 incomplete | `NOTE_INCOMPLETE{no_speech}` / `TRANSCRIPTION_FAILED{NO_SPEECH, TOO_SHORT}` |
| 6 | Backend failed | 🔴 backend | `SCRIBE_FAILED` / `STATUS_CHANGED{to: ERROR}` / `TRANSCRIPTION_FAILED{CORRUPT, OTHER}` |
| 7 | Backend stuck | 🔴 backend | `SCRIBE_STUCK`, or no terminal backend event by horizon |
| 8 | Expected exit | ⚪ excluded from rates | `PREFLIGHT_BLOCKED` (except low_battery / low_storage, which count as failures), `DISCARDED`, `TERMINATED_UNEXPECTEDLY{last_phase: preflight}` |
| 9 | Start failed (incl. resume failed) | 🔴 client | `START_FAILED`, with no later successful resume |
| 10 | Recording failed | 🔴 client | `RECORDING_FAILED` |
| 11 | Upload stuck (ended, never handed off) | 🔴 client | last `FINALIZE_FAILED` / `FINALIZE_TIMEOUT` / `MANIFEST_FAILED` / `TRIGGER_FAILED` / `UPLOAD_FAILED`, or the cache still `error` / `uploading` in the latest cache health ping |
| 12 | Paused by user, never resumed | 🟡 waiting on user | last `PARALLEL_RECORDING_PAUSED{reason: user / user_pip / user_tour}` (or `phone_call` / `interruption`), still open with no end |
| 13 | Abandoned before handoff | 🔴 client | `ABANDONED` (split by reason, incl. `killed_before_mic` = `TERMINATED_UNEXPECTEDLY{last_phase: initializing}`) |
| 14 | Killed unexpectedly | 🔴 client | `TERMINATED_UNEXPECTEDLY{last_phase: recording / paused}` (restored as `auto_paused`), or a crash event with this `recording_id`; never handed off. `exit_reason` (crash / low_memory / anr / user_swipe / os / page_unload / unknown) is an attribute for breakdowns, **not** separate outcomes: we can't reliably know why the app died, and every reason is unexpected. |
| 15 | Open at horizon | 🟡 pending | still listed in a cache health ping (`SCRIBE_AUDIO_CACHE_HEALTH_V3`) within 24 h of the horizon |
| 16 | Lost: telemetry gap | ⚪ data quality | §5.4 rule. Checked first, so missing events are never mistaken for a vanished recording. |
| 17 | Lost: vanished on device | 🔴 client | §5.4 rule |
| 18 | Lost: device not seen since | 🟡 client | §5.4 rule |

A recording that was killed, stuck or failed and **later handed off** gets its backend outcome (1–7) and keeps the earlier trouble as a flag (§6.4). That's the existing recovery logic, made explicit.

**Headline rates:**
- **Reliability rate** = outcomes 1–2 / (all − 8 − 16).
- **Lost rate** = 17 + 18 (17 shown on its own).
- The other OKR rates are filters over the same table (§6.5).

### 6.4 Flags per recording (not exclusive)

`ever_paused`, `ever_auto_paused`, `ever_interrupted` (+ source), `ever_resume_failed`, `partial_submit`, `ever_persist_error` (+ step), `ever_backgrounded`, `ever_upload_failed` (+ attempt count), `ever_killed`, `recovered_after_kill`, `recovered_after_stuck`, `crashed_during` (+ crash ids), `memory_pressure`, `audio_discrepancy` (client length − server length > 10 s), `duplicate_scribe`, `late_resolution`, `clock_skew` (client_ts vs received_at > 5 min), `telemetry_gap`, `ever_mic_lost` (any `MIC_LOST`), `mic_silent` (`silent_seconds` above threshold, e.g. ≥ 30 s, or peak level below the floor), `low_input` (average level below the floor), `clipped` (`clipped_pct` above threshold). Thresholds live in the job, so they change without an app release. `mic_silent` splits "incomplete: no speech" (outcome 5) into a mic problem vs. nobody talking.

### 6.5 Today's OKR metrics as filters over `recording_outcome`

| Metric | Filter | Goal |
|---|---|---|
| % Lost Scribes | outcome ∈ {17, 18} / cohort excluding 8 and 16 | 0.01% |
| % Unexpected Recording Failures | outcome ∈ {9, 10} / same denominator | 0.01% |
| % Stuck in Cache | outcome = 11 / same. Today's metric also counts paused caches; those now split into 12 (user) and 14 (auto-paused after a kill). | — |
| Recovery rate | `recovered_after_stuck` / (`recovered_after_stuck` + outcome 11) | 99% |
| % Audio Discrepancy | `audio_discrepancy` / reached B2 | 0.5% |
| % Incomplete | outcome ∈ {4, 5} / reached B1 | TBD (baseline ~0.22%) |
| Reliability rate (new) | §6.3 | TBD (proposed 99.5%) |
| Kills per 1k recordings (new) | `ever_killed` / cohort, broken down by `exit_reason` when known | TBD |
| Recordings affected by crashes (new) | `crashed_during` / cohort | TBD |

## 7. Crashes: every crash traced to a session, and to a recording when there is one

### 7.1 What exists today (reused)

GCP project `athelas-scribe-mobile`, BigQuery dataset `unified_monitoring`, with Grafana reading from it:
- **Crashlytics export.** Raw crash events land in `firebase_crashlytics.*`, as both batch and realtime tables. The export already includes `custom_keys`: `provider_id`, `site_id` and `app_version` are on every iOS crash. Any new key flows through automatically.
- **Daily scheduled queries** `firebase_{sync,users,metrics}_{android,ios}`, which fill `source_issues`, `issue_users` and `source_metrics` (hourly counts).
- **Cloud Run `sentry-ingestion`.** It loads fatal Sentry events (daily 00:00) into the same tables. A daily matching job (00:30) links Sentry and Crashlytics reports of the same crash in `canonical_issues` / `issue_mappings`.
- **Health on 2026-11-02:**
  - All jobs succeeded.
  - Firebase fatal counts match the published weekly report (10/19–10/25: Android 88, iOS 66).
  - 7 days since 10/05 are off by 1–3 events, because late batch rows are missed by the 25 h window.

### 7.2 Changes

| Change | Detail |
|---|---|
| **Event-level crash table** | New scheduled queries `firebase_crash_events_{android,ios}` (7-day look-back, MERGE on event_id) plus a new event-level pass in `sentry-ingestion` (fatal and ANR; tags `recording_id`, `recording_phase`, `chunk_index`, `app_session_id`, `install_id`) → `unified_monitoring.crash_events`. One row per crash, keeping `canonical_issue_id`, release, device, `memory.used` / `memory.free`, `process_state` and the source URL. **Every** crash gets a row, not only those during recordings. |
| **Push to StarRocks** | Daily copy of `crash_events` into StarRocks. A few thousand rows a week, ids and metadata only, no patient data. All per-recording and per-session joins happen in StarRocks, where Grafana reads them. |
| **Our own crash-free rate** | `app_session_id` is on every event and every crash, so **crash-free sessions = sessions with no crash event / all sessions**, computed from our own data. Each crashed session can be drilled into. The Sentry Sessions API (session tracking is on: `scribe-mobile/lib/main.dart:250`) and the Firebase console stay as cross-checks. |
| **Bot screening** | Android Play-review, emulator and test-device crashes are filtered in SQL using `device_model` and the existing rules. They're flagged, not deleted, so they can still be traced. |
| **Pipeline fixes** | Label Sentry fatals `crash` instead of `error`. De-duplicate `ingestion_watermarks`. Fix the schedule comments, which say 15 min and 4 h; both run daily. |

### 7.3 How a crash shows up in the view

- **Crash during a recording** → it's on the recording's timeline and sets `crashed_during`. If the recording was never handed off, its outcome is 14 (Killed unexpectedly) with `exit_reason = crash`.
- **Crash during upload or background recovery** (`recording_phase = uploading`, or `open_recording_count > 0`) → it's linked to that recording, or recordings, through the open-recording entries (§5.4).
- **Crash outside a recording** (login, Intune, settings) → it's linked to its app session and install. It counts in crash-free sessions and in the crash band.
- **Crash band:** each crash issue shows **sessions affected, recordings affected, and recordings lost**. Issues are ranked by recordings lost, then by sessions. Every number can be drilled into.

## 8. Data model

All per-recording and per-session tables live in **StarRocks**. Grafana reads them directly; funnel events also go to Mixpanel through a Pub/Sub subscriber (design: `docs/20261105-funnel-logging-design.md`).

| Table | Grain | Built from | Purpose |
|---|---|---|---|
| `recording_trace` | One row per signal per recording | Lifecycle events, legacy events (normalized), backend events / status history, `crash_events`, Sentry handled-error ids | **The timeline.** Columns: `recording_id`, `ts`, `seq`, `source` (app / backend / crash), `kind`, `detail` (codes only), `app_session_id`, `link` (deep link to the source) |
| `recording_outcome` | One row per recording | `recording_trace` | Cohort, frozen dimensions, stage timestamps C0–B4, outcome + `outcome_evidence`, flags, `contract_version`, `classifier_path` (contract / legacy) |
| `session_outcome` | One row per app session | Events grouped by `app_session_id`, `crash_events` | Platform, version, start/end, crashed (+ crash ids), recordings started in it. Feeds crash-free rates. |
| `crash_events` | One row per crash | §7.2 | Crash band, joins |
| `funnel_daily`, `funnel_weekly`, `sessions_daily` | Day/week × platform × browser × version × outcome or stage | The outcome tables | Fast tiles and charts in Grafana (StarRocks). `RECORDING_OUTCOME` events go to Mixpanel for the outcome report. |

**Build:**
- A daily job rebuilds every recording whose ATTEMPTED falls in the last 3 days (horizon + margin), plus anything that received a late event. Older rows are frozen, except for the `late_resolution` columns.
- Scheduler: a StarRocks async materialized view, dbt or Airflow. Decision for the data platform team.
- Each run scans only those days.
- The same job sends one `RECORDING_OUTCOME` event per recording (and again only if it changes) to Mixpanel.

## 9. Views

**Where each view lives** (decided 11/5): the **funnel chart** in Mixpanel; **everything else** (tiles, outcomes, crash band, breakdowns, recording list, timeline, session view, data quality) in **Grafana** on StarRocks. Every cell is a link:
1. **Headline tiles:** reliability, the OKR metrics, incomplete, crash-free sessions per platform, kills per 1k. Each shows goal, 🟢/🔴, `trendFor` arrow, 5-week sparkline, and `fmtRate` with raw counts.
2. **Funnel (Mixpanel):** stages C0–B4 by recording, 48 h conversion window, with breakdowns by platform, version, path and reason.
3. **Outcomes:** 18 outcomes × 5 weeks, grouped by the four phases (§1). **Flags:** same layout.
4. **Crash band:** top issues by recordings lost / sessions affected, and crash-free sessions per platform.
5. **Breakdowns:** platform + browser, version.
6. **Recording list.** Opens from any cell, pre-filtered. Columns: recording_id, account id, platform, browser, version, cohort day, outcome, evidence, flags, last event. CSV export.
7. **Recording timeline.** Opens from a list row, or from a search box by `recording_id` / `scribe_id` / account. It merges app, backend and crash entries in order, each linked to its source (Sentry event, Crashlytics issue, scribe id).
8. **Session view.** Same pattern for crashed sessions.
9. **Data quality strip:**
   - share of recordings on the contract;
   - telemetry gap rate;
   - share of crashes with `app_session_id`;
   - share of in-recording crashes with `recording_id`;
   - share of scribes with a matching app `SCRIBE_CREATED` (and vice versa).

**Alerts (Grafana):** all alert rules on the StarRocks outcome tables. Every alert links to the Grafana recording list for that platform, day and outcome.

## 10. Rollout and soundness

### 10.1 Two classifier paths during rollout

- Old app versions don't send the contract, so the classifier picks a path for each recording:
  - **contract path:** the recording has `ATTEMPTED`;
  - **legacy path:** v1-style inference from today's events.
- `classifier_path` is stored, and every view can be split by it.
- The legacy path only produces outcomes 1–11, 13 and 14, plus lost without the sub-splits. It can't tell a user pause from an auto-pause, so it can't produce 12.
- Rates are reported **per path and combined**. That way a mix shift as people upgrade isn't mistaken for a reliability change.

### 10.2 Invariants, checked on every build (failures alert)

| Invariant | Catches |
|---|---|
| Sum of outcomes = cohort size, for every week and platform | Classifier holes or double counting |
| Every outcome has non-null `outcome_evidence` | Unexplained classifications |
| Every `SCRIBE_CREATED` has a scribe row with the same uuid and `scribe_id` within 1 h | Identity breaks between app and backend |
| No `recording_id` with more than 1 terminal client event | Contract violations |
| Recordings with an `EVENTS_DROPPED` from their session < 0.5%; lost recordings with a later event from the same `install_id` stays low | Event loss |
| Crashes with `recording_phase ≠ idle` and null `recording_id` ≈ 0 | Code paths that skip the setter |
| Crash `recording_id`s that exist in `recording_outcome` ≈ 100% | Id mismatch (e.g. today's `scribe_audio_legacy_*` fallback) |

### 10.3 Reconciliation before switching the OKR to the new numbers

Run the old scorecard and the new funnel side by side for 4 weeks. Explain every difference by category, for example:
- hard-deleted backend failures moving out of lost;
- pre-charted scribes counted as recovered (LLM-21067);
- the 48 h horizon.

Switch the OKR headline when **≥ 95% of recordings are on the contract path** and the invariants have held for 2 consecutive weeks.

### 10.4 Validation against support tickets (acceptance test)

Support tickets are the third data source, next to app events and crash reports. The funnel is only useful if it explains what providers actually report. So:
- Take the last 10–15 days of FE-related support tickets (the weekly triage list).
- For each ticket, find the recording id (from the account, time and scribe id in the ticket) and look up its outcome and timeline.
- **Pass:** every ticket lands in exactly one outcome, and the timeline shows the stage where it failed. Tickets that land in "success", "lost: telemetry gap", or can't be matched to a recording are logging gaps: each becomes an item on the gap list.
- Repeat after each P0 / P1 release.
- Ids only: ticket text has patient data, so the mapping table stores the ticket link, recording id and outcome, never the message.

## 11. Phasing

| Phase | Scope | Why this order |
|---|---|---|
| **P0 (now): instrument + legacy funnel** | **App:** §5.1 common fields, §5.2 lifecycle events (new events + fields on existing ones), §5.4 open-recording entry, §5.6 crash keys, removing patient names (G14). **Backend:** pre-chart / duplicate flag, `STATUS_CHANGED` + history, soft-delete instead of hard delete, `SCRIBE_STUCK`. **Data:** `recording_outcome` on the legacy path from current tables; Grafana recording list and timeline; Mixpanel approval; existing metric fixes (dead `RECORDING_STARTED`, LLM-21067 recovery fix). | App changes take a release cycle to reach users, so they go first. Meanwhile the legacy funnel gives value and a baseline. **Dependencies:** typed errors (§5.7); the recording-session object and periodic watchdog events (§5.2, §5.4); recording id on Sentry + Crashlytics (meeting action item). |
| **P1: contract path + crashes + alerts** | Contract classifier; `crash_events` (Crashlytics + Sentry event level) pushed to StarRocks; `session_outcome` and our own crash-free rate; `recording_trace` merging all sources; backend stage events (`AUDIO_RECEIVED`, `TRANSCRIPTION_*`, `NOTE_*`, `DELIVERY_*`); bronze mirrors; BigQuery aggregates + Grafana alerts; data quality strip. | Needs P0 builds in the field |
| **P2: depth** | OS exit reasons (ApplicationExitInfo / MetricKit) → `exit_reason` on outcome 14 and on `ever_killed`; `NOTE_VIEWED` / `NOTE_COPIED`; `X-Recording-Id` in backend logs; web `sendBeacon`; switch the OKR at ≥ 95% contract coverage; retire the old scorecard. | Most valuable once the core is trusted |

## 12. Tool decision (decided 11/5)

| Need | Tool | Why |
|---|---|---|
| **Funnel chart** (management: where recordings drop off, getting better?) | **Mixpanel** | Purpose-built funnel and drop-off views; Pengyao asked for a Mixpanel-style view |
| **Everything else**: headline tiles, outcomes, crash band, breakdowns, recording list, timeline, session view, data quality, alerts | **Grafana** on StarRocks | Already the alerting tool; reads the per-recording tables directly; replaces the planned Retool page |
| **Warehouse** | **StarRocks** | `scribe_events` already lands there through the Pub/Sub topic, next to the scribe mirror |

**How events reach Mixpanel:** the app is not changed to call Mixpanel.
1. `scribe_events` publishes every event to the existing Pub/Sub topic.
2. A new subscriber forwards only the funnel events, with `$insert_id = client_event_id` and the phone's timestamp.
3. The daily outcome job adds one `RECORDING_OUTCOME` per recording.

The app's own Mixpanel tap events are not part of the funnel. Full design: `docs/20261105-funnel-logging-design.md`.

**Still open:** Mixpanel approval for this data (BAA / security) and Group Analytics on the plan (§13).

## 13. Risks and open questions

| # | Question / risk | Proposed answer |
|---|---|---|
| 1 | Who owns Grafana alert routing to Slack? | Mobile platform / reliability on-call. Confirm. |
| 2 | Which scheduler builds the tables, and how do pushes happen (BigQuery → StarRocks crash rows, StarRocks → BigQuery aggregates)? | Data platform team's choice. Both pushes are small daily batches. |
| 3 | Monday provisional, Wednesday final: is that OK for the weekly review? | Yes. Mark Monday numbers provisional. |
| 4 | Goals for the new metrics | Set after 4 weeks of baseline. Placeholder: reliability ≥ 99.5%. |
| 5 | Moving the uuid mint to tap-to-record changes when the id exists. Any backend assumptions about uuid format (`scribe_audio_workflows_<hex>` vs v4)? | Keep accepting both formats. New recordings use v4 from tap. |
| 6 | Event volume for open recordings | No new periodic event: open recordings come from the existing 30-min cache health ping (§5.4). |
| 7 | iOS gives no reliable user-swipe signal; MetricKit arrives daily and can be delayed | `exit_reason = user_swipe` is best-effort on iOS; everything unclear is `unknown`. The outcome (14) doesn't depend on it. |
| 8 | Is "Incomplete: no speech" with ≥ 30 s of audio a failure? | Tracked separately. Decide after baseline. |
| 9 | Pre-chart restore on failure (`restore_pre_chart_draft`) could move the uuid off the scribe | The pre-chart flag (§5.3) and `STATUS_CHANGED{to: PRE_CHARTED, reason: restored}` keep the history. Verify in the backend design. |
| 10 | Patient data in the timeline | Codes and ids only (R7). The timeline never shows payload text. |
| 11 | Does the backend need extra metadata (beyond §5.3) for the funnel? | Raised on 11/2, not settled. Decide when the recorder gap doc is done. |
| 12 | When does the partial-submit path (`FINALIZE_PARTIAL`) fire, and do the missing chunks ever reach the backend? | Confirm with the recorder owner. Until then: handed off + `partial_submit` flag, cross-checked with audio discrepancy. |
| 13 | Is "auto-paused" a new cache state or a flag on `paused`? | Proposed: new state `auto_paused`, reported on `TERMINATED_UNEXPECTEDLY{restored_as}`. Recorder owner's call. Also decide whether auto-paused recordings upload automatically or prompt the provider. |
| 14 | Does auto-stop at 3 h run on chunking? `autoStop()` has no caller found and calls `stop()`, which is empty on chunking | Confirm with the app team; `PARALLEL_RECORDING_ENDED{reason: auto_stop}` depends on it |
| 15 | `ATTEMPTED` on the start flow: does any start path bypass `StartVisitController.startVisit()`? | Welcome tour and Smart Update use it; check any other entry point before rollout |
| 16 | Is Mixpanel approved for this data (BAA / security)? | Check before sending anything. Only ids, codes, platform and version are sent. |
| 17 | Does the Mixpanel plan include Group Analytics (needed to count recordings, not accounts)? | If not, a separate Mixpanel project with distinct_id = `recording_id`. |
| 18 | Mixpanel volume: ~365k attempts/week × ~8 forwarded events ≈ 3M events/week | Check against the plan before go-live. |
| 19 | Is the scribe-event Pub/Sub publish flag on in production for every platform? | Confirm; the Mixpanel subscriber depends on it. |

## 14. Owners

| Area | Owner | Notes |
|---|---|---|
| Visualization, data model (`recording_outcome`, `recording_trace`), Grafana views, Mixpanel setup | Arthur Fung | Get Pengyao Chen's input on the management view |
| Crash metadata and pipeline (`crash_events`, event-level Sentry pass) | Arthur Fung with Prokash Sarkar | Prokash owns the `sentry-ingestion` scripts |
| App logging gaps (§5.1–5.7) and a doc of what's captured, what's missing and how to read each metric | Recorder engineer (11/2 meeting) | §5 is the proposed input to that doc; they own the final event list |
| Periodic watchdog events | Bhanu Mantri | Can refresh the open-recording entry's `last_seen_at` (§5.4) |
| Backend events (§5.3), Pub/Sub → Mixpanel subscriber, keeping `client_event_id` | TBD | |

Estimate from the meeting: about 1–2 weeks to close the main gaps and see first data. Next step: the 11/3 regroup to finalize the approach and split the work.

## Appendix A: legacy events used by the fallback classifier

| Contract event | Legacy equivalent(s) today |
|---|---|
| ATTEMPTED | `RESOURCE_MONITORING:RECORDING_INITIATED` (random uuid, so not joinable) → use first `RECORDING_INITIALIZED` / `AUDIO_CACHE_START` |
| MIC_LIVE | first `RESOURCE_MONITORING:RECORDING_IN_PROGRESS` (`RECORDING_STARTED` on builds before Mar 2026) |
| Audio saved | first `SCRIBE_AUDIO_CACHE_SYNC_V2:CHUNK_ADDED`; non-chunking: `FILE_UPDATED` (not `FILE_ADDED`, which fires before the mic) |
| Ended | `SCRIBE_JOURNEY:PARALLEL_RECORDING_ENDED` (too-short: `SCRIBE_FAILED_TOO_SHORT`) |
| START_FAILED / RECORDING_FAILED | `SCRIBE_FAILED` (ON_START / Open), `START_RECORDING_ERROR`, `MID_RECORDING_ERROR` (the two are misclassified today), `AUDIO_CACHE_*_FAILED`, `SCRIBE_DB_READY_FAILED` |
| DISCARDED | `SCRIBE_FAILED_TOO_SHORT`, `PAUSED_CACHE_DELETE:*` |
| UPLOAD_FAILED | `SCRIBE_UPLOAD_ERROR:*`, `CHUNK_UPLOAD_FAILED`, `SCRIBE_CHUNKING:FINALIZE_FAILED` / `TRIGGER_FAILED` |
| Handed off | `SCRIBE_CHUNKING:SCRIBE_CREATED` (chunking), `AUDIO_CACHE_UPLOAD_ENDED` (native), or a `scribe` row by uuid |
| ABANDONED | `SCRIBE_CACHE_CLEANUP`, `AUDIO_CACHE_DELETED` without handoff |
| Open recordings | `SCRIBE_AUDIO_CACHE_HEALTH_V3.all_caches[]` snapshots (same source on both paths) |
| TERMINATED_UNEXPECTEDLY | `APP_LIFECYCLE:APP_KILLED_DETECTED` (+ `ORPHANED_AUDIO_FILE_RECOVERED`) |
| Backend stages | `scribe.task_status`, `error_message` prefix, `audio_length_in_seconds`, `processing_completed_timestamp`, `NORMANDY_WORKFLOWS_*` events |

## Appendix B: code references

- App event builder: `scribe-mobile/lib/services/tracking/event_tracker_service.dart:233`.
- Start flow and pre-flight exits: `lib/src/features/visits/providers/start_visit_controller.dart:58-163` (`startVisit`), results handled in `visits/views/visit_info_screen.dart:2579` (`_handleVisitStartResult`).
- Recording uuid minted: `chunking_recording_state_notifier.dart:379`; saved for kill detection at `:955`; first audio packet: stream listener `:878`.
- Kill detection: `main/providers/app_lifecycle_provider.dart:328-363`, conditions in `services/lifecycle/app_lifecycle_service.dart:134-186`; started → paused on launch: `cache_repository.dart:1975`, `sqlite_migration_service.dart:270`.
- Recording uuid context: `lib/src/services/recording_log_context.dart`.
  - Set at `native_recording_state_notifier.dart:217` and `chunking_recording_state_notifier.dart:380`.
  - Cleared at `recording_state_notifier.dart:1017, 1287`.
- Crash reporter: `lib/src/services/dual_crash_reporter.dart` (`setCustomKey` is Crashlytics-only, :470). Sentry init: `lib/main.dart:180-300`.
- Backend trigger + pre-chart promotion: `normandy/app/api/v1/scribe/workflows/services.py:581-740`.
- Hard delete: `app/api/v1/scribe/services.py:7040-7082` (`cleanup_scribe_data`).
- Status update: `workflows/services.py:4274-4490`.
- Stuck alert: `openai/alerts.py:556-636`.
- Crash pipeline: GCP `athelas-scribe-mobile`. BigQuery `unified_monitoring`. Scheduled queries `firebase_*`. Cloud Run `sentry-ingestion` (source `~/source/services_sentry-ingestion_*`). Cloud Scheduler `sentry-ingestion-sync`, `sentry-canonicalize`.
