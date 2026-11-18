# API spec: template builder Preview (LLM-17855)

Preview shows a clinician the note their template would produce **before they save it**. The backend runs a transcript through errands' **real** note generation, using the template's current config plus the unsaved edits. It returns the note without creating a scribe, saving anything, or triggering follow-on work (ICD-10, clinical integrity, CareCues, EHR sync).

- Ticket: [LLM-17855](https://linear.app/commure/issue/LLM-17855/preview-mode) · Project: Customize 2.0
- Design write-up (call graph, options, inputs): [20261118-LLM-17855-preview-mode-call-graph.html](20261118-LLM-17855-preview-mode-call-graph.html)
- Status: **proposal**. Not built yet. The errands owner should confirm the errands assumptions (see [Open questions](#open-questions)).

---

## Overview

The client starts a preview, gets a `preview_id` back right away, and polls until the note is ready.

```
POST /v1/scribe/template_builder/preview          → 202 { preview_id, status: "pending" }
GET  /v1/scribe/template_builder/preview/{id}     → poll every 2 s until completed | failed
GET  /v1/scribe/template_builder/preview/sources  → recent scribes for the source picker (optional)
```

Why polling instead of one blocking request:

- Generation takes **30–90 s**, which risks gateway timeouts and dropped mobile connections.
- The user can **switch source mid-generation**. The client moves on to the newest `preview_id` and ignores older ones.
- There's a single result, so streaming (server-sent events or websockets) isn't worth it.

### How the server generates the note

```
POST /preview
  ├─ validate: auth, feature flag, rate limit, template type, source access
  ├─ Redis SET preview:{id} = {status: pending, account_id, ...}  (TTL 15 min)
  ├─ start a FastAPI background task ───────────────────────────────┐
  └─ return 202 {preview_id}                                        │
                                                                    ▼
             build GenerateWorkflowTaskOutput (same payload as a real note)
               • saved config + draft overrides
               • carry-forward / EHR context left out
               • is_note_metrics_engine_env = True
             HTTP POST errands /generate_workflow_task_output (direct, no Cloud Tasks)
               └─ errands returns the note in the response and does NOT call
                  /task_completed_callback (errands/jobs/openai/controllers.py:4133)
             Redis SET preview:{id} = {status: completed | failed, output...}
```

Nothing is written to Postgres, and no migration is needed.

---

## Common rules

| | |
|---|---|
| Auth | Scribe user auth (`get_scribe_user`), same as the other `template_builder` routes |
| Feature flag | New flag `scribe_template_preview` on the calling scribe account. Off: `403` |
| Admin panel | Optional `scribe_account_id` = the provider being edited. Validated with `is_valid_site_admin_scribe_account_access`, and the action is logged with `log_admin_action` (same pattern as LLM-21928 / LLM-21929) |
| Rate limit | `@dynamic_rate_limiter` (per user, by tier). Also **one preview in progress per account**: a new `POST` supersedes the previous one |
| Templates allowed | Standard note templates only. Clinical integrity, CareCues, orders & codes, Compassus visit notes and flowsheet guides get `422` |
| Logging | Never log the prompt or the transcript. Log `preview_id`, `template_id`, source type, duration and outcome |

---

## 1. Start a preview

```
POST /v1/scribe/template_builder/preview
```

### Request body

```json
{
  "template_id": 1234,
  "source": { "type": "scribe", "scribe_id": 98765 },
  "draft": {
    "custom_format_settings": [
      { "custom_format_id": 3, "section": "hpi.history", "value": "low" }
    ],
    "disabled_section_paths": ["ros.constitutional"],
    "form_definition": null
  },
  "scribe_account_id": null
}
```

| Field | Type | Required | Rules |
|---|---|---|---|
| `template_id` | int | yes | Must be one of the target account's templates (`get_single_saved_template_service`). |
| `source.type` | `"example"` \| `"scribe"` | yes | `example` uses the onboarding tour's sample transcript, stored server-side. |
| `source.scribe_id` | int | when `type = "scribe"` | Must belong to the target account and have a non-empty transcript. The frontend sends the latest scribe by default (from `/preview/sources`). |
| `draft` | object \| null | no | Unsaved edits. A missing or `null` field means "use the saved config". |
| `draft.custom_format_settings` | list \| null | no | **Replaces** the saved settings for this template. Same item shape as `POST /custom_formatting/format_option_settings` (`custom_format_id`, `section`, `value`). |
| `draft.disabled_section_paths` | string[] \| null | no | **Replaces** the saved subsection on/off state. Dot paths, same as `section_generation`. |
| `draft.form_definition` | object \| null | no | **v2, not in v1.** Draft template structure. In v1, sending a non-null value returns `422`. |
| `scribe_account_id` | int \| null | no | Admin panel only. See [Common rules](#common-rules). |

### What the preview includes

| Input | v1 |
|---|---|
| Saved template structure, with disabled subsections removed | Included (with draft toggles applied) |
| Formatting settings | Included (draft replaces saved) |
| Macros v2 selection, note preferences, dot phrases, learning examples | Included (saved data) |
| Provider's feature flags | Included |
| Carry-forward / previous note | **Left out** |
| Patient / appointment context, EHR metadata, chart prep, uploaded documents | **Left out** |
| Diarized transcript, English translation | **Left out** (uses the plain transcript) |
| ICD-10, corrections and other callback post-processing | **Left out** (callback skipped) |

The response's `omitted_inputs` lists what was left out, so the frontend can tell the user.

### Response

`202 Accepted`

```json
{
  "preview_id": "0193a8f2-6c1e-7b3a-9d40-5f2e1c7a8b90",
  "status": "pending",
  "poll_interval_ms": 2000
}
```

`preview_id` is a UUIDv7.

### Errors

| Status | When |
|---|---|
| `400` | `source.type = "scribe"` without `scribe_id`. Scribe has no transcript. Provider at another site (admin mode) |
| `403` | Feature flag off. Scribe doesn't belong to the target account. Caller isn't a site admin (admin mode) |
| `404` | Template not found for the target account. Scribe not found |
| `422` | Template type not allowed. `draft.form_definition` sent in v1. Bad body |
| `429` | Rate limited |

---

## 2. Poll for the result

```
GET /v1/scribe/template_builder/preview/{preview_id}
```

### Responses

`200 OK`, pending:

```json
{ "preview_id": "0193a8f2-...", "status": "pending" }
```

`200 OK`, completed:

```json
{
  "preview_id": "0193a8f2-...",
  "status": "completed",
  "template_id": 1234,
  "source": { "type": "scribe", "scribe_id": 98765 },
  "output_json": { "subjective": { "hpi": "..." }, "plan": "..." },
  "output_text": "SUBJECTIVE\n...",
  "omitted_inputs": ["carry_forward", "ehr_context"],
  "duration_ms": 41230
}
```

`200 OK`, failed:

```json
{
  "preview_id": "0193a8f2-...",
  "status": "failed",
  "error": { "code": "generation_failed", "retryable": true }
}
```

`200 OK`, superseded by a newer preview from the same account:

```json
{ "preview_id": "0193a8f2-...", "status": "superseded" }
```

| Field | Notes |
|---|---|
| `status` | `pending` \| `completed` \| `failed` \| `superseded` |
| `output_json` | Same shape as a real task's `output_json`, so the existing note renderer works. Section order and hidden titles come from the client's draft. |
| `output_text` | Plain-text fallback for templates that don't enforce JSON output. |
| `omitted_inputs` | Values: `carry_forward`, `ehr_context`, `documents`, `translation`. Only lists what applied to this source. |
| `error.code` | `generation_failed`, `errands_timeout`, `transcript_too_long` |

### Errors

| Status | When |
|---|---|
| `404` | Unknown or expired `preview_id`, **or the preview belongs to another account** (so IDs can't be probed). Also returned if an API server restart lost the in-progress preview. The client treats it as `failed` and offers Retry. |

---

## 3. Recent scribes for the source picker (optional)

```
GET /v1/scribe/template_builder/preview/sources?limit=5&scribe_account_id=
```

Lists the target account's most recent scribes **that have a transcript**, newest first. Skip this endpoint if an existing scribe-list endpoint can already filter by "has transcript" with a limit.

```json
{
  "sources": [
    {
      "scribe_id": 98765,
      "patient_name": "J. Doe",
      "created_at": "2026-11-17T21:04:11Z",
      "template_name": "SOAP Note"
    }
  ]
}
```

`limit` is 1–10, default 5.

---

## Client flow

```
Tap "Preview"
  └─ POST /preview {source: latest scribe or example}   → preview_id A
       show loading animation
       poll GET /preview/A every poll_interval_ms
         ├─ completed  → render note (+ "not shown in preview" note from omitted_inputs)
         ├─ failed/404 → error + Retry (new POST)
         │                 second failure → "We're investigating" + log
         └─ > 3 min    → stop, treat as failed

Switch source while A is pending
  └─ POST /preview {new source}   → preview_id B   (server marks A superseded)
       stop polling A, poll B

"Back to Edit"  → stop polling. Nothing to clean up (Redis entry expires)
"Save Template" → normal save endpoints. Preview never saves
```

---

## Tracking

| Event | When | Fields |
|---|---|---|
| `TEMPLATE_PREVIEW_REQUESTED` | `POST /preview` accepted | `template_id`, `source.type`, admin mode yes/no |
| `TEMPLATE_PREVIEW_COMPLETED` | Background task stores `completed` | `preview_id`, `duration_ms` |
| `TEMPLATE_PREVIEW_FAILED` | Background task stores `failed` | `preview_id`, `error.code` |

The frontend tracks taps on Preview, Back to Edit and the source picker separately.

---

## Implementation notes (normandy)

- **Routes** go in `app/api/v1/scribe/template_builder/controllers.py`, mounted at `/v1/scribe/template_builder`. Business logic goes in a new `preview_services.py` next to it.
- **Payload builder:** add a variant of `trigger_single_workflow_task` (`app/api/v1/scribe/workflows/services.py:3495`) that builds `GenerateWorkflowTaskOutput` from (template, target account, transcript, draft) **without** a workflow task, workflow or scribe. Share the lookups (flags, macros, preferences, dot phrases, learning examples). **Real-note behavior must not change.** Add tests that the existing payload is unchanged.
- **Errands call:** a direct, blocking HTTP POST to errands' `/generate_workflow_task_output`, with errands auth and a ~150 s timeout. Not `scribe_trigger_task` (Cloud Tasks).
- **State:** Redis `preview:{preview_id}` holds status, `account_id`, source and output, with a 15 min TTL. Redis `preview_active:{account_id}` holds the newest `preview_id`, used to supersede older previews.
- **Background work:** FastAPI `BackgroundTasks`. An API server restart loses in-progress previews, which is acceptable (the client retries). Move to Cloud Tasks plus a preview callback only if that becomes a problem.
- **Long transcripts:** reuse the compression the real path applies above `MAX_TRANSCRIPTION_LENGTH`, or reject with `transcript_too_long`.
- **Don't copy** the old `preview_custom_formatting` (`app/api/v1/scribe/controllers.py:9037`). It builds its own prompt and logs the full prompt, transcript included.

## Open questions

1. **Errands mid-run calls** *(errands owner)*: before the final callback, errands sends status and tracking events (`send_scribe_status_message_to_normandy`, `send_scribe_track_event`). Confirm they don't fail the request when there's no real scribe or task, or skip them when `is_note_metrics_engine_env` is set.
2. **`is_note_metrics_engine_env` on current errands** *(errands owner)*: confirm it still returns the note in the response and skips `/task_completed_callback`. (Checked on an errands checkout from 2026-10-12.)
3. **Speed** *(Prasanna / Cyvian)*: is 30–90 s acceptable for v1? If not, decide which errands steps the preview can skip.
4. **Draft scope** *(product)*: v1 covers formatting settings and subsection on/off. Are draft structure and macros needed in v1?
5. **API server capacity** *(backend)*: each preview holds a worker for up to ~90 s. Check the thread pool can handle expected concurrency, or use an async HTTP client.
6. **Example transcript** *(frontend / backend)*: confirm which transcript the onboarding tour uses, and move it server-side if it only lives in the frontend.

## Effort

| Scope | Estimate |
|---|---|
| v1: endpoints 1–2, payload builder variant, direct errands call, Redis state, flag, rate limit, tracking, tests | ~½–1 week (backend) |
| Endpoint 3 (sources) | +½ day, if no existing endpoint fits |
| v2: draft `form_definition` and macro overrides, admin panel support | +2–3 days |
