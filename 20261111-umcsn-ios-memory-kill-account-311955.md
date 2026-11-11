# UMCSN Ortho: iOS app dies mid-recording (account 311955)

2026-11-11 · scribe-mobile iOS · Sentry, Postgres replica, scribe_events (Retool), Cloud Logging · no provider or patient names

**Report.** Slack #scribe-support (11/11): a provider at UMCSN Ortho (site 153504) says the app crashes during about 90% of her recordings and leaves the scribe paused. Support was told it was low device memory and to reinstall.

## Summary

- **It is the iOS memory kill** (Sentry [SCRIBE-MOBILE-B0](https://athelas-monitoring.sentry.io/issues/SCRIBE-MOBILE-B0), WatchdogTermination), not low storage and not too many open apps. The phone is an iPhone 16 Pro (`device.class: high`).
- **Rate:** at least 50 kills for this account from 11/6 to 11/11, about 16 a day, one every 15–20 minutes in clinic hours. The fleet rate is about 0.45% of recordings.
- **Reinstalling did not help.** Kills continued on a fresh 3.43.2 install.
- **It matches the memory-kill loop** in [the 11/9 analysis](20261109-mobile-memory-kill-loops-analysis.html): memory climbs to about 3.2 GB, the app dies, relaunches and climbs again. Her phone shipped **0 client logs** on every one of her 14 recordings on 11/10, the doc's torn-log-cache signature.
- **On 3.43.3 she looks healthy.** Two recordings, about 1,000 log entries each, no kill since. This is encouraging, not proof.

## What the data shows

**Kills by day and version (Sentry B0, `user.id:311955`; the query was capped at 50 events, so older days are undercounted):**

| Day | App version | Kills |
|---|---|---|
| 11/6 | 3.42.1 | 17 |
| 11/9 | 3.42.1 | 15 |
| 11/10 | 3.42.1 | 2 |
| 11/10 | 3.43.2 | 10 |
| 11/11 | 3.43.2 | 6 |

**The test scribe (24755865, 3.43.2+3).** Event [`ebed40cd…`](https://athelas-monitoring.sentry.io/issues/SCRIBE-MOBILE-B0/events/ebed40cd5e364054b6cc0566b0ddf159/) at 18:20:43 UTC on 11/10.

| Time (UTC) | Source | What happened |
|---|---|---|
| 18:15:12 | scribe_events | Consent clicked, recording starts (this is her "12:15 PM", so she is UTC−6) |
| 18:17:18 | scribe_events | `IOS_LOW_MEMORY_WARNING`, then `LOW_MEMORY_DURING_RECORDING` |
| 18:17:43–18:20:43 | Sentry breadcrumbs | App memory 2,661 → 3,226 MB (+~120 MB per 30 s; OS compressed it once at 18:19) |
| 18:20:43 | Sentry | Killed at about 3.2 GB (last heap sample) |
| 18:21:00 | scribe_events | Relaunch, `APP_KILLED_DETECTED` |
| 18:21:09 | scribe_events | Recording resumed (`PARALLEL_RECORDING_RESUMED`) |
| 18:21:15 | scribe_events | She stops it, 6 s later |
| 18:21:23 | scribe_events | `SCRIBE_CREATED`, `FINALIZE_SUCCESS`; note generation completes |

- The scribe is `COMPLETED` with 336 s of audio, so the recovery worked. The ~7 s she lost in the video is plausibly the audio since the last 30 s chunk flush; not checked.
- Chunks flushed and uploaded normally (28 added, 26 uploaded, none failed). This is not an upload problem.
- Every scribe I saw for her from 11/9 to 11/11 is `COMPLETED` (28 rows); none is currently paused. The "paused" state in her video is the state before the app relaunched and resumed.
- At 18:06:41 there was another kill and resume. That recording was paused at 18:11:00 and I saw no resume or stop afterwards. I did not identify its scribe, so it may be one that stayed paused.

**Client logs per recording (Cloud Logging, `athelas-scribe-mobile`, `labels.recording_uuid`):**

| Build | Recordings checked | Log entries per recording |
|---|---|---|
| 3.42.1 / 3.43.2 (11/10) | 14 | **0** for all 14 |
| 3.43.2 control (two other accounts, 18:15 UTC, 20 s window) | 2 | 63 and 22 |
| 3.43.3+2 (11/11) | 2 (24876220, 24877630) | 1,001 and 1,049 |

The `user_id` label is not the scribe account ID (filtering on 311955 returned only an unrelated web recording), so use `recording_uuid`. I checked that `scribe.uuid` equals `recording_uuid` on the control scribes.

## Is it fixed in 3.43.3?

- scribe-mobile PR [#6488](https://github.com/getathelas/scribe-mobile/pull/6488) (torn GCP log cache wedging the buffer and leaking memory) merged 11/9. It sits on `release/hotfix/2026-11-10`, and that branch's `Bump version` commit sets `SCRIBE_VERSION` 3.43.2 → 3.43.3.
- Every kill I found is on 3.42.1 or 3.43.2, which predate the fix.
- **Not verified:** that the App Store 3.43.3 build was cut from that branch. Her logs coming back is consistent with it, but is not proof.

## Caveats

- Cause not confirmed. The decisive check is still the test-phone repro in the 11/9 doc (append an incomplete emoji to the log cache, relaunch, watch memory; repeat with #6488).
- The Sentry breadcrumbs keep only the last 100, so I cannot see where the climb started. The visible rate (~4 MB/s) is lower than the ~10 MB/s the doc expects from the torn cache.
- Two recordings on 3.43.3 is about 20 minutes of use. With a kill every 15–20 minutes before, that is thin evidence.

## Next steps

1. Recheck account 311955 after a full clinic day on 3.43.3: Sentry B0 events, `APP_KILLED_DETECTED`, and log entries per recording.
2. Run the test-phone repro to confirm the cause.
3. Confirm with the release owner that the shipped 3.43.3 includes #6488.
4. Reply to the support thread: this is an app bug, 3.43.3 carries a candidate fix, she should stay on 3.43.3; reinstalling and closing other apps was not the fix.
