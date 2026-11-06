# SCRIBE-MOBILE-QKX — "File part not found for ID" pager: root cause

**Alert.** [incident.io 01M6S7BBC7TGE7R49F8EVVRMVS](https://app.incident.io/athelas/on-call/alerts/01M6S7BBC7TGE7R49F8EVVRMVS/details) → Sentry [SCRIBE-MOBILE-QKX](https://athelas-monitoring.sentry.io/issues/SCRIBE-MOBILE-QKX) (Ambient Frontend Platform, #scribe-frontend-pagers).

**Scope.** 52 events / 10 users since 2026-08-07. This burst: one user (88472), Android 3.43.0 (1025). Handled, non-fatal. No user-visible impact.

## Problem

A queued live chunk upload re-reads its cached file part after the row was already deleted by a successful finalize.

1. Each recorded chunk is cached in SQLite, then a `filePartId`-only op is queued in the shared `ChunkUploadPool` (`chunk_upload_provider.dart:883-905`, from [#5238](https://github.com/getathelas/scribe-mobile/pull/5238)).
2. User was on weak cellular ↔ wifi. GCS chunk PUTs kept failing across 4 recordings, so the pool backed up.
3. User tapped End Visit. Finalize uploaded the cached chunks, created the scribe, and `_handleSuccessfulUpload` called `deleteAudioCache`, deleting the file-part rows (`chunk_upload_provider.dart:1881-1892`).
4. A pool slot freed. The queued op ran `_uploadCachedChunkById` → `getFilePartForId(id)` (`chunk_upload_provider.dart:942`). Row gone → `SimpleException` (`cache_repository.dart:1493`).
5. The pool wrapper catches it and calls `_crashReporter.reportException` (`chunk_upload_provider.dart:896-904`) → Sentry error → page.

Failing IDs 19088–19091 are consecutive, i.e. one finished recording's leftover queued ops. Those chunks were already uploaded and combined by finalize, so nothing is lost. `_uploadCachedChunkById` already skips a cleared blob (`fileData == null`) but not a deleted row.

## Fix

- `getFilePartForId` throws a typed `FilePartNotFoundException` instead of `SimpleException`.
- `_uploadCachedChunkById` catches it, logs at info ("cache already finalized/deleted, skipping live upload") and returns.
- No Sentry report for this case.

## Ownership

- Code: vijay-aug — `_uploadCachedChunkById` / pool queueing ([#5238](https://github.com/getathelas/scribe-mobile/pull/5238) AFEP-1598, [#6330](https://github.com/getathelas/scribe-mobile/pull/6330) AFEP-2886).
- Existing unmerged agent drafts for older Sentry groups of the same error: [#5112](https://github.com/getathelas/scribe-mobile/pull/5112) (AFEP-1095), [#5861](https://github.com/getathelas/scribe-mobile/pull/5861) (AFEP-1972). Reuse AFEP-1972 rather than opening a new ticket.
