{% raw %}
# Funnel logging design: spec and sequence diagrams

2026-11-05 · Draft · Local only.

**Related:**
- `docs/20261102-reliability-funnel-prd.md` (§5 event contract, §6 outcomes);
- `docs/20261105-recording-journey-event-index.md` (today's events, gaps G1–G19, tasks T1–T39);
- `docs/20261105-funnel-questions.md` (what the funnel must answer).

**Decisions behind this design (11/5):**

| Topic | Decision |
|---|---|
| Event store | `scribe_events`. No new table. |
| Funnel fields | In the payload JSON. No new columns. |
| Path to Mixpanel | scribe_events → the existing Pub/Sub topic → a new subscriber → Mixpanel |
| Sent to Mixpanel | Funnel events only (§3) |
| Funnel unit | The recording: `recording_id` as a Mixpanel group key; distinct_id = account |
| Outcomes | A daily job in StarRocks classifies each recording and sends one `RECORDING_OUTCOME` event |
| Duplicates | `client_event_id` → Mixpanel `$insert_id`; the phone's `timestamp` is the event time |
| Grafana | Everything except the funnel chart: one ops dashboard (stage panels, flags, crashes) with a drill-down table of recording ids. Timeline and alerts are deferred. |
| Warehouse | StarRocks (scribe_events already lands there via the same topic) |
| App's own Mixpanel events | Not part of the funnel; they stay for product analytics |
| Scope | All paths at once: mobile chunking, mobile single-file, web app, Chrome extension |
| Compliance | **Mixpanel approval to confirm** before anything is sent. Only ids, codes, platform and version are sent. |

---

## 1. Architecture

```mermaid
flowchart LR
  APP["App: mobile, web, extension<br/>(scribe-mobile)"] -->|"batch every 30 s<br/>/tracking/batch_scribe_events"| PG[("scribe_events<br/>Postgres")]
  BE["Backend: normandy<br/>track_scribe_event"] --> PG
  PG -->|"publish after commit<br/>(existing, behind a flag)"| PS{{"Pub/Sub topic<br/>scribe_events"}}
  PS --> SR[("StarRocks<br/>scribe_events + scribe mirror")]
  PS --> SUB["NEW: Mixpanel subscriber<br/>funnel events only"]
  SUB -->|"/import, $insert_id = client_event_id<br/>time = phone timestamp"| MP["Mixpanel<br/>funnel view"]
  SR --> JOB["NEW: daily outcome job<br/>48 h horizon"]
  JOB --> RO[("StarRocks<br/>recording_outcome")]
  JOB -->|"RECORDING_OUTCOME<br/>one per recording"| MP
  SR --> GF["Grafana<br/>ops dashboard +<br/>drill-down table"]
  RO --> GF
```

**What exists today:**
- **App batching:** events are written to local SQLite and uploaded every 30 s (`lib/services/tracking/batching_event_tracker_service.dart`).
- **Backend writes:** both write paths, single (`track_scribe_event`, `normandy/app/utils/tracking.py:101`) and batch (`track_scribe_events_bulk`, `:175`), publish every event after the commit (`publish_scribe_event`, `normandy/app/utils/scribe_event_publisher.py:71`), gated by `is_publish_scribe_event_enabled`. The topic already feeds StarRocks.

**What's new:**
- **The subscriber:** filters to the funnel events (§3), maps each to a Mixpanel event (§5) and sends it with the `/import` API. `/import` accepts old timestamps, which matters because phones can hold events for days.
- **Delivery is best-effort:** a failed send goes to a retry queue and never blocks the Postgres write.
- **The outcome job:** daily, over recordings attempted in the last 3 days, plus any recording with a late event.
  - It writes `recording_outcome` in StarRocks.
  - It sends one `RECORDING_OUTCOME` per recording, and again only if the outcome changes.
  - It derives the mic flags (§2.2) and writes `outcome`, `drop_stage` and the flags onto the Mixpanel **group profile** for the `recording_id`, so any funnel step can be broken down by them (§5).
  - It reports the share of lost recordings that have a later event from the same `install_id` (the telemetry-gap safety check).
- **Grafana:** reads StarRocks over the MySQL protocol.

**Backend change needed:**
- **`client_event_id`:** the app sends it on every event (`event_tracker_service.dart:234-284`), but `ScribeEventTracking` (`normandy/app/api/v1/scribe/models.py:1319`) has no column for it and drops it. Keep it inside `payload` (no schema change), so the subscriber can dedupe repeat sends, e.g. `APP_KILLED_DETECTED` sent twice.

---

## 2. Event contract

### 2.1 Common payload fields (every funnel event)

| Field | Value | Set by |
|---|---|---|
| `recording_id` | Same value as the `uuid` column. Created at `ATTEMPTED`. | app; backend uses `scribe.uuid` |
| `app_session_id` | One per app launch / page load | app |
| `install_id` | One per install / browser profile, kept on the device | app |
| `client_event_id` | Random per event, kept across retries | app (exists); backend must keep it in payload |
| `contract_version` | `1` | app |
| `path` | `chunking` / `single_file` | app |
| `on_resume` | true when the event belongs to a resume | app |

**Already on every row:** `device_type`, `browser_name`, `version`, `scribe_account_id`, `scribe_id`, `timestamp` (phone time), `created_at` (server time).

**Ordering:** by the phone's `timestamp`, with `created_at` as the tiebreak. There is no per-recording sequence number. Mixpanel doesn't need one: it orders by `time` and dedupes by `$insert_id`.

**Telemetry gaps:** outcome 16 relies on `EVENTS_DROPPED` and the `install_id` check (did the phone come back?). The outcome job also reports the share of "lost" recordings (17 / 18) that have a later event from the same `install_id`. If that share is high, add a per-recording counter back.

**No patient data** in any field. Today `patient_name` is sent in four payloads and has to be removed first (T21).

### 2.2 Funnel events (forwarded to Mixpanel)

**Change:**
- 🆕 new event;
- ➕ field added to an existing event;
- 🔁 existing event, sent from more paths;
- ✅ unchanged.

| # | Stage | Tag / action | Key payload | Change |
|---|---|---|---|---|
| F1 | C0 | `RECORDING_LIFECYCLE / ATTEMPTED` | entry_point, recording_mode | 🆕 |
| F2 | C0 | `RECORDING_LIFECYCLE / PREFLIGHT_BLOCKED` | reason | 🆕 |
| F3 | C1 | `RECORDING_LIFECYCLE / MIC_LIVE` | ms_since_attempted, input_device | 🆕 |
| F4 | C1 | `RECORDING_LIFECYCLE / START_FAILED` | error_code, error_domain | 🆕 |
| F5 | C2 | `SCRIBE_AUDIO_CACHE_SYNC_V2 / CHUNK_ADDED` (**first per recording only**) | chunk_index, bytes | ➕ |
| F5b | C2 | `RECORDING_LIFECYCLE / AUDIO_PERSISTED` (single-file / web single-file) | storage, bytes | 🆕 |
| F6 | C2 | `SCRIBE_JOURNEY / PARALLEL_RECORDING_PAUSED` | reason | ➕ |
| F7 | C2 | `RECORDING_LIFECYCLE / INTERRUPTED` | source | 🆕 |
| F7b | C2 | `RECORDING_LIFECYCLE / MIC_LOST` | source (bluetooth_disconnect / route_change / mic_taken / unknown), recovered, ms_without_audio | 🆕 |
| F8 | C2 | `RECORDING_LIFECYCLE / RECORDING_FAILED` | stage, error_code | 🆕 |
| F9 | C2 / K | `RECORDING_LIFECYCLE / TERMINATED_UNEXPECTEDLY` | last_phase, last_seen_at, restored_as | 🆕 |
| F10 | C3 | `SCRIBE_JOURNEY / PARALLEL_RECORDING_ENDED` | reason, recording_length | ➕ 🔁 |
| F10b | C3 / K | `RECORDING_LIFECYCLE / AUDIO_QUALITY` (**once per recording**, at ENDED, or at TERMINATED_UNEXPECTEDLY with the last heartbeat value) | silent_seconds, peak_dbfs, avg_dbfs, clipped_pct, input_device | 🆕 |
| F11 | C3 | `RECORDING_LIFECYCLE / DISCARDED` | reason | 🆕 |
| F12 | C4a | `SCRIBE_CHUNKING / FINALIZE_SUCCESS`, `FINALIZE_PARTIAL`, `FINALIZE_FAILED`, `FINALIZE_TIMEOUT` | stage, error_class, chunks_failed | ✅ |
| F12b | C4a | `RECORDING_LIFECYCLE / UPLOAD_FAILED` (single-file) | http_status, error_code, attempt_n | 🆕 |
| F13 | C4a | `SCRIBE_AUDIO_CACHE_SYNC_V2 / AUDIO_CACHE_ERROR` | reason | 🔁 |
| F14 | C4b | `SCRIBE_CHUNKING / SCRIBE_CREATED` | scribe_id, path | 🔁 |
| F15 | C4b | `RECORDING_LIFECYCLE / ABANDONED` | reason | 🆕 |
| F16 | B1 | `SCRIBE_JOURNEY / NORMANDY_WORKFLOWS_SCRIBE_JOURNEY_START` | — | ✅ (backend) |
| F17 | B2 | `SCRIBE_JOURNEY / NORMANDY_WORKFLOWS_TRANSCRIPTIONS_AND_OCRS_COMPLETED` | — | ✅ (backend) |
| F18 | B3 | `SCRIBE_JOURNEY / NORMANDY_WORKFLOWS_ALL_TASKS_COMPLETED` (first only) | — | ✅ (backend) |
| F19 | B1–B4 | `SCRIBE_LIFECYCLE / STATUS_CHANGED` | from, to, reason_code | 🆕 (backend) |
| F20 | — | `RECORDING_LIFECYCLE / RECORDING_OUTCOME` | outcome (1–18), outcome_evidence, drop_stage, flags | 🆕 (outcome job) |

**Flags the outcome job derives from the raw numbers** (thresholds live in the job, so they change without an app release):
- `mic_silent`: `silent_seconds` above the threshold (e.g. ≥ 30 s), or peak level below the floor;
- `low_input`: average level below the floor;
- `clipped`: `clipped_pct` above the threshold;
- `ever_mic_lost`: any `MIC_LOST`.

**Not forwarded (they stay in scribe_events for Grafana):**
- 30-second resource pings;
- the rolling audio level carried on the 30 s `RECORDING_IN_PROGRESS` heartbeat (cumulative `silent_seconds`, `peak_dbfs`, `avg_dbfs`, `clipped_pct`, `input_device`); only the final value goes out, as `AUDIO_QUALITY`;
- every chunk after the first;
- upload retries;
- cache health;
- diagnostics.

These feed the timeline, not the funnel.

**Subscriber filter:** the exact `(tag, action)` pairs above. For F5 and F18, forward only the first occurrence per `recording_id`. The subscriber keeps a small "seen" set keyed by `recording_id`, or the Mixpanel funnel's "first time" setting does it.

---

## 3. Per-path spec

Code paths are in `scribe-mobile/lib/src/features/` unless noted. Line numbers are at `c87c9fe7a`.

### 3.1 Shared start (all paths)

| Event | Where | Notes |
|---|---|---|
| ATTEMPTED + recording id created | top of `visits/providers/start_visit_controller.dart` `startVisit()` (:58), after the double-tap lock | Written to `recordingUuidProvider`. Format: v4 for chunking, `scribe_audio_workflows_<hex>` for single-file. Open-recording entry saved (`phase: preflight`). |
| PREFLIGHT_BLOCKED | one switch at the end of `startVisit()` | 8 reasons (PRD §5.2.1). The Safari-iOS check moves in from `visit_info_screen.dart:2540`. |
| `RESOURCE_MONITORING / RECORDING_INITIATED` | `start_visit_controller.dart:75` | Changed to a single sample with the recording id (not forwarded) |

### 3.2 Mobile chunking (iOS, Android)

| Stage | Event | Where |
|---|---|---|
| C1 | MIC_LIVE | first packet in the stream listener, `record/providers/chunking_recording_state_notifier.dart:878` |
| C1 | START_FAILED | `:798-813`, `:493-543`, `start()` catch `:1013`, new 5 s watchdog |
| C2 | first CHUNK_ADDED (+ chunk_index, bytes) | `record/data/cache_repository.dart:1397` |
| C2 | PAUSED reason | `pauseParallelRecording()` callers (PRD §5.2.3) |
| C2 | INTERRUPTED | Android call `record/providers/recording_state_notifier.dart:855`; iOS interruption begin `:955`; device change `record/providers/device_change_mixin.dart:107` |
| C2 | MIC_LOST | Route change / headset or Bluetooth disconnect in `device_change_mixin.dart:107`; the stream listener (`chunking_recording_state_notifier.dart:878`) when packets stop for more than a few seconds mid-recording; `recovered` set when packets resume |
| C2 | Audio level sampling | In the same stream listener: per packet, update cumulative `silent_seconds`, `peak_dbfs`, `avg_dbfs`, `clipped_pct`; copy onto the 30 s `RECORDING_IN_PROGRESS` heartbeat |
| C3 | AUDIO_QUALITY | Next to ENDED (`chunking_recording_state_notifier.dart:1762`); on kill, sent at the next launch from the last heartbeat value |
| K | TERMINATED_UNEXPECTEDLY | next launch, replacing the check in `main/providers/app_lifecycle_provider.dart:328`; started → `auto_paused` in `cache_repository.dart:1975` |
| C3 | ENDED reason | `chunking_recording_state_notifier.dart:1762`; too-short path `recording_state_notifier.dart:1403-1459` |
| C4a | FINALIZE_* | `record/services/chunking_analytics.dart` (exists) |
| C4a | AUDIO_CACHE_ERROR reason | `record/providers/chunk_upload_provider.dart` `_updateCacheState` (:465) |
| C4b | SCRIBE_CREATED | `chunk_upload_provider.dart:1875` (exists); add to `record/services/background_upload_retry_service.dart` (success) and the orphan recovery flow |

### 3.3 Mobile single-file

| Stage | Event | Where / difference |
|---|---|---|
| C1 | MIC_LIVE | first amplitude sample (`record/providers/native_recording_state_notifier.dart`, `amplitudeSubscription`) |
| C2 | AUDIO_PERSISTED | first time the file has data; `FILE_ADDED` doesn't count (it fires in initialize, `:397`) |
| C2 | MIC_LOST, audio level | Same fields as chunking. Level comes from the same `amplitudeSubscription` samples as MIC_LIVE; MIC_LOST when amplitude samples stop mid-recording |
| C3 | AUDIO_QUALITY | Next to ENDED (`recording_state_notifier.dart:1563`) |
| C3 | ENDED | `recording_state_notifier.dart:1563` |
| C4a | UPLOAD_ATTEMPT / UPLOAD_FAILED | `record/providers/cache_upload_provider.dart` `upload` (:175); today only `SCRIBE_UPLOAD_ERROR` |
| C4b | SCRIBE_CREATED | **new on this path**: after the trigger succeeds (`cache_upload_provider.dart`, before `AUDIO_CACHE_UPLOAD_ENDED` :622) |

### 3.4 Web app (WEB_APP) and Chrome extension (WEB_CHROME)

The same Flutter code as mobile, built for web, so the chunking and single-file rules above apply. Differences:

| Topic | Web behaviour |
|---|---|
| Kills | No OS kill; a page refresh or tab close is the "kill". Open-recording entry in **localStorage** written at ATTEMPTED (today only on unload while recording, `app_lifecycle_provider.dart:179-202`). TERMINATED_UNEXPECTEDLY on next page load with `last_phase`. |
| Pre-checks | Duplicate-tab check active; storage warning skipped |
| Interruptions | No OS interruption events. Device change via `MIC_CHANGE_*`, which also raises `MIC_LOST` when the input goes away mid-recording. |
| Audio level | Same sampling as mobile. The web keeps the running values in memory and in the localStorage open-recording entry, so `AUDIO_QUALITY` can still be sent after a refresh. |
| Tab state | `WEB_LIFECYCLE / TAB_FROZEN`, `TAB_UNFROZEN` (timeline only) |
| Single-file web | Audio is in memory until stop, so a refresh loses it. AUDIO_PERSISTED only at stop. |
| Extension | `SCRIBE_JOURNEY / EXTENSION_MINIMIZED_DURING_RECORDING` (timeline only) |
| Unload events | Send with `navigator.sendBeacon` (T22) |

### 3.5 Backend (normandy)

| Stage | Event | Where |
|---|---|---|
| B1 | `NORMANDY_WORKFLOWS_SCRIBE_JOURNEY_START` (exists) | `scribe/workflows/controllers.py:806` |
| B2 | `NORMANDY_WORKFLOWS_TRANSCRIPTIONS_AND_OCRS_COMPLETED` (exists) | `workflows/services.py:287` |
| B3 | `NORMANDY_WORKFLOWS_ALL_TASKS_COMPLETED` (exists; first only) | `scribe/workflows/services.py:4583` |
| B1–B4 | `SCRIBE_LIFECYCLE / STATUS_CHANGED` (new) | every `task_status` write (`update_scribe_status` :4360, `scribe_ehr_services.py:142`, `scribe/services.py:10393`, …) |
| — | `client_event_id` kept in payload (new) | `app/utils/tracking.py` `track_scribe_events_bulk` (:175) |

---

## 4. Sequence diagrams

Shorthand:
- **App** = scribe-mobile.
- **SE** = scribe_events (Postgres → Pub/Sub → StarRocks).
- **MP** = Mixpanel, via the subscriber.

Only funnel events (F#) go to MP.

### 4.1 Normal recording (chunking)

```mermaid
sequenceDiagram
  participant App
  participant SE as scribe_events
  participant MP as Mixpanel
  participant BE as Backend
  App->>SE: ATTEMPTED (recording id created, entry phase preflight)
  SE->>MP: F1
  App->>SE: MIC_LIVE (first audio packet, entry phase recording)
  SE->>MP: F3
  App->>SE: first CHUNK_ADDED (chunk_index 1, bytes)
  SE->>MP: F5
  Note over App: more chunks every 30 s (timeline only)
  App->>SE: PARALLEL_RECORDING_ENDED (reason user)
  SE->>MP: F10
  App->>SE: FINALIZE_SUCCESS
  App->>BE: trigger workflow
  BE-->>App: scribe id
  App->>SE: SCRIBE_CREATED (scribe_id), entry cleared
  SE->>MP: F14, F12
  BE->>SE: NORMANDY_WORKFLOWS_SCRIBE_JOURNEY_START ... ALL_TASKS_COMPLETED
  SE->>MP: F16, F17, F18
  BE->>SE: STATUS_CHANGED (to SYNCED)
  SE->>MP: F19
  Note over SE,MP: daily job: RECORDING_OUTCOME (1 Delivered)
```

### 4.2 Blocked by a pre-check

```mermaid
sequenceDiagram
  participant App
  participant SE as scribe_events
  participant MP as Mixpanel
  App->>SE: ATTEMPTED (entry saved)
  SE->>MP: F1
  Note over App: mic permission denied
  App->>SE: PREFLIGHT_BLOCKED (reason permission_denied), entry cleared
  SE->>MP: F2
  Note over SE,MP: RECORDING_OUTCOME (8 Expected exit)
```

### 4.3 Start failed, then resume failed

```mermaid
sequenceDiagram
  participant App
  participant SE as scribe_events
  participant MP as Mixpanel
  App->>SE: ATTEMPTED
  App->>SE: START_FAILED (error_code no_audio_packets, after 5 s watchdog)
  SE->>MP: F1, F4
  Note over App: provider taps record again: new attempt, new recording id
  App->>SE: ATTEMPTED (new id) ... MIC_LIVE ... PAUSED (reason user)
  Note over App: later: resume
  App->>SE: ATTEMPTED (on_resume true, same id)
  App->>SE: START_FAILED (on_resume true, error_code mic_unavailable)
  SE->>MP: F1, F4
  Note over SE,MP: first id: 9 Start failed. Second id: 9 if no later MIC_LIVE
```

### 4.4 Paused by the user, then resumed

```mermaid
sequenceDiagram
  participant App
  participant SE as scribe_events
  participant MP as Mixpanel
  App->>SE: PARALLEL_RECORDING_PAUSED (reason user), entry phase paused
  SE->>MP: F6
  Note over App: provider comes back
  App->>SE: ATTEMPTED (on_resume true)
  App->>SE: MIC_LIVE (on_resume true), entry phase recording
  SE->>MP: F1, F3
  Note over SE,MP: if never resumed by the horizon: 12 Paused by user
```

### 4.5 Phone call

```mermaid
sequenceDiagram
  participant OS
  participant App
  participant SE as scribe_events
  participant MP as Mixpanel
  OS->>App: call started
  App->>SE: INTERRUPTED (source call)
  App->>SE: PARALLEL_RECORDING_PAUSED (reason phone_call)
  SE->>MP: F7, F6
  OS->>App: call ended
  App->>SE: INTERRUPTION_ENDED (timeline only)
  Note over App: provider resumes: ATTEMPTED and MIC_LIVE (on_resume)
```

### 4.6 Killed mid-recording, recovered at the next launch

```mermaid
sequenceDiagram
  participant OS
  participant App
  participant SE as scribe_events
  participant MP as Mixpanel
  participant SN as Sentry
  App->>SE: ... MIC_LIVE, CHUNK_ADDED (entry phase recording)
  Note over App: RECORDING_IN_PROGRESS every 30 s = last sign of life
  OS->>App: memory kill (nothing can be logged)
  Note over App: next launch
  App->>SN: watchdog kill (tagged with recording id)
  App->>SE: TERMINATED_UNEXPECTEDLY (last_phase recording, restored_as auto_paused)
  SE->>MP: F9
  App->>SE: recovery: FINALIZE_SUCCESS, SCRIBE_CREATED
  SE->>MP: F12, F14
  Note over SE,MP: outcome from the backend (e.g. 1 Delivered), flags ever_killed, recovered_after_kill
```

### 4.7 Killed before the mic started

```mermaid
sequenceDiagram
  participant App
  participant SE as scribe_events
  participant MP as Mixpanel
  App->>SE: ATTEMPTED (entry phase preflight)
  Note over App: cache created, entry phase initializing
  Note over App: app killed before the first audio packet
  Note over App: next launch
  App->>SE: TERMINATED_UNEXPECTEDLY (last_phase initializing)
  App->>SE: ABANDONED (reason killed_before_mic), empty cache deleted
  SE->>MP: F9, F15
  Note over SE,MP: 13 Abandoned. If last_phase were preflight: 8 Expected exit
```

### 4.8 Upload stuck, background retry recovers

```mermaid
sequenceDiagram
  participant App
  participant SE as scribe_events
  participant MP as Mixpanel
  App->>SE: PARALLEL_RECORDING_ENDED
  App->>SE: FINALIZE_SKIPPED (offline)
  App->>SE: AUDIO_CACHE_ERROR (reason offline)
  SE->>MP: F10, F13
  Note over App: hours later: background retry (every 2 h)
  App->>SE: BACKGROUND_CHUNK_RETRY CACHE_SUCCESS (timeline only)
  App->>SE: SCRIBE_CREATED (new on this path)
  SE->>MP: F14
  Note over SE,MP: outcome from the backend, flag recovered_after_stuck
```

### 4.9 Lost

```mermaid
sequenceDiagram
  participant App
  participant SE as scribe_events
  participant JOB as Outcome job
  App->>SE: ATTEMPTED, MIC_LIVE, CHUNK_ADDED ...
  Note over App,SE: then nothing for this recording
  JOB->>SE: at horizon: any later event from the same install_id?
  alt no later event from the phone
    JOB->>SE: RECORDING_OUTCOME (18 Device not seen since)
  else phone came back
    JOB->>SE: was the recording in a later cache health list, or terminated?
    alt not listed, no cleanup or discard event
      JOB->>SE: RECORDING_OUTCOME (17 Vanished on device)
    else listed
      JOB->>SE: RECORDING_OUTCOME (12, 14 or 15: still on the phone)
    end
  end
  Note over JOB: checked first: EVENTS_DROPPED from the session gives 16 Telemetry gap
  Note over JOB: safety check: share of 17 / 18 with a later event from the same install_id
```

### 4.10 Single-file recording

```mermaid
sequenceDiagram
  participant App
  participant SE as scribe_events
  participant MP as Mixpanel
  participant BE as Backend
  App->>SE: ATTEMPTED (id scribe_audio_workflows_hex)
  App->>SE: MIC_LIVE (first amplitude sample)
  App->>SE: AUDIO_PERSISTED (first data in the file)
  App->>SE: PARALLEL_RECORDING_ENDED (reason user)
  SE->>MP: F1, F3, F5b, F10
  App->>BE: upload file + trigger
  BE-->>App: scribe id
  App->>SE: SCRIBE_CREATED (new on this path)
  SE->>MP: F14
```

### 4.11 Silent mic the whole recording

```mermaid
sequenceDiagram
  participant App
  participant SE as scribe_events
  participant MP as Mixpanel
  participant BE as Backend
  participant JOB as Outcome job
  App->>SE: ATTEMPTED, MIC_LIVE (packets arrive, but near-silent)
  SE->>MP: F1, F3
  Note over App: heartbeat every 30 s carries silent_seconds, peak_dbfs, avg_dbfs
  App->>SE: PARALLEL_RECORDING_ENDED, AUDIO_QUALITY (silent_seconds high, peak very low)
  SE->>MP: F10, F10b
  App->>BE: upload + trigger
  App->>SE: SCRIBE_CREATED
  BE->>SE: NOTE_INCOMPLETE (no_speech)
  JOB->>MP: RECORDING_OUTCOME (5 Incomplete: no speech), flag mic_silent
  Note over JOB,MP: mic_silent splits "no speech" into mic problem vs nobody talked
```

### 4.12 Mic dropped mid-recording

```mermaid
sequenceDiagram
  participant OS
  participant App
  participant SE as scribe_events
  participant MP as Mixpanel
  App->>SE: ATTEMPTED, MIC_LIVE, CHUNK_ADDED
  SE->>MP: F1, F3, F5
  OS->>App: Bluetooth headset disconnected (route change)
  App->>SE: MIC_LOST (source bluetooth_disconnect)
  SE->>MP: F7b
  alt packets resume on the phone mic
    App->>SE: MIC_LOST update (recovered true, ms_without_audio)
    Note over SE,MP: recording continues. Flag ever_mic_lost; outcome from how it ends
  else no audio comes back
    App->>SE: PARALLEL_RECORDING_ENDED (reason user), AUDIO_QUALITY (silent_seconds high)
    Note over SE,MP: flag ever_mic_lost + mic_silent; audio is shorter than the visit (audio_discrepancy)
  end
```

### 4.13 Incomplete scribe linked to the device audio

```mermaid
sequenceDiagram
  participant SE as scribe_events
  participant BE as Backend
  participant JOB as Outcome job
  participant MP as Mixpanel
  BE->>SE: NOTE_INCOMPLETE (not_enough_info or no_speech)
  JOB->>SE: read AUDIO_QUALITY, MIC_LOST for the same recording_id
  alt mic_silent or ever_mic_lost
    JOB->>MP: outcome 4 / 5 + flag mic_silent / ever_mic_lost (device cause)
  else normal levels
    JOB->>MP: outcome 4 / 5, no mic flag (nobody talked, or a short visit)
  end
```

---

## 5. Mixpanel setup

- **Events:** one Mixpanel event per funnel event. Name = action, e.g. `ATTEMPTED`, `MIC_LIVE`, `SCRIBE_CREATED`.
- **Properties on every event:** platform (device_type + browser), app_version, path, on_resume, plus the payload fields from §2.2. Never free text.
- **Identity:** distinct_id = `scribe_account_id`. Group key `recording_id` (Group Analytics), so funnels count **recordings**.
- **Time:** the phone's `timestamp`; `$insert_id = client_event_id`. Sent with `/import`, which accepts events older than 5 days.
- **Main funnel (by recording):**
  1. ATTEMPTED (excluding `on_resume`)
  2. MIC_LIVE
  3. first CHUNK_ADDED / AUDIO_PERSISTED
  4. PARALLEL_RECORDING_ENDED
  5. SCRIBE_CREATED
  6. NORMANDY_WORKFLOWS_ALL_TASKS_COMPLETED
  7. STATUS_CHANGED to SYNCED / COPIED / MDS
- **Conversion window:** 48 h, the same as the outcome horizon.
- **Breakdowns known when the event is sent:** platform, app_version, path, PREFLIGHT_BLOCKED reason, START_FAILED error_code, PAUSED reason, TERMINATED last_phase, `AUDIO_QUALITY` input_device.
- **One view for everything:** the same funnel, with a "break down by" setting. No breakdown shows the totals (near real time). Breaking down by outcome or flag explains each drop-off.
- **Breakdown by final outcome (group profile):** the outcome is only known 48 h after the attempt, so it can't sit on the funnel's events. The daily job writes `outcome`, `drop_stage`, `mic_silent`, `low_input`, `clipped`, `ever_mic_lost` and the other flags onto the `recording_id` group profile. In the funnel report, break down by those group properties.
  - Each step's drop-off then splits into reasons, e.g. between ENDED and SCRIBE_CREATED: upload stuck, lost (device not seen since), abandoned, paused by user.
  - Recordings younger than 48 h have no profile values yet and show as "unknown".
  - Needs Group Analytics (open item 2).
- **Not included:** a separate outcome-mix report. The Grafana ops panels and the weekly report keep that view.

---

## 6. Grafana (StarRocks)

Grafana is **one ops dashboard**, read from `recording_outcome` (filled by the daily job). Mixpanel keeps the funnel; Grafana shows the daily health of each stage.

**Common to every panel**
- **Filters:** date range, platform, app version, account.
- **Numbers:** a percentage with the raw count, e.g. "0.4% (12 / 3,100)". No "per 1,000".
- **Provisional days:** the last 2 days are shaded, because an outcome needs 48 h to settle.
- **Stage panels** are one stacked-bar template (one bar per day, one segment per outcome) repeated for each stage. The query is the same; only the outcome list changes:
  ```sql
  SELECT date(attempted_at) AS day, outcome_name, COUNT(*) AS n
  FROM recording_outcome
  WHERE attempted_at >= $from AND outcome IN ($stage_outcomes)
    AND platform IN ($platform) AND app_version IN ($version)
  GROUP BY day, outcome_name
  ```
- **Click-through:** clicking a bar segment, or a crash issue, filters the drill-down table at the bottom (below) to that day and outcome.

**Panels**

| # | Panel | Chart | Question it answers | Outcomes / fields | Rate (denominator) |
|---|---|---|---|---|---|
| 1 | Top line: reliability | Line | Of all recordings, how many became a note the provider got, and is it getting better? | 1 delivered + 2 note ready | (1 + 2) ÷ (all − 8 − 16) |
| 2 | Top line: telemetry gap | Line, beside #1 | How much can I trust the reliability number? | 16 telemetry gap | 16 ÷ all |
| 3 | Start | Stacked bar | How many attempts never started, and why? | 9 start failed; 8 blocked, split by reason | each ÷ all |
| 4 | Record | Stacked bar | What went wrong while recording? | 10 recording failed; 14 killed, never handed off; 12 paused, never resumed | each ÷ all |
| 5 | End and upload | Stacked bar | Which recordings ended but were never handed to the backend? | 11 upload stuck; 13 abandoned; 15 open at horizon | each ÷ all |
| 6 | Backend | Stacked bar | What happened after the scribe was created? Did the provider get a usable note? | 2 ready not delivered; 3 delivery failed; 4 and 5 incomplete (5 split by `mic_silent`); 6 backend failed; 7 backend stuck | each ÷ all |
| 7 | Lost | Stacked bar | How many recordings vanished without a trace, and which kind? | 17 vanished on device; 18 device not seen since | each ÷ all |
| 8 | Flags | Line, several series | Where is trouble happening even when the recording was later saved? Are mic problems rising? | `mic_silent`, `ever_mic_lost`, `ever_killed`, `recovered_after_kill`, `recovered_after_stuck` | each ÷ all |
| 9 | Crashes | Bar | Which crashes cost us recordings? | per crash issue (`crash_events`, T32 joined to `recording_outcome`): sessions affected, recordings affected, recordings lost | ranked by recordings lost, not crash count |

Outcomes 1–18 each appear in exactly one panel, except 1 (delivered), which is only the numerator of panel 1. Panel 9 needs crashes tagged with `recording_id` and `app_session_id` (T20, T32), so it waits on that work.

**Drill-down table** (under the panels): one row per recording from `recording_outcome` for the clicked day and outcome, or crash issue.
- Columns: `recording_id`, attempted time, platform, app version, account, outcome, flags.
- Source: `recording_outcome` only. No join to `scribe_events`.
- Answers "show me the recordings that ended as 'device not seen since' on this day".

**Deferred (not in this phase):**
- a per-recording timeline;
- Slack alerts on these numbers.

Until the timeline exists, `outcome_evidence` on each row is the only per-recording explanation. When the timeline is built, filter `scribe_events` by `uuid` and `created_at` first, never on payload (payload parsing is what timed out in Retool on 11/3).

---

## 6b. Work to do

**App (scribe-mobile)**
- [ ] Common fields on every event: `recording_id`, `app_session_id`, `install_id`, `client_event_id`, `contract_version`, `path`, `on_resume`
- [ ] New events: `ATTEMPTED`, `PREFLIGHT_BLOCKED`, `MIC_LIVE`, `START_FAILED`, `TERMINATED_UNEXPECTEDLY`, `ABANDONED`
- [ ] `MIC_LOST` for a mic that drops mid-recording
- [ ] Audio level sampling on the 30 s heartbeat; `AUDIO_QUALITY` once at the end
- [ ] `SCRIBE_CREATED` on every path (single-file, background retry)
- [ ] Web: localStorage open-recording entry + `sendBeacon` on unload

**Backend (normandy)**
- [ ] Keep `client_event_id` in the payload
- [ ] `SCRIBE_LIFECYCLE / STATUS_CHANGED` events

**Pipeline**
- [ ] Pub/Sub → Mixpanel subscriber (filter, `/import`, retry)
- [ ] Daily outcome job: outcome 1–18, flags (`mic_silent`, `low_input`, `ever_mic_lost`…), `RECORDING_OUTCOME`, write outcome + flags to the `recording_id` group profile, lost-with-later-event safety check

**Mixpanel**
- [ ] Approval (BAA / security), Group Analytics confirmed, project + group key
- [ ] One funnel with breakdowns by outcome, flag, platform, version

**Grafana**
- [ ] Ops dashboard (stage panels, flags, crashes) + drill-down table of recording ids; timeline and alerts deferred

---

## 7. New tasks (added to the task list)

| # | Task | Owner | Phase |
|---|---|---|---|
| T35 | Pub/Sub → Mixpanel subscriber: filter the funnel events, map, send with `/import` and `$insert_id`, retry queue | Backend (TBD) | P0 |
| T36 | Keep `client_event_id` (in payload) on every app event | Backend (TBD) | P0 |
| T37 | Mixpanel approval (BAA / security), project, Group Analytics on `recording_id` | Arthur | P0 |
| T38 | Daily outcome job in StarRocks → `recording_outcome` + `RECORDING_OUTCOME` events; includes the lost-with-later-event safety check | Arthur | P1 |
| T39 | Grafana ops dashboard (stage panels, flags, crashes) + drill-down table of recording ids (replaces the Retool page). Timeline and alerts deferred. | Arthur | P0 |
| T40 | Client audio-level sampling (rolling on the heartbeat) + `AUDIO_QUALITY` at the end | App (TBD) | P0 |
| T41 | `MIC_LOST` event (route change, headset disconnect, packets stop mid-recording) | App (TBD) | P0 |
| T42 | Outcome job: derive mic flags (`mic_silent`, `low_input`, `clipped`, `ever_mic_lost`) and write outcome + flags to the `recording_id` group profile | Arthur | P1 |
| T43 | Mixpanel funnel with breakdown by group-profile outcome and flags | Arthur | P1 |

## 8. Open items

1. **Mixpanel approval:** is Mixpanel covered for this data (BAA)? Nothing is sent until confirmed.
2. **Mixpanel plan:** is Group Analytics available? If not, use distinct_id = `recording_id` in a separate Mixpanel project.
3. **Volume:** about 365k attempts a week × ~8 forwarded events, roughly 3M events a week. Check against the Mixpanel plan.
4. **Pub/Sub flag:** is `is_publish_scribe_event_enabled` on in production for all platforms?
5. **Grafana on StarRocks:** confirm the data source and access (Tailscale for viewers).
6. **Payload queries:** applies when the timeline is built (deferred). Keep Grafana queries filtered on tag / uuid / time first. If timeline queries are still slow, revisit promoting a few fields to columns.
7. **Group-profile breakdown:** confirm Mixpanel can break a funnel step down by a group profile property on the plan, and how long a profile update takes to show.
8. **Volume:** `MIC_LOST` and `AUDIO_QUALITY` add about 1–2 events per recording (roughly +0.4–0.7M a week). Re-check item 3.
9. **Privacy:** confirm audio level numbers and `input_device` are acceptable to send. No audio content is sent.
10. **PRD follow-up:** done 11/6. `recording_seq` removed; `MIC_LOST`, `AUDIO_QUALITY` and the mic flags added to PRD §5.2 and §6.4. The event index (T19) still mentions `recording_seq`.

{% endraw %}
