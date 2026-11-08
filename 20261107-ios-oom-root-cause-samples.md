# iOS memory kills (SCRIBE-MOBILE-B0) — root-cause sample, 3.42.1

Issue: https://athelas-monitoring.sentry.io/issues/SCRIBE-MOBILE-B0
Release: `scribe-ios@3.42.1`, last 30 days to 2026-11-07. Sample: 30 users, one kill trail (Sentry breadcrumbs) each.

## How the sample was picked
- Group 1: top 10 users by kill count (39–136 kills each).
- Group 2: ranks 11–20 (23–32 kills each).
- Group 3: 10 users with 1–5 kills each (two are iPads).
- Event per user: top 3 users = latest kill; the other 27 = whichever event Sentry returned (`any(id)`), not necessarily the latest. For users with 1 kill this makes no difference.
- Sentry user id = `scribe_account_id` in Postgres (not `scribe.user_id`).

## Categories
| Code | Meaning |
|---|---|
| A | Memory grows steadily during recording until killed |
| B | Memory not released after a visit; next visit starts high (2–3 GB) |
| C | Killed while idle or paused with a flat, low footprint (not an app-memory pattern) |
| D | Memory keeps growing after End Visit while browsing visit/EHR pages |
| E | Other or unclear (no samples, short in-dialog recording, mid-recording at low memory) |

## Tally (30 users)
| Class | Users | Count |
|---|---|---|
| A | 311731, 309965, 293330, 272644, 303877, 41105, 283020, 36433, 302233, 300556, 272637*, 288424, 309023, 278886, 302256, 274572 | 16 |
| B | 311955, 114516, 313364, 272331, 271113, 297572 | 6 |
| C | 318218*, 311108, 284566 | 3 |
| D | 303151, 273698 | 2 |
| E | 293513, 297227, 273650 | 3 |

\* low confidence (272637: only 30 s of recording samples; 318218: the key memory value is truncated and may belong in D).

By group: group 1 A4 / B3 / C1 / D1 / E1; group 2 A6 / B2 / D1 / E1; group 3 A6 / B1 / C2 / E1. The mix is similar for typical users and for repeat killers.

## Findings
- Growth rate while recording is about 200–550 MB/min (most 330–480). Footprint at the kill sits in a narrow band, about 2.7–3.4 GB, on 5.6–11.7 GB devices, with device free RAM often under 100 MB. Not a low-RAM-device problem.
- Memory is often not released after End Visit (B, D). Seen as carry-over baselines of 1.9–3.2 GB at the next Start Recording, and as +500 to +1,500 MB after End Visit while browsing.
- Several kills happen outside recording: 41105, 297227, 303151, 318218, 311108, 313364, 272331 were killed 1–8 minutes after End Visit or while idle.
- The UIKit low-memory warning fires at roughly 2.4–2.7 GB footprint, and kills follow within seconds to minutes. (Inferred; the `ios_low_memory` values are truncated in Sentry.)
- The `crypto_backend resolved` breadcrumb seen at ramp onset in 288424, 278886 and 302256 is not a cause. It is a one-time telemetry message emitted when the first encrypted-audio operation runs in a launch (AES-GCM engine tag), so it simply marks the first cached audio write after Start Recording. The slow Dart crypto path (`dart_inline` / `dart_background`, higher CPU and memory) is also ruled out as the main driver: across all 9,734 events on the issue (all versions, tag set since 2026-08-09), `crypto_backend` is `native` on 2,549 and empty on 7,185. No event has a Dart value. Empty means no encrypted operation had run yet in that launch, so those kills happen before any audio was cached (idle/browsing/early start).
- Not every kill is memory. 273650 (iPhone, ~200 MB, 2 GB free, no warnings), 284566 (iPad, 140–180 MB flat), 311108 (flat ~170 MB) look like a different cause. Watchdog terminations can also come from other OS reasons. These need a separate look.
- Data loss: for 10 accounts checked in Postgres, nearly all recordings still became scribes (statuses COMPLETED/SYNCED). Exceptions: 272644 had 6 INCOMPLETE scribes of 4–9 s audio, 303151 had 1 SYNC_ERROR, 293330 had 1 USER_ERROR. Not checked for the other 20 users.

