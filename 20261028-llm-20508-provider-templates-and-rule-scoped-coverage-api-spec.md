# LLM-20508 — Provider templates, rule-scoped template coverage, unset default: API spec

Paths are under `/v1/scribe/admin_panel/appointment_rules`.

| PR | Ticket | Endpoint | Status (2026-10-28) |
|---|---|---|---|
| [normandy#61078](https://github.com/getathelas/normandy/pull/61078) | LLM-20951 | `GET /providers/{provider_id}/templates` (new) | Open, review required |
| [normandy#61094](https://github.com/getathelas/normandy/pull/61094) | LLM-20962 | `GET /template_coverage` (new params) | Open, review required |
| Not opened yet | LLM-20970 | `DELETE /{template_id}/default` (new) | Not started (stacked on #61094) |

## 1. `GET /providers/{provider_id}/templates` (new)

### Request

| Param | In | Type | Required |
|---|---|---|---|
| `provider_id` | path | int ≥ 1 | yes |

### Response `200`

| Field | Type | Notes |
|---|---|---|
| `provider_id` | int | |
| `scribe_account_id` | int | The account the backend checks for this provider (informational) |
| `templates` | `{template_id: int, template_name: str}[]` | Templates the provider can use. No guaranteed order |

```json
{
  "provider_id": 75200,
  "scribe_account_id": 48183,
  "templates": [
    {"template_id": 1362, "template_name": "SOAP Template"},
    {"template_id": 64,   "template_name": "Progress Note"},
    {"template_id": 79,   "template_name": "Daily Note"}
  ]
}
```

`404 Provider not found` if the provider isn't at the admin's site or has no enabled account.

## 2. `GET /template_coverage` (new params)

### Request

| Param | Type | Required | Meaning |
|---|---|---|---|
| `template_id` | int ≥ 1 | yes (existing) | Template to check: where providers will end up |
| `facility_id` | int | no (existing) | Site-wide calls only; 422 with the params below |
| `appointment_type` | str | no (new) | The rule's appointment type |
| `rule_template_id` | int ≥ 1 | no (new) | The rule's template: whose providers to check |

Send `appointment_type` and `rule_template_id` together (422 otherwise). Without them, the response is site-wide as today.

### Response `200` (shape unchanged)

| Field | Type | With rule scope |
|---|---|---|
| `template_id` | int | Echo |
| `total_provider_count` | int | Providers on the rule |
| `providers_without_template` | `RuleProvider[]` | Providers on the rule without `template_id`. Every one is accepted in `providers_without_template` by that rule's edit / delete |

```
GET /template_coverage?template_id=79&appointment_type=QA+Follow+Up&rule_template_id=65
```
```json
{
  "template_id": 79,
  "total_provider_count": 2,
  "providers_without_template": [
    {"provider_id": 75201, "name": "Sevinc2 Test2", "email": "sevinc2.test2@example.com",
     "has_template": false, "is_explicit": true}
  ]
}
```

`404 No appointment rule for that type and template` if the rule doesn't exist.

## 3. `DELETE /{template_id}/default` (new)

Stops a rule being the default (the counterpart of `PUT /{template_id}/default`). Nobody's template changes: the default's providers are pinned to the rule, and the type is left with no default.

### Request

| Param | In | Type | Required |
|---|---|---|---|
| `template_id` | path | int | yes |
| `appointment_type` | query | str, min length 1 | yes |

No body.

### Response `200`

`AppointmentRuleWriteResponse`, the same as `PUT /{template_id}/default`: the refreshed `appointment_type` card (the rule now has `is_default: false` and the same `provider_count`) and the site-wide `missing_rules`.

```
DELETE /64/default?appointment_type=QA+New+Patient
```
```json
{
  "appointment_type": {
    "appointment_type": "QA New Patient",
    "rules": [
      {"template_id": 64, "template_name": "Progress Note", "template_deleted": false,
       "is_default": false, "provider_count": 14, "providers_missing_template_count": 2},
      {"template_id": 83, "template_name": "SOAP Note", "template_deleted": false,
       "is_default": false, "provider_count": 2, "providers_missing_template_count": 0}
    ]
  },
  "missing_rules": {"provider_count": 11, "appointment_type_count": 3},
  "errors": []
}
```

| Case | Status | `detail` |
|---|---|---|
| No rule for that type and template | 404 | `No appointment rule for that type and template` |
| Rule is not the default | 400 | `Rule is not the default for this appointment type` |
| Default covers no active providers | 400 | `Rule has no providers; delete it instead` |

## 4. What to call

| Scenario | Call |
|---|---|
| Add template / Add rule (All providers) | `GET /template_coverage?template_id={new}` (unchanged) |
| Change template on a rule | `GET /template_coverage?template_id={new}&appointment_type={type}&rule_template_id={rule}` |
| Change template **and** providers in one edit | `GET /template_coverage?template_id={new}`, then keep only the new `provider_ids` |
| Delete a non-default rule (the type has a default) | `GET /template_coverage?template_id={default}&appointment_type={type}&rule_template_id={rule}` |
| Delete the default (other rules exist) | `GET /template_coverage?template_id={new_default_template_id}&appointment_type={type}&rule_template_id={default}` |
| Delete when there's nowhere to land (no default, or the last rule) | No call; skip the missing-template step |
| Uncheck "Set as default" on the default | `DELETE /{template_id}/default?appointment_type={type}` (not `PUT`) |
| Move providers onto a rule | `GET /providers/{provider_id}/templates` for each selected provider; missing = target template not in `templates` |

Call when the action is confirmed, not from data loaded earlier.
