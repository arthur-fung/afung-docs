# Appointment rules console — UI smoke flow

Open: **Account → Demos → Appointment rules API** (`scribe_developer`).

All parameters below are for the **staging** account `arthur.fung@commure.com` (scribe account `100000217`, provider `7`, site `4` "Aalok Test 2"). Run a local Normandy backend pointed at the staging DB, since the appointment rules routes are not on staging yet. Check out the branch for the endpoints you test (see [PRs](#prs)).

### PRs

Status as of 2026-10-25. Merged PRs are on `main`. The open PRs are stacked, so each branch includes the ones above it: #60070 → #60355 → #60358 → #60362, and #60070 → #60372 → #60385. To test everything except my rules, check out #60362.

| PR | Endpoints | Sections | Status |
|---|---|---|---|
| [#60065](https://github.com/getathelas/normandy/pull/60065) | `GET /admin_panel/appointment_rules` | [List rules](#list-rules) | Merged 2026-10-22 |
| [#60069](https://github.com/getathelas/normandy/pull/60069) | `GET …/providers`, `GET …/template_coverage` | [Providers](#providers), [Coverage](#coverage) | Merged 2026-10-22 |
| [#60070](https://github.com/getathelas/normandy/pull/60070) | `POST /admin_panel/appointment_rules` | [Create](#create) | Open |
| [#60355](https://github.com/getathelas/normandy/pull/60355) | `PATCH …/{template_id}`, `PATCH …/{template_id}/providers` | [Edit](#edit), [Move](#move) | Open |
| [#60358](https://github.com/getathelas/normandy/pull/60358) | `PUT …/{template_id}/default`, `DELETE …/{template_id}` | [Set default](#set-default), [Delete](#delete), [Cleanup](#cleanup) | Open |
| [#60362](https://github.com/getathelas/normandy/pull/60362) | `GET …/missing`; `providers_without_template` on create, edit, move, delete; `GET …/providers` without `appointment_type` | [Missing](#missing), [Providers](#providers) | Open |
| [#60372](https://github.com/getathelas/normandy/pull/60372) | `GET /v1/scribe/appointment_rules/me` | [My rules](#my-rules) | Open |
| [#60385](https://github.com/getathelas/normandy/pull/60385) | `PUT /v1/scribe/appointment_rules/me` | [Choose template](#choose-template) | Open |

Set once:

```bash
export BASE='http://localhost:8000'
export token='YOUR_SCRIBE_JWT'   # staging JWT for arthur.fung@commure.com
export HDR=(
  -H "Authorization: Bearer $token"
  -H 'Content-Type: application/json'
  -H 'x-caller-service-name: SCRIBE'
  -H 'x-caller-service-state: /'
  -H 'x-device-type: WEB_APP'
  -H 'x-app-version: 1.0.0-default'
)
export OUT_DIR="${OUT_DIR:-./appointment-rules-smoke}"
mkdir -p "$OUT_DIR"
```

Spec: [`normandy/docs/20261025-template-appointment-linking-fe-api-spec.md`](../../normandy/docs/20261025-template-appointment-linking-fe-api-spec.md)

### Staging data (site 4, 2026-10-22)

| Appointment type | Rule template | Default | Providers | Missing the template |
|---|---|---|---|---|
| Follow Up | 64 Progress Note | yes | 11 | 2 (Inna Yaskin `7`, C A `122211`) |
| New Patient | 64 Progress Note | yes | 11 | 2 (same) |
| MD New Patient 30 | 63 SOAP Note | yes | 11 | 5 (`109902`, `110485`, `110505`, `125372`, `125381`) |

Facilities: `46` "test" (3 providers: Inna, Amon, Gautam) and `47` "ENTERTAINMENT MEDICAL GROUP" (5 providers: Inna, Amon, abc, dgfargaer, UNASSIGNED).

Templates the site's providers have, used below:

| Template | Name | Providers who have it |
|---|---|---|
| 64 | Progress Note | all except `7`, `122211` |
| 65 | Meeting Note | all except `122211` |
| 63 | SOAP Note | `7`, `110280`, `110367`, `122210`, `122211`, `123327496` |
| 503 | (TEST) Scribe Hospitalist | all except `123327496` |
| 1362 | SOAP Template | primary template for most providers, incl. `110485` |
| 10195 | — | primary template of C A `122211` |

The write steps use a throwaway appointment type, **`Smoke Test`**, so the real Follow Up / New Patient rules stay untouched. Run the write sections top to bottom; each step depends on the one before. [Cleanup](#cleanup) removes the type again.

---

## Facility IDs (new UI dropdown)

**`GET /v1/scribe/admin_panel/filter_options`** — build the dropdown from `available_facilities` (`id`, `name`). Use `id` as `facility_id` on appointment-rules requests; omit for “All facilities”. Expect facilities `46` and `47`.

```bash
curl -sS -w 'HTTP %{http_code}\n' -o "$OUT_DIR/filter-options.json" "${HDR[@]}" \
  "$BASE/v1/scribe/admin_panel/filter_options"

jq '.available_facilities' "$OUT_DIR/filter-options.json"
```

---

## List rules

**UI:** optional `facility_id` → **List rules**. Expect `200` and the three types above. Site-wide: `total_provider_count` 11, `missing_rules` `{provider_count: 7, appointment_type_count: 3}`. Facility 46: `total_provider_count` 3, `missing_rules.provider_count` 2.

```bash
curl -sS -w 'HTTP %{http_code}\n' -o "$OUT_DIR/list-rules.json" "${HDR[@]}" \
  "$BASE/v1/scribe/admin_panel/appointment_rules"

curl -sS -w 'HTTP %{http_code}\n' -o "$OUT_DIR/list-rules-facility-46.json" "${HDR[@]}" \
  "$BASE/v1/scribe/admin_panel/appointment_rules?facility_id=46"
```

---

## Providers

**UI:** `template_id`; optional `appointment_type`, `facility_id`, `search`, `page`, `items_per_page` → **Providers**. A type/template pair that isn't a rule returns `404` `"No appointment rule for that type and template"`.

Default rule: expect 11 providers sorted by name, all `is_explicit: false`, 2 with `has_template: false` (C A, Inna Yaskin).

```bash
curl -sS -G -w 'HTTP %{http_code}\n' -o "$OUT_DIR/providers-follow-up-t64.json" "${HDR[@]}" \
  --data-urlencode 'appointment_type=Follow Up' \
  --data-urlencode 'template_id=64' \
  --data-urlencode 'page=1' \
  --data-urlencode 'items_per_page=20' \
  "$BASE/v1/scribe/admin_panel/appointment_rules/providers"
```

Paging: expect providers 6–10, `total_count` 11, `total_pages` 3.

```bash
curl -sS -G -w 'HTTP %{http_code}\n' -o "$OUT_DIR/providers-follow-up-t64-page-2.json" "${HDR[@]}" \
  --data-urlencode 'appointment_type=Follow Up' \
  --data-urlencode 'template_id=64' \
  --data-urlencode 'page=2' \
  --data-urlencode 'items_per_page=5' \
  "$BASE/v1/scribe/admin_panel/appointment_rules/providers"
```

Search + facility: `amon` matches Amon Sthapit by name and UNASSIGNED PROVIDER by email (`AMON.STHAPIT.TEST8@…`), both in facility 47. Expect 2 rows.

```bash
curl -sS -G -w 'HTTP %{http_code}\n' -o "$OUT_DIR/providers-follow-up-t64-amon-facility-47.json" "${HDR[@]}" \
  --data-urlencode 'appointment_type=Follow Up' \
  --data-urlencode 'template_id=64' \
  --data-urlencode 'search=amon' \
  --data-urlencode 'facility_id=47' \
  "$BASE/v1/scribe/admin_panel/appointment_rules/providers"
```

All site providers (Add rule **Select providers** picker): leave out `appointment_type`. Needs [#60362](https://github.com/getathelas/normandy/pull/60362) (`422` before it). Template 63: expect all 11 providers sorted by name, all `is_explicit: false`, 5 with `has_template: false` (`109902`, `110485`, `110505`, `125372`, `125381`). With `facility_id=46`: 3 providers, only Gautam Pradeep (`109902`) with `has_template: false`.

```bash
curl -sS -G -w 'HTTP %{http_code}\n' -o "$OUT_DIR/providers-site-t63.json" "${HDR[@]}" \
  --data-urlencode 'template_id=63' \
  --data-urlencode 'page=1' \
  --data-urlencode 'items_per_page=20' \
  "$BASE/v1/scribe/admin_panel/appointment_rules/providers"
```

A non-default rule (`is_explicit: true`) only exists after [Create](#create); that section has its own providers call.

---

## Coverage

**UI:** `template_id`; optional `facility_id` → **Coverage**. Template 63 site-wide: expect `total_provider_count` 11 and 5 `providers_without_template` (`109902`, `110485`, `110505`, `125372`, `125381`). Facility 46: 3 providers, only Gautam Pradeep (`109902`) without it.

```bash
curl -sS -G -w 'HTTP %{http_code}\n' -o "$OUT_DIR/coverage-t63.json" "${HDR[@]}" \
  --data-urlencode 'template_id=63' \
  "$BASE/v1/scribe/admin_panel/appointment_rules/template_coverage"

curl -sS -G -w 'HTTP %{http_code}\n' -o "$OUT_DIR/coverage-t63-facility-46.json" "${HDR[@]}" \
  --data-urlencode 'template_id=63' \
  --data-urlencode 'facility_id=46' \
  "$BASE/v1/scribe/admin_panel/appointment_rules/template_coverage"
```

---

## Missing

**UI:** optional `facility_id` → **Missing**. Needs [#60362](https://github.com/getathelas/normandy/pull/60362) (`404 "Not Found"` before it). Site-wide: expect 7 providers across the 3 types.

```bash
curl -sS -w 'HTTP %{http_code}\n' -o "$OUT_DIR/missing.json" "${HDR[@]}" \
  "$BASE/v1/scribe/admin_panel/appointment_rules/missing"

curl -sS -G -w 'HTTP %{http_code}\n' -o "$OUT_DIR/missing-facility-46.json" "${HDR[@]}" \
  --data-urlencode 'facility_id=46' \
  "$BASE/v1/scribe/admin_panel/appointment_rules/missing"
```

---

## Create

**UI:** `appointment_type`, `template_id`, `apply_to` (`ALL`|`SELECTED`), `is_default`, optional `provider_ids`, optional `providers_without_template` lines → **Create**. Expect `201` + write body.

1. Default rule for everyone: `Smoke Test` → 64 (Progress Note). Expect 11 providers, 2 missing (`7`, `122211`).
2. Non-default rule: 65 (Meeting Note) for `110485`, `110505`.
3. Non-default rule: 503 (Hospitalist) for `110367`.

```bash
curl -sS -X POST -w 'HTTP %{http_code}\n' -o "$OUT_DIR/create-smoke-t64-default.json" "${HDR[@]}" \
  "$BASE/v1/scribe/admin_panel/appointment_rules" \
  -d '{
    "appointment_type": "Smoke Test",
    "template_id": 64,
    "is_default": true,
    "apply_to": "ALL"
  }'

curl -sS -X POST -w 'HTTP %{http_code}\n' -o "$OUT_DIR/create-smoke-t65.json" "${HDR[@]}" \
  "$BASE/v1/scribe/admin_panel/appointment_rules" \
  -d '{
    "appointment_type": "Smoke Test",
    "template_id": 65,
    "is_default": false,
    "apply_to": "SELECTED",
    "provider_ids": [110485, 110505]
  }'

curl -sS -X POST -w 'HTTP %{http_code}\n' -o "$OUT_DIR/create-smoke-t503.json" "${HDR[@]}" \
  "$BASE/v1/scribe/admin_panel/appointment_rules" \
  -d '{
    "appointment_type": "Smoke Test",
    "template_id": 503,
    "is_default": false,
    "apply_to": "SELECTED",
    "provider_ids": [110367]
  }'
```

Repeat any of these for `409` (template is already a rule for the type).

Providers on the non-default card: expect 2 rows (abc def, dgfargaer aergaeae), both `is_explicit: true`, `has_template: true`.

```bash
curl -sS -G -w 'HTTP %{http_code}\n' -o "$OUT_DIR/providers-smoke-t65.json" "${HDR[@]}" \
  --data-urlencode 'appointment_type=Smoke Test' \
  --data-urlencode 'template_id=65' \
  "$BASE/v1/scribe/admin_panel/appointment_rules/providers"
```

---

## Set default

**UI:** `appointment_type`, `template_id` (existing non-default rule) → **Set default**. No body.

65 becomes the default and rule 64 stops existing; everyone except `110367` (still on 503) is on 65. Missing: C A (`122211`) only.

```bash
curl -sS -X PUT -w 'HTTP %{http_code}\n' -o "$OUT_DIR/set-default-smoke-t65.json" "${HDR[@]}" \
  "$BASE/v1/scribe/admin_panel/appointment_rules/65/default?appointment_type=Smoke%20Test"
```

---

## Edit

**UI:** `appointment_type`, `template_id` (current rule); optional `new_template_id`, `provider_ids`, `providers_without_template` → **Edit**.

Change template: rule 503 (`110367`) → 63 (SOAP Note, which `110367` has). The rule's URL is now `/63`.

```bash
curl -sS -X PATCH -w 'HTTP %{http_code}\n' -o "$OUT_DIR/edit-smoke-t503-to-t63.json" "${HDR[@]}" \
  "$BASE/v1/scribe/admin_panel/appointment_rules/503?appointment_type=Smoke%20Test" \
  -d '{"new_template_id": 63}'
```

Resolve missing (rule unchanged; URL-encode `appointment_type` in query; `providers_without_template` returns `400` before [#60362](https://github.com/getathelas/normandy/pull/60362)): C A lacks 65, so `PERSONAL_RULES` pins them to their primary template 10195 as a new non-default rule. Expect missing to drop to 0.

```bash
curl -sS -X PATCH -w 'HTTP %{http_code}\n' -o "$OUT_DIR/edit-smoke-resolve-missing-t65.json" "${HDR[@]}" \
  "$BASE/v1/scribe/admin_panel/appointment_rules/65?appointment_type=Smoke%20Test" \
  -d '{
    "providers_without_template": [
      {"provider_id": 122211, "action": "PERSONAL_RULES"}
    ]
  }'
```

`ADD_TEMPLATE` would instead add template 65 to every enabled scribe account C A has at the site, so it changes staging accounts; leave it out unless you want to test that.

---

## Move

**UI:** `appointment_type`, `template_id` (target rule), `provider_ids` → **Move**.

Move Test Provider (`110280`, has 63) from the default onto rule 63. Rule 63 then has `110280`, `110367`.

```bash
curl -sS -X PATCH -w 'HTTP %{http_code}\n' -o "$OUT_DIR/move-smoke-to-t63.json" "${HDR[@]}" \
  "$BASE/v1/scribe/admin_panel/appointment_rules/63/providers?appointment_type=Smoke%20Test" \
  -d '{"provider_ids": [110280]}'
```

---

## Delete

**UI:** `appointment_type`, `template_id`; when deleting the default with other rules, set `new_default_template_id` → **Delete**.

Non-default: delete C A's rule 10195; C A falls back to the default 65 and is missing again.

```bash
curl -sS -X DELETE -w 'HTTP %{http_code}\n' -o "$OUT_DIR/delete-smoke-t10195.json" "${HDR[@]}" \
  "$BASE/v1/scribe/admin_panel/appointment_rules/10195?appointment_type=Smoke%20Test" \
  -d '{}'
```

Default with other rules: delete 65 and make 63 the default. Without `new_default_template_id` expect `400`. The `providers_without_template` field needs [#60362](https://github.com/getathelas/normandy/pull/60362). `110485` lacks 63, so `PERSONAL_RULES` pins them to their primary template 1362 (new rule). The other providers without 63 (`109902`, `110505`, `125372`, `125381`) land on 63 and show as missing.

```bash
curl -sS -X DELETE -w 'HTTP %{http_code}\n' -o "$OUT_DIR/delete-smoke-t65-with-new-default.json" "${HDR[@]}" \
  "$BASE/v1/scribe/admin_panel/appointment_rules/65?appointment_type=Smoke%20Test" \
  -d '{
    "new_default_template_id": 63,
    "providers_without_template": [{"provider_id": 110485, "action": "PERSONAL_RULES"}]
  }'
```

---

## Cleanup

Remove the `Smoke Test` type: delete the non-default 1362 rule, then the default 63 (no other rules left, so the type is unmapped). Afterwards **List rules** should show only the three original types.

```bash
curl -sS -X DELETE -w 'HTTP %{http_code}\n' -o "$OUT_DIR/cleanup-smoke-t1362.json" "${HDR[@]}" \
  "$BASE/v1/scribe/admin_panel/appointment_rules/1362?appointment_type=Smoke%20Test" \
  -d '{}'

curl -sS -X DELETE -w 'HTTP %{http_code}\n' -o "$OUT_DIR/cleanup-smoke-t63.json" "${HDR[@]}" \
  "$BASE/v1/scribe/admin_panel/appointment_rules/63?appointment_type=Smoke%20Test" \
  -d '{}'
```

---

## My rules

**UI:** `scope` (`top`|`all`) → **My rules**. Needs site `scribe_appointment_rules` (on for site 4) + account `scribe_appointment_rules_provider_view`. As of 2026-10-22 account `100000217` has **no** `scribe_appointment_rules_provider_view` override, so expect `403` until it's turned on for the account.

```bash
curl -sS -G -w 'HTTP %{http_code}\n' -o "$OUT_DIR/my-rules-scope-top.json" "${HDR[@]}" \
  --data-urlencode 'scope=top' \
  "$BASE/v1/scribe/appointment_rules/me"

curl -sS -G -w 'HTTP %{http_code}\n' -o "$OUT_DIR/my-rules-scope-all.json" "${HDR[@]}" \
  --data-urlencode 'scope=all' \
  "$BASE/v1/scribe/appointment_rules/me"
```

---

## Choose template

**UI:** `appointment_type`, `template_id` (your active scribe template) → **Choose template**. Same flags as **My rules**. Picking the type’s default template removes your pin.

Account `100000217` has templates 1362, 64 and 65. Pick 65 for Follow Up: provider `7` gets a pin, and **List rules** shows a non-default Follow Up → 65 rule with 1 provider. Then pick 64 (the default) to remove the pin and restore the original state.

```bash
curl -sS -X PUT -w 'HTTP %{http_code}\n' -o "$OUT_DIR/choose-template-follow-up-t65.json" "${HDR[@]}" \
  "$BASE/v1/scribe/appointment_rules/me" \
  -d '{"appointment_type": "Follow Up", "template_id": 65}'

curl -sS -X PUT -w 'HTTP %{http_code}\n' -o "$OUT_DIR/choose-template-follow-up-t64-reset.json" "${HDR[@]}" \
  "$BASE/v1/scribe/appointment_rules/me" \
  -d '{"appointment_type": "Follow Up", "template_id": 64}'
```

A template not on the account (e.g. `63`) returns `400` `"Template is not one of your active scribe templates"`.