## Caveats
- One kill per user. Some users may fall in another class on other days.
- 7 of the 30 buffers had wrapped (no app-start crumb), so time-to-kill is a lower bound and the start of the recording isn't always visible.
- Breadcrumb memory samples only log during recording; growth after End Visit is mostly inferred from warnings.
- A/B and B/D lines are judgment calls.

## Group 1 — top 10 by kill count
| User | Kills | Device / OS | Sentry event | Class | Evidence |
|---|---|---|---|---|---|
| 293513 | 136 | iPhone16,1 / iOS 27.0.1 | https://athelas-monitoring.sentry.io/issues/SCRIBE-MOBILE-B0/events/e8d4b7d7b22149729a16d2cb989a0594/ | E | Idle kill about 1 min after End Recording / Update Scribe; low-memory warning at 17:23; app had been running less than 1 min at the start of the trail; no recording samples |
| 311955 | 95 | iPhone17,1 / iOS 27.0.1 | https://athelas-monitoring.sentry.io/issues/SCRIBE-MOBILE-B0/events/cf7d584a2bc7429fb74898a540d686e3/ | B | Visit 2+: starts at 2.5 GB after Resume Visit; many low-memory warnings; grows 2.7 → 3.3 GB; killed opening a new RecordingScreen. 38 scribes landed (COMPLETED) |
| 311731 | 94 | iPhone19,3 / iOS 27.2 | https://athelas-monitoring.sentry.io/issues/SCRIBE-MOBILE-B0/events/fe89d4ae7ac849efa82ad7be6f745d4b/ | A | 0.9 → 3.2 GB in 3.5 min after Start Recording; kept growing after End Visit; 11.6 GB device |
| 114516 | 89 | iPhone18,3 / iOS 27.0.1 | https://athelas-monitoring.sentry.io/issues/SCRIBE-MOBILE-B0/events/01d702c246064b2aaabb354923b28e89/ | B | Visit 1: 263 → 2,938 MB in 6.75 min (~396 MB/min); visit 2 started at 3,234 MB; killed 0.7 s after starting a second recording |
| 318218 | 85 | iPhone17,3 / iOS 26.6.1 | https://athelas-monitoring.sentry.io/issues/SCRIBE-MOBILE-B0/events/04c90955a0dc43d49929a3af81767496/ | C* | Two short recordings; last sample ~0.9 GB; low memory 3 min after End Visit; truncated footprint "26…" may be 2.6 GB (then D) |
| 309965 | 63–75 | iPhone19,2 / iOS 27.0.1 | https://athelas-monitoring.sentry.io/issues/SCRIBE-MOBILE-B0/events/02ef4842b993476287e378277e017d17/ | A | 607 → 1,980 MB (~550 MB/min); footprint stayed ~1.98 GB after End Visit; low-memory burst 65 s after End Visit. Kills all on or before 10-30 |
| 313364 | 72 | iPhone18,1 / iOS 26.6.2 | https://athelas-monitoring.sentry.io/issues/SCRIBE-MOBILE-B0/events/05d987dfb36d4073bdd0677505b8db4f/ | B | Killed ~4.7 min after recording ended, footprint ~2.1 GB, 12 LOW_MEMORY in 0.4 s; 3 background cycles; (C also fits) |
| 293330 | 56 | iPhone16,2 / iOS 26.6.1 | https://athelas-monitoring.sentry.io/issues/SCRIBE-MOBILE-B0/events/0235b397bf6e4014a681d9985f6c87dd/ | A | 2,703 → 3,160 MB (~335 MB/min); stayed 3.16 GB after End Visit; start of recording not visible |
| 272644 | 53 | iPhone16,1 / iOS 26.6.1 | https://athelas-monitoring.sentry.io/issues/SCRIBE-MOBILE-B0/events/00187ca325b140a19806d97eb041c636/ | A | 2,737 → 3,358 MB (~267 MB/min), 40 LOW_MEMORY within 2 s; no navigation crumbs in buffer. 6 INCOMPLETE scribes (4–9 s audio) |
| 303151 | 39 | iPhone17,1 / iOS 27.0.1 | https://athelas-monitoring.sentry.io/issues/SCRIBE-MOBILE-B0/events/02a87c0662044743852ad3f470194c90/ | D | 436 MB at End Visit → ~1.78 GB three minutes later while browsing visit/EHR screens; later recordings start at 1.84 GB. 1 SYNC_ERROR on 11-04 |

