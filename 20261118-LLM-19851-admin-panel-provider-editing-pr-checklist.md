# 20261118 — Admin Panel: site admins edit a provider's customize settings — PR checklist

Parent: [LLM-19851](https://linear.app/commure/issue/LLM-19851/show-new-custom-formatting-ux-in-the-admin-panel)
· FE PR: getathelas/scribe-mobile#6539

Two backend gaps block parts of the admin editor. The frontend has those actions disabled or locked
in admin mode until the backend PRs below ship.

| PR | Ticket | Endpoint | Today | Size |
|---|---|---|---|---|
| 1 | [LLM-21928](https://linear.app/commure/issue/LLM-21928) | `DELETE /custom_formatting/format_option_settings/{template_id}/{custom_format_id}/{section}` | Acts on the admin's own account. It can delete the **admin's** setting | Small (1–2 h) |
| 2 | [LLM-21929](https://linear.app/commure/issue/LLM-21929) | `POST /template_builder/edit_template_v2` | 403. The admin isn't the template's owner | Medium (½–1 day) |

Shared pattern to copy: `get_format_option_settings` in
`app/api/v1/scribe/custom_formatting/controllers.py`, which takes an optional `scribe_account_id`,
calls `is_valid_site_admin_scribe_account_access(...)`, and then `log_admin_action(...)`.

---

## PR 1: clear a provider's formatting setting (LLM-21928)

Title: `fix(custom_formatting): let site admins clear a provider's format option setting`

### Implementation

- [ ] `delete_format_option_setting` in `app/api/v1/scribe/custom_formatting/controllers.py`:
  - [ ] Add `request: Request` and `scribe_account_id: Optional[int] = None` (query param, same as the GET).
  - [ ] When `scribe_account_id` is set, call `is_valid_site_admin_scribe_account_access` and use the
        returned `scribe_account` as the target user.
  - [ ] Pass the **target** user to `get_single_saved_template_service`, not `scribe_user`.
  - [ ] `log_admin_action(..., action_type=AdminActionType.CUSTOM_FORMATTING, details={template_id, section, custom_format_id, scribe_account_id, "operation": "delete_format_option_setting"})`.
  - [ ] Log lines show the target account ID.
- [ ] Without `scribe_account_id`, behavior is unchanged.
- [ ] Don't touch the single-setting GET endpoint. The admin screen doesn't call it.

### Tests (`app/tests/scribe/custom_formatting/test_scribe_custom_formatting_controllers.py`)

- [ ] Site admin with `scribe_account_id` clears the provider's setting. The provider's row is gone.
- [ ] The **admin's own** setting on the same template and section is untouched (regression for the original bug).
- [ ] Non-admin passing `scribe_account_id` gets 403.
- [ ] Provider at another site gets 400.
- [ ] Unknown `scribe_account_id` gets 404.
- [ ] No `scribe_account_id` clears the caller's own setting (existing behavior).
- [ ] An admin action log row is written.

### PR description

- [ ] Follow `.github/pull_request_template.md`, with an endpoint table and local curl tests.
- [ ] Note for FE: re-enable the clear button in admin mode once this is deployed.

---

## PR 2: edit a provider's template structure (LLM-21929)

Title: `feat(template_builder): let site admins edit a provider's template structure`

### Before starting

- [ ] **Product sign-off on LLM-21929**: site admins may add, remove and rename sections on a provider's template.
- [ ] **Audit decision**: version history records the provider (simple), or "admin on behalf of provider" (needs an `Actor` change).

### Implementation

- [ ] `TemplateBuilderEditTemplateV2Payload` (`app/api/v1/scribe/template_builder/schemas.py`): add
      `scribe_account_id: Optional[int] = None`.
- [ ] `edit_template_v2` (`app/api/v1/scribe/template_builder/controllers.py`):
  - [ ] Add `request: Request`.
  - [ ] When `payload.scribe_account_id` is set, call `is_valid_site_admin_scribe_account_access` and resolve the target provider.
  - [ ] `log_admin_action(...)` with template ID, version IDs and `"operation": "edit_template_v2"`.
      Add a new `AdminActionType` only if `CUSTOM_FORMATTING` doesn't fit (that needs a migration if it's a DB enum, so check first).
- [ ] `edit_builder_template_v2` (`services.py`): build `Actor` from the **target provider**, so
      `compute_permissions` applies the provider's ownership rule:
  - [ ] An individual template of the provider can be updated.
  - [ ] A shared template still gets 403 (`SharedTemplateReadOnly`).
  - [ ] A template that isn't the provider's still gets 403. The admin can't use a provider's ID to edit unrelated templates.
- [ ] `verify_template` and `track_template_builder_event`: decide which user is passed (provider for
      template data, admin for analytics), and say so in the PR.
- [ ] `build_v2_response`: pass the target provider so the returned `permissions` describe the provider.
- [ ] If the audit decision is "on behalf of": extend `Actor` in
      `app/api/v1/templates/template_service/commands.py` and stamp it in `_add_version`
      (`writer.py`). This is shared template service code, so tag its owners for review.
- [ ] Without `scribe_account_id`, behavior is unchanged.

### Tests (`app/tests/scribe/template_builder/test_scribe_template_builder_v2_controllers.py`)

- [ ] Site admin renames a section on a provider's individual template. The new version is created and configs follow the rename.
- [ ] Site admin deletes a section. That section's configs are deleted and other sections are untouched.
- [ ] Site admin renames the template.
- [ ] Shared template gets 403.
- [ ] Template not assigned to the target provider gets 403.
- [ ] Non-admin with `scribe_account_id` gets 403. A provider at another site gets 400.
- [ ] Stale `expected_version_id` gets 409.
- [ ] EHR-sync template: a top-level add, delete or rename gets 403 (same as for the provider).
- [ ] The response `permissions` reflect the provider.
- [ ] Version `updated_by_*` matches the audit decision.
- [ ] An admin action log row is written.
- [ ] No `scribe_account_id`: the existing tests still pass.

### PR description

- [ ] Follow `.github/pull_request_template.md`, with an endpoint table and local curl tests.
- [ ] **Risks**:
  - [ ] Destructive edits: deleting a section deletes the provider's configs and changes their future notes.
  - [ ] The audit trail shows the provider, not the admin, unless `Actor` is extended.
  - [ ] Touches the shared template service, if extended.
- [ ] Note for FE: unlock structure editing in admin mode once this is deployed.

---

## Both PRs

- [ ] Run the tests for the changed modules locally: `ENV=TESTING uv run --env-file .env pytest -n0 app/tests/scribe/custom_formatting app/tests/scribe/template_builder`
- [ ] Lint and typecheck clean.
- [ ] No migrations expected (unless a new `AdminActionType` DB enum value is added).
- [ ] New routes or params gated by the existing site-admin check, not `user_is_admin`.
- [ ] Update the endpoint table (`docs/20261118-LLM-19851-admin-panel-api-endpoints.html`) when each PR ships.
