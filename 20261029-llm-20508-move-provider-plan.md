# LLM-20508 — Move provider: move only to an existing rule

PR: [scribe-mobile#6406](https://github.com/getathelas/scribe-mobile/pull/6406) (`move_provider_dialog.dart`). No backend change.

## Problem

The Move dialog lets the admin pick any template the provider has. The move API (`PATCH /appointment_rules/{template_id}/providers`) only accepts a template that is already a rule for that appointment type, so any other pick fails with `404`.

## Fix

Move sends providers only to **another rule that already exists** for the same appointment type.

To move a provider to a template that isn't a rule yet, the admin uses **Add rule → Select providers** instead.

## Example

"QA New Patient" has three rules:

- Progress Note (64), the default
- SOAP Note (83)
- Daily Note (79)

The admin opens the Progress Note rule and moves Dr A (provider 123).

## Steps

### 1. Admin clicks Move on Dr A

The dialog lists only the type's **other rules**: SOAP Note and Daily Note.

- The rule Dr A is on (Progress Note) is not listed.
- Templates that aren't rules for this type are not listed.
- The list comes from the rule list the screen already loaded (`GET /appointment_rules`). No new call.
- If the type has no other rules, Move is unavailable: there's nowhere to move to.

### 2. Admin picks the target rule and confirms

For example, Daily Note (79).

### 3. Check whether Dr A has the target template

Use one of:

| Call | Missing when | Available |
|---|---|---|
| `GET /appointment_rules/template_coverage?template_id=79` | Dr A is in `providers_without_template` | Now |
| `GET /appointment_rules/providers/123/templates` | Template 79 is not in `templates` | After [normandy#61078](https://github.com/getathelas/normandy/pull/61078) merges |

Make the call on confirm, not from data loaded earlier. No prompt: moving Dr A to the rule implies adding the template.

### 4. Send one call

```
PATCH /v1/scribe/admin_panel/appointment_rules/79/providers?appointment_type=QA+New+Patient
```

Dr A lacks the template:
```json
{
  "provider_ids": [123],
  "providers_without_template": [
    { "provider_id": 123, "action": "ADD_TEMPLATE" }
  ]
}
```

Dr A has the template:
```json
{ "provider_ids": [123] }
```

Never send `PERSONAL_RULES` for a move: it would pin Dr A to their primary template, not the target.

### 5. After the save

- Update the screen from the response: both rule cards get their new counts.
- If the save fails, keep the dialog open and show the error.
- If the target rule was deleted in the meantime (`404`), reload the rule list, as the screen already does.

## What changes

| | Today | After |
|---|---|---|
| Target list | Every template Dr A has | The type's other rules |
| Pick a template that isn't a rule | Allowed, then `404` | Not possible |
| Step "Which template should they use instead?" | Shown | Removed |
| Provider lacks the target template | Not handled | `ADD_TEMPLATE` sent automatically |

## Tests

- Target list shows only the type's other rules, not the current one or other templates.
- Provider has the target template → request has no `providers_without_template`.
- Provider lacks it → request sends `ADD_TEMPLATE` for them.
- Save fails → dialog stays open.