## Group 2 — ranks 11–20
| User | Kills | Device | Sentry event | Class | Evidence |
|---|---|---|---|---|---|
| 272331 | 32 | iPhone18,1 | https://athelas-monitoring.sentry.io/issues/SCRIBE-MOBILE-B0/events/04d0ec4da88b4b8dbd4cf863bc6de80d/ | B | Visit 1 698 → 1,232 MB; +756 MB in 61 s after End Visit; visit 2 started at 2.1 GB; killed <1 min after End Visit (overlaps D) |
| 303877 | 31 | iPhone17,1 | https://athelas-monitoring.sentry.io/issues/SCRIBE-MOBILE-B0/events/03a98038cd024e37ac93b528b07622da/ | A | 423 → 3,371 MB (~346 MB/min); killed 8.5 min into recording |
| 41105 | 31 | iPhone16,2 | https://athelas-monitoring.sentry.io/issues/SCRIBE-MOBILE-B0/events/00593ce8a048491da1facceaf4e51f02/ | A | 319 → 2,104 MB (~300 MB/min) during a 6 min recording; killed ≥8 min after End Visit while idle |
| 297227 | 30 | iPhone18,3 | https://athelas-monitoring.sentry.io/issues/SCRIBE-MOBILE-B0/events/013475bf99d54b00bda2d4b609912aca/ | E | ~45 s recording in the AI Actions dialog (no recording screen); idle 5 min later; free RAM 89 MB; no samples |
| 283020 | 29 | iPhone18,2 | https://athelas-monitoring.sentry.io/issues/SCRIBE-MOBILE-B0/events/057fff4128594308978de7d0efe832ea/ | A | 2,701 → 3,371 MB (~210 MB/min); ~41 low-memory warnings; start not visible |
| 271113 | 26 | iPhone18,1 | https://athelas-monitoring.sentry.io/issues/SCRIBE-MOBILE-B0/events/15f840015be74fa48d2e7c86a1f889c0/ | B | Visit 1 336 → 1,385 MB; visit 2 started at 1,879 MB and reached 3,334 MB; killed 4.5 min into visit 2 |
| 36433 | 24 | iPhone17,2 | https://athelas-monitoring.sentry.io/issues/SCRIBE-MOBILE-B0/events/05217118823a42b8a99f6827a5779a84/ | A | 622 → 3,324 MB (~403 MB/min); grew ~1.1 GB while paused for 2.2 min |
| 302233 | 23 | iPhone17,1 | https://athelas-monitoring.sentry.io/issues/SCRIBE-MOBILE-B0/events/0accb471f4494e4381c1288315e968b6/ | A | 2,757 → 3,278 MB (~348 MB/min); ~48 low-memory warnings; start not visible |
| 300556 | 23 | iPhone17,2 | https://athelas-monitoring.sentry.io/issues/SCRIBE-MOBILE-B0/events/03a4d45a88e546219b8e2b79793cc376/ | A | 367 → 3,245 MB (~410 MB/min); killed 7 min into recording |
| 273698 | 23 | iPhone17,1 | https://athelas-monitoring.sentry.io/issues/SCRIBE-MOBILE-B0/events/1588a0962b9e4137acc374ebe09fa3b8/ | D | Visit 1 703 → 1,631 MB; +1,500 MB in 3.3 min while browsing between visits (~460 MB/min); visit 2 started at 3.1 GB |

