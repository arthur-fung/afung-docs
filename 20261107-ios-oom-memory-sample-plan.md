# iOS OOM — measure the recording memory gap

Related: `docs/20261107-ios-oom-memory-sample-gap.html`
Issue: [SCRIBE-MOBILE-B0](https://athelas-monitoring.sentry.io/issues/SCRIBE-MOBILE-B0)

## Problem
During recording, `internal_mb` climbs about 300–500 MB/min and the process dies near 3 GB. The audio path cannot be that climb: 16 kHz 16-bit mono is about 2 MB/min, the Dart packet list is flushed about every 30 seconds, and SQLite's page cache is about 2 MB.

The current sample cannot say whether the rest is the Dart heap or native anonymous memory. It also stops at pause and at End Visit, so growth in those gaps is not measured.

## Add to `recording_heap_sample`
- `dart_heap_mb` — Dart new space + old space, from the Dart runtime, so it works in release. Compare it to `internal_mb` on the same sample.
- `phase` — `recording`, `paused`, or `after_end`.
- Keep `malloc_in_use_mb` in the breadcrumb. It is already collected (native malloc, not the Dart heap) and was missing from the sample that was reviewed.

How to read the next kill:
- `dart_heap_mb` climbs with `internal_mb` → the growth is Dart.
- `dart_heap_mb` stays small and `malloc_in_use_mb` climbs → native malloc.
- Both stay small while `internal_mb` climbs → anonymous memory that is neither the Dart heap nor the default malloc zone.

## Where to keep sampling
Leave the 30-second sampler running through pause. After End Visit, keep it running for about 8 minutes, or until the next recording starts. That covers the kills that landed 1–8 minutes after End Visit.

Do not sample the rest of the app. Extra breadcrumbs fill the Sentry buffer.

## Code
- `lib/src/features/record/services/resource_monitoring_service.dart` — breadcrumb already emitted from `_addMemoryBreadcrumb`. Add `phase`. Do not cancel the timer on pause. After End Visit, start an 8-minute tail instead of `stop()`.
- Pause and End Visit call sites in `chunking_recording_state_notifier.dart`, `native_recording_state_notifier.dart`, and `recording_state_notifier.dart`. Today pause calls `stop()` and one `track`. End Visit calls `track(RECORDING_ENDED)` and then `stop()`.
- Dart heap read next to `collectMemoryMetrics` in `resource_metrics_collector_io.dart`. iOS only. Web and Android stay unchanged.

## Out of scope
- Finding the retainer. These fields only split Dart vs native vs other anonymous.
- `audio_buffered_mb`. The packet list is about 1 MB per flush, so it cannot explain this rate.
- Changing SQLite, encryption, or the upload path.
