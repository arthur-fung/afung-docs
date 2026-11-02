# LLM-21145 — Unset the default appointment rule: API spec

For FE (scribe-mobile, Appointment Mapping side panel). Adds one admin write to the [Template Appointment Linking FE API spec](20261025-template-appointment-linking-fe-api-spec.md). Conventions (§1), `WriteResponse` (§2) and the error contract (§6) are the same as there.

| | |
|---|---|
| Ticket | [LLM-21145](https://linear.app/commure/issue/LLM-21145) (replaces the canceled LLM-20970) |
| Status (2026-11-02) | **Not available yet.** Waiting on Product and Design to pick option 1 on LLM-21145. Backend PR not opened. |
| Backend | normandy `app/api/v1/scribe/admin_panel/appointment_rules/` |

## Why

Admins can't uncheck **Set as default** on the current default. Today the app dims the checkbox, because no endpoint can stop a rule being the default:

| Existing call | What it does to the default |
|---|---|
| `PUT /{template_id}/default` | Only makes a rule the default |
| `PATCH /{template_id}` | Rejects `provider_ids` on the default rule |
| `PATCH /{template_id}/providers` | Moving onto the default only drops pins |
| `DELETE /{template_id}` | Removes the rule, and asks for a new default when other rules exist |

This endpoint lets the checkbox be unchecked.

## Endpoint

```
DELETE /v1/scribe/admin_panel/appointment_rules/{template_id}/default?appointment_type=<type>
```

| Call | Meaning |
|---|---|
| `PUT /{template_id}/default` | Make this rule the default (existing) |
| `DELETE /{template_id}/default` | Stop this rule being the default (**new**) |
| `DELETE /{template_id}` | Delete the rule (existing) |

`DELETE /{template_id}/default` and `DELETE /{template_id}` differ only by `/default`. Keep both paths as constants; don't build them by hand.

### Request

| Param | In | Type | Required | Notes |
|---|---|---|---|---|
| `template_id` | path | int | yes | The current default's template |
| `appointment_type` | query | string | yes | URL-encoded, at least 1 character. Send the exact string from the list response. |

No body. Auth is the same as every admin write: site admin, `scribe_admin_panel` on for the caller, `scribe_appointment_rules` on for the site.

### Behavior

The rule stays, with the same template and the same providers. It's just no longer the default.

| Who | Before | After |
|---|---|---|
| Providers the default covered | On the default rule | On the **same rule** (same template), now pinned individually. Their template doesn't change. |
| Providers on other rules for the type | On their rule | Unchanged |
| Providers added to the site later | Would get the default | Get no rule for the type, so they use their own primary template |

Afterwards the type has **no default**. That has two knock-on effects in the existing UI:

- New providers show up in `missing_rules` for the type.
- Missing-rules fixes for this type only offer **Create personal rule** (no "Use default"), as for any type with no default (QA plan B17).

To make a rule the default again, call `PUT /{template_id}/default` on it.

### Response

`200 WriteResponse`, the same shape as `PUT /{template_id}/default`:

- `appointment_type`: the refreshed card. The rule has `is_default: false` and the same `provider_count`. No rule on the type has `is_default: true`.
- `missing_rules`: the refreshed site-wide summary.
- `errors`: always `[]` (this call never adds templates).

### Errors

| Status | `detail` | When | Suggested UI |
|---|---|---|---|
| `400` | `Rule is not the default for this appointment type` | The rule exists but isn't the default (for example, the list was stale) | Revert the checkbox, refetch |
| `400` | `Rule has no providers; delete it instead` | The default covers no active providers, so the rule would disappear | Revert the checkbox, offer Delete |
| `403` | | Not a site admin, or a flag is off | Same as other writes |
| `404` | `No appointment rule for that type and template` | No rule for `(appointment_type, template_id)` | Revert the checkbox, refetch |
| `409` | | Conflicted with a concurrent change | Refetch and retry |
| `500` | `Appointment rule was updated but the updated list could not be loaded` | **The write succeeded** | Refetch `GET /appointment_rules`, don't retry |

Any other `500` means nothing was written.

**Open (decide in spec review):** the default's template has been soft-deleted (`template_deleted: true`). Unsetting works today, but `PUT /default` rejects deleted templates, so that rule could never be made the default again. The backend may return `400` for this case instead. If it does, the FE should keep the checkbox disabled when `template_deleted` is true.

### Example

`Follow Up` on site 152825. Progress Note (64) is the default and covers 3 providers. Meeting Note (65) has Jorge.

```
DELETE /v1/scribe/admin_panel/appointment_rules/64/default?appointment_type=Follow%20Up
```

```json
{
  "appointment_type": {
    "appointment_type": "Follow Up",
    "rules": [
      { "template_id": 64, "template_name": "Progress Note", "template_deleted": false, "is_default": false, "provider_count": 3, "providers_missing_template_count": 0 },
      { "template_id": 65, "template_name": "Meeting Note", "template_deleted": false, "is_default": false, "provider_count": 1, "providers_missing_template_count": 0 }
    ]
  },
  "missing_rules": { "provider_count": 0, "appointment_type_count": 0 },
  "errors": []
}
```

## FE changes (scribe-mobile)

- `AppointmentRulesV2Repository.unsetDefault(appointmentType, templateId)`. Path constant next to `setDefault`.
- `AppointmentMappingViewModel.unsetDefault`: same saving key, error toast and `_applyWriteResult` as `setDefault`.
- `rule_detail_panel.dart`: stop dimming and ignoring the checkbox on the default (`Opacity` / `IgnorePointer`), and let `_onDefaultChanged(false)` through.
- `appointment_mapping_view.dart` `onSetDefault`: `isDefault ? setDefault(...) : unsetDefault(...)`.
- Revert the checkbox if the call fails.
- Confirm copy before unchecking is up to Design. Suggestion: "`<type>` will have no default. Current providers keep `<template>`. New providers will use their primary template."
- Repository test asserting the exact method and path for `unsetDefault` and `deleteRule`.

## QA (after it ships)

- Uncheck the default: the same rule and providers stay, the card shows no default.
- Visit check for a covered provider: same template as before.
- Check **Set as default** on the same rule again: it's the default again.
- A non-default rule's checkbox still works as today (check makes it the default).