## Group 3 — 1–5 kills each
| User | Kills | Device | Sentry event | Class | Evidence |
|---|---|---|---|---|---|
| 273650 | 1 | iPhone19,2 | https://athelas-monitoring.sentry.io/issues/SCRIBE-MOBILE-B0/events/ce5b58d3e557485590a7cafd337974a5/ | E | Killed ~70 s into a recording at ~200 MB footprint, 2 GB free, no warnings; not a memory pattern |
| 311108 | 1 | iPhone14,2 | https://athelas-monitoring.sentry.io/issues/SCRIBE-MOBILE-B0/events/2d7c6359d34f43ce9fefab634205bc44/ | C | Flat ~165 MB; 5.6 GB device, free RAM 40–270 MB; killed ≥4.5 min after End Visit while backgrounded |
| 272637 | 1 | iPad15,7 | https://athelas-monitoring.sentry.io/issues/SCRIBE-MOBILE-B0/events/5a8adc46bbb74418b1927f7e8520399e/ | A* | 281 → 526 MB in the first 30 s (~480 MB/min); then paused ~7 min, killed with free RAM ~38 MB; only 30 s of samples |
| 284566 | 1 | iPad15,7 | https://athelas-monitoring.sentry.io/issues/SCRIBE-MOBILE-B0/events/6301e6aa3c3844f89c3b716a31a428ca/ | C | Flat 140–180 MB across a 27+ min recording session with 3 pauses; no warnings; not a memory pattern |
| 288424 | 2 | iPhone18,2 | https://athelas-monitoring.sentry.io/issues/SCRIBE-MOBILE-B0/events/10b2774cdb454edbba94514d3e06439c/ | A | 285 → 3,169 MB (~430–445 MB/min); `crypto_backend resolved` at ramp onset |
| 309023 | 2 | iPhone14,7 | https://athelas-monitoring.sentry.io/issues/SCRIBE-MOBILE-B0/events/9da5ec9128504542b8cd431f2a3e155d/ | A | 1,212 → 2,925 MB (~200 MB/min); plateau ~2.9 GB; killed on foreground resume after 4 min in background |
| 297572 | 4 | iPhone18,5 | https://athelas-monitoring.sentry.io/issues/SCRIBE-MOBILE-B0/events/39effaa998964bbcbaf2e5f11a3b138f/ | B | Visit 1 ended at 1.3 GB; visit 2 started at 2.0 GB and reached 3.36 GB; 6 background cycles, growth continued while backgrounded |
| 278886 | 4 | iPhone16,2 | https://athelas-monitoring.sentry.io/issues/SCRIBE-MOBILE-B0/events/15a1818510d94e51bf5ffc4a1c6fc18d/ | A | 285 → 3,317 MB (~335–340 MB/min, linear); `crypto_backend resolved` at ramp onset |
| 302256 | 5 | iPhone19,2 | https://athelas-monitoring.sentry.io/issues/SCRIBE-MOBILE-B0/events/07828dc843114af4a6970fafe0b2e7be/ | A | 265 → 3,208 MB (~475–490 MB/min); `crypto_backend resolved` at ramp onset |
| 274572 | 5 | iPhone16,2 | https://athelas-monitoring.sentry.io/issues/SCRIBE-MOBILE-B0/events/20e142a5810e4b61b2e478aafc70cc84/ | A | 352 → 3,340 MB (~345–355 MB/min) over 8.5 min; killed right after Pause |

## Suggested next steps
1. Hand the iOS team the A/B/D pattern: what holds memory during recording and after End Visit. Crypto backend is not the lead (all `native` or unset).
2. Look separately at the non-memory kills (273650, 284566, 311108), which look like another cause.
3. Check Postgres for the 20 users not yet checked, to confirm kills rarely lose scribes.
