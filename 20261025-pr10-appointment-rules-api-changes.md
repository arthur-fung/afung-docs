# PR 10 appointment rules API changes (2026-10-25)

[#60362](https://github.com/getathelas/normandy/pull/60362). All paths are under `/v1/scribe/admin_panel/appointment_rules`. Full contract: `docs/20261025-template-appointment-linking-fe-api-spec.md`.

| Endpoint | New / changed | What changed in PR 10 |
|---|---|---|
| `GET /missing` | **New** | Missing-rules pop-up. Optional `facility_id`. Returns `groups[]` (one per rule, with the providers missing it) and a `summary` (`provider_count`, `appointment_type_count`). |
| `GET /providers` | Changed | `appointment_type` is now optional. Without it, the endpoint lists every active site provider for the Add-rule picker, with `has_template` checked against `template_id`. With it, it behaves as before. `template_id` is still required in both modes. |
| `POST /` (create) | Changed | Accepts `providers_without_template`, which previously returned `400 "providers_without_template is not supported yet"`. |
| `PATCH /{template_id}` (edit) | Changed | Accepts `providers_without_template`. |
| `PATCH /{template_id}/providers` (move) | Changed | Accepts `providers_without_template`. |
| `DELETE /{template_id}` | Changed | Accepts `providers_without_template`. It's ignored when there's no landing template. |

## Entry checks for `providers_without_template`

Applies to create, edit, move and delete. Every entry is checked before anything is written.

| Problem | Status |
|---|---|
| The provider isn't in scope for the request | `400` |
| The provider already has the landing template | `400` |
| `PERSONAL_RULES` has no template to use | `400` |
| The same `provider_id` is listed twice | `422` |

## Actions

| `action` | Effect |
|---|---|
| `ADD_TEMPLATE` | After the rule write commits, the landing template is added to the provider's accounts without becoming their primary template. Any failure appears in `errors[]` as `{provider_id, action, error}`. |
| `PERSONAL_RULES` | The provider is pinned to a rule on a template they already have. That's their current non-default rule if it still applies, otherwise their primary template. |
