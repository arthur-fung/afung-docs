# LLM-21387 — PR #6490: recording opens on Previsit for non-P360 users — root cause

**PR.** [#6490](https://github.com/getathelas/scribe-mobile/pull/6490) `feat(p360): replace scribe_pvs_recording_default_mobile flag with a Display Settings preference` (Tianhao Yu).

## Problem

- #6490 replaces the flag `scribe_pvs_recording_default_mobile` with a user preference `recording_start_on_previsit`. Its rollout sets the preference as a **site default** for today's flag sites.
- A site default reaches **every** user at the site, including users without P360. The Display Settings toggle is hidden from them, so they can't turn it off.
- For a non-P360 user with the Flowsheet Guide on (phone / Chrome), the recording screen opens with `_selectedTab = previsit`. There's no Previsit tab, so the tab bar highlights Recording, but `isMobileCustomRecordingTab` is true, so the screen also shows the white overlay, mini bar and bottom padding of a custom tab. It stays like that until the user taps another tab.

## How it happened

| When | Who | PR | What it assumed or added |
|---|---|---|---|
| 2026-07-23 | William Jiang | [#5622](https://github.com/getathelas/scribe-mobile/pull/5622) Gate mobile/chrome default recording state to be pvs | `startOnPvs` reads the flag with **no P360 check**. Safe then: admins only turned the flag on for P360 customers, and P360 was the only thing that added tabs. |
| 2026-10-17 | Md. Shohan Ahmed | [#6300](https://github.com/getathelas/scribe-mobile/pull/6300) LLM-19024: Flowsheet Guide for recording screen | Flowsheet Guide becomes a **second source of tabs**, so non-P360 users can get the tab layout. |
| 2026-11 (open) | Tianhao Yu | [#6490](https://github.com/getathelas/scribe-mobile/pull/6490) | Flag → preference with **site defaults**, which reach non-P360 users at those sites. |

## Root cause

The opening-tab code never checks that the user has P360. It relied on the flag only being given to P360 users. #6300 made that assumption matter, and #6490 removes the admin control that kept it true.

## Fix (in #6490)

`lib/src/features/record/views/recording_screen.dart:185`

AS-IS:
```dart
_selectedTab = initialRecordingTab(
  startOnPvs:
      ref.read(preferencesProvider).recordingStartOnPrevisit.value == true,
);
```

TO-BE:
```dart
_selectedTab = initialRecordingTab(
  startOnPvs:
      ref.read(featureFlagProvider).scribePatient360 &&
      ref.read(preferencesProvider).recordingStartOnPrevisit.value == true,
);
```

Also update the stale field comment at `recording_screen.dart:139` ("Previsit vs Recording, per the flag") to name the preference; #6490 updated the matching comments at lines 182–183 and `recording_screen_tabs.dart:69` but missed this one.

## Not issues

- **No fallback to the flag when an env hasn't defined the preference:** by design; the rollout in #6490's description creates the preference and site/account defaults before the release.
- **Toggle visible on tablet / desktop, where tabs aren't used:** by design since #5622; it's a per-account setting for phone and Chrome, and the toggle copy says so.
