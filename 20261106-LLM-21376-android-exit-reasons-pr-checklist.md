# LLM-21376 — Android exit reasons on `APP_KILLED_DETECTED` — PR checklist

**Ticket.** [LLM-21376](https://linear.app/commure/issue/LLM-21376). PRD: `docs/20261106-android-exit-reasons-prd.md` (scribe-mobile, local).

**Branch.** `arthurfung/llm-21376-android-record-why-the-previous-process`, off `develop`.

**Problem.** An OS kill on Android leaves no exception, no Sentry event and no Crashlytics crash. `APP_LIFECYCLE / APP_KILLED_DETECTED` fires on the next launch, but `wasKilled` only means "new session while a recording UUID was in prefs", so swipe-aways, crashes and memory kills all look the same.

**Fix.** On API 30+ (minSdk is 26), read `ActivityManager.getHistoricalProcessExitReasons` on the next cold launch, match the previous process by pid, and add the reason to the existing `APP_KILLED_DETECTED` payload. No new event.

**Changes from the PRD.**
- F9 `TERMINATED_UNEXPECTEDLY` / F20 `RECORDING_OUTCOME` are only designed ([funnel logging design](20261105-funnel-logging-design.html)), not in the code yet. Use `APP_KILLED_DETECTED`, which already fires at that point, is written local-first, and carries the recording UUID.
- There's no 30 s `last_seen_at` heartbeat: `last_active_timestamp` is only written on lifecycle changes. So match by **pid**, not by a time window.

## Commit 1 — Kotlin: `getLastExitInfo`

- [ ] `MainActivity.kt` `SYSTEM_HEALTH` handler: add `getLastExitInfo(pid: Int)`.
- [ ] Below `Build.VERSION_CODES.R` → `result.success(null)`.
- [ ] `getHistoricalProcessExitReasons(packageName, pid, 1)`; if empty → `null`.
- [ ] Return a map: `reason` / `importance` (mapped to the strings in the table below), `timestamp`, `pss_kb`, `rss_kb`, `status`.
- [ ] Never return `description` or `traceInputStream`.
- [ ] Logic goes in `SystemMonitor.kt` next to `getMemoryInfo`, so the handler stays a one-line dispatch.

| `getReason()` | `exit_reason` |
|---|---|
| `REASON_LOW_MEMORY` | `low_memory` |
| `REASON_SIGNALED` | `signaled` |
| `REASON_CRASH` | `crash` |
| `REASON_CRASH_NATIVE` | `crash_native` |
| `REASON_ANR` | `anr` |
| `REASON_USER_REQUESTED` / `REASON_USER_STOPPED` | `user_requested` |
| `REASON_DEPENDENCY_DIED` | `dependency_died` |
| `REASON_EXIT_SELF` | `exit_self` |
| anything else | `other` |

| `getImportance()` | `exit_importance` |
|---|---|
| `FOREGROUND` | `foreground` |
| `VISIBLE` | `visible` |
| `FOREGROUND_SERVICE` / `SERVICE` | `service` |
| `CACHED` | `cached` |
| anything else | `other` |

## Commit 2 — Store the pid

- [ ] `AppLifecycleService.saveAppState`: also write `pid` (`dart:io`) under a new `last_pid` key. Android only; web has no `dart:io`, so keep it behind the existing non-web path / conditional import (run `platform-safety`).
- [ ] `checkForAppKill`: read `last_pid` into `AppKillCheckResult.lastPid`; clear it with the recording UUID.
- [ ] `last_pid` is a plain int, so SharedPreferences is fine (no PHI).

## Commit 3 — Dart: read the exit info and add it to `APP_KILLED_DETECTED`

- [ ] `ISystemHealthMonitorService.getLastExitInfo(int pid)` → `ExitInfo?` (small model with `fromMap`, next to `memory.dart`). Non-Android → `null`.
- [ ] `_checkForAppKill` (`app_lifecycle_provider.dart`), Android only: call it with a **1 s timeout**; timeout, error, null pid or null result → `exit_reason: 'unknown'`. Never block startup or throw.
- [ ] Add `exit_reason`, `exit_importance`, `exit_at`, `exit_pss_kb`, `exit_rss_kb` to the payload. Leave the iOS / web payloads unchanged.
- [ ] `low_memory` only: one `Sentry.captureMessage('Android low memory kill', level: warning)` with tags `exit_reason:low_memory`, `exit_importance`, and `recording_uuid` (same tag name as AFEP-3003). Don't await it on the startup path.
- [ ] No exit info on `APP_RESUMED_AFTER_BREAK` (same process, nothing to read).

## Tests

- [ ] `app_lifecycle_service_test.dart`: `saveAppState` writes `last_pid`; `checkForAppKill` returns it and clears it on kill.
- [ ] `system_health_monitor` test: mock channel → map parsed to `ExitInfo`; `null` → `null`; `PlatformException` → `null`.
- [ ] `app_lifecycle_provider_test.dart`, Android kill:
  - [ ] exit info → payload has all five fields.
  - [ ] channel returns null / throws / times out → `exit_reason: 'unknown'`, event still sent.
  - [ ] `low_memory` → Sentry message with the tags; `signaled` → no Sentry message.
- [ ] iOS kill → payload has no `exit_*` keys.
- [ ] Kotlin: if unit tests aren't set up under `android/app/src/test`, cover the mapping by hand in Verify instead.

## Verify

- [ ] `flutter analyze` and `dart format` clean on changed files.
- [ ] `flutter test` on the changed test files.
- [ ] Patch coverage ≥ 80% on changed `lib/` lines.
- [ ] Pixel (API 30+), start a recording, then:
  - [ ] `adb shell am kill com.athelas.scribe` (in background) → relaunch → event `exit_reason` (expect `signaled` or `low_memory`).
  - [ ] Swipe away from recents → relaunch → `user_requested` / `signaled` / `other`; note which one.
  - [ ] Forced low memory (`adb shell am send-trim-memory` doesn't kill; open heavy apps or use a low-RAM emulator) → `low_memory`, Sentry message shows up.
- [ ] Repeat on a Samsung; write down what each case reports (PRD open item 1).
- [ ] API 28/29 emulator → `exit_reason: 'unknown'`, no crash.
- [ ] Check that sentry-android (sentry_flutter 9.20) isn't already sending these exits (it reads ApplicationExitInfo for ANRs) → no duplicate Sentry events.
- [ ] PR description: Linear link, Impacted Platforms: Android only. Note for data: new `exit_*` fields on `APP_KILLED_DETECTED`. The weekly memory-kill query is a follow-up.
