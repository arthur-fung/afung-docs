# Appointment rules console — UI smoke flow

Open: **Account → Demos → Appointment rules API** (`scribe_developer`).

Set once:

```bash
export BASE='http://localhost:8000'
export token='YOUR_SCRIBE_JWT'
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

Spec: [`normandy/docs/20261021-template-appointment-linking-fe-api-spec.md`](../../normandy/docs/20261021-template-appointment-linking-fe-api-spec.md)

---

## Facility IDs (new UI dropdown)

**`GET /v1/scribe/admin_panel/filter_options`** — build the dropdown from `available_facilities` (`id`, `name`). Use `id` as `facility_id` on appointment-rules requests; omit for “All facilities”.

```bash
curl -sS -w 'HTTP %{http_code}\n' -o "$OUT_DIR/filter-options.json" "${HDR[@]}" \
  "$BASE/v1/scribe/admin_panel/filter_options"

jq '.available_facilities' "$OUT_DIR/filter-options.json"
```

---

## List rules

**UI:** optional `facility_id` → **List rules**. Expect `200`, types in the cached list + JSON panel. Replace `46` with an id from [Facility IDs](#facility-ids-new-ui-dropdown).

```bash
curl -sS -w 'HTTP %{http_code}\n' -o "$OUT_DIR/list-rules.json" "${HDR[@]}" \
  "$BASE/v1/scribe/admin_panel/appointment_rules"

curl -sS -w 'HTTP %{http_code}\n' -o "$OUT_DIR/list-rules-facility-46.json" "${HDR[@]}" \
  "$BASE/v1/scribe/admin_panel/appointment_rules?facility_id=46"
```

---

## Providers

**UI:** `appointment_type`, `template_id`; optional `facility_id`, `search`, `page`, `items_per_page` → **Providers**.

```bash
curl -sS -G -w 'HTTP %{http_code}\n' -o "$OUT_DIR/providers-illness-t12.json" "${HDR[@]}" \
  --data-urlencode 'appointment_type=Illness' \
  --data-urlencode 'template_id=12' \
  --data-urlencode 'page=1' \
  --data-urlencode 'items_per_page=20' \
  "$BASE/v1/scribe/admin_panel/appointment_rules/providers"

curl -sS -G -w 'HTTP %{http_code}\n' -o "$OUT_DIR/providers-workers-comp-t77.json" "${HDR[@]}" \
  --data-urlencode "appointment_type=Workers' Comp" \
  --data-urlencode 'template_id=77' \
  --data-urlencode 'search=keiko' \
  --data-urlencode 'facility_id=46' \
  "$BASE/v1/scribe/admin_panel/appointment_rules/providers"
```

---

## Coverage

**UI:** `template_id`; optional `facility_id` → **Coverage**.

```bash
curl -sS -G -w 'HTTP %{http_code}\n' -o "$OUT_DIR/coverage-t12.json" "${HDR[@]}" \
  --data-urlencode 'template_id=12' \
  "$BASE/v1/scribe/admin_panel/appointment_rules/template_coverage"

curl -sS -G -w 'HTTP %{http_code}\n' -o "$OUT_DIR/coverage-t12-facility-46.json" "${HDR[@]}" \
  --data-urlencode 'template_id=12' \
  --data-urlencode 'facility_id=46' \
  "$BASE/v1/scribe/admin_panel/appointment_rules/template_coverage"
```

---

## Missing

**UI:** optional `facility_id` → **Missing**.

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

```bash
curl -sS -X POST -w 'HTTP %{http_code}\n' -o "$OUT_DIR/create-rule.json" "${HDR[@]}" \
  "$BASE/v1/scribe/admin_panel/appointment_rules" \
  -d '{
    "appointment_type": "Illness",
    "template_id": 45,
    "is_default": false,
    "apply_to": "SELECTED",
    "provider_ids": [881, 882]
  }'
```

---

## Set default

**UI:** `appointment_type`, `template_id` (existing non-default rule) → **Set default**. No body.

```bash
curl -sS -X PUT -w 'HTTP %{http_code}\n' -o "$OUT_DIR/set-default-t45-illness.json" "${HDR[@]}" \
  "$BASE/v1/scribe/admin_panel/appointment_rules/45/default?appointment_type=Illness"
```

---

## Edit

**UI:** `appointment_type`, `template_id` (current rule); optional `new_template_id`, `provider_ids`, `providers_without_template` → **Edit**.

Change template:

```bash
curl -sS -X PATCH -w 'HTTP %{http_code}\n' -o "$OUT_DIR/edit-t45-to-t46.json" "${HDR[@]}" \
  "$BASE/v1/scribe/admin_panel/appointment_rules/45?appointment_type=Illness" \
  -d '{"new_template_id": 46}'
```

Resolve missing (rule unchanged; URL-encode `appointment_type` in query):

```bash
curl -sS -X PATCH -w 'HTTP %{http_code}\n' -o "$OUT_DIR/edit-resolve-missing-t77.json" "${HDR[@]}" \
  "$BASE/v1/scribe/admin_panel/appointment_rules/77?appointment_type=Workers%27%20Comp" \
  -d '{
    "providers_without_template": [
      {"provider_id": 902, "action": "ADD_TEMPLATE"},
      {"provider_id": 903, "action": "PERSONAL_RULES"}
    ]
  }'
```

---

## Move

**UI:** `appointment_type`, `template_id` (target rule), `provider_ids` → **Move**.

```bash
curl -sS -X PATCH -w 'HTTP %{http_code}\n' -o "$OUT_DIR/move-providers-t12.json" "${HDR[@]}" \
  "$BASE/v1/scribe/admin_panel/appointment_rules/12/providers?appointment_type=Illness" \
  -d '{"provider_ids": [881]}'
```

---

## Delete

**UI:** `appointment_type`, `template_id`; when deleting the default with other rules, set `new_default_template_id` → **Delete**.

```bash
curl -sS -X DELETE -w 'HTTP %{http_code}\n' -o "$OUT_DIR/delete-t12.json" "${HDR[@]}" \
  "$BASE/v1/scribe/admin_panel/appointment_rules/12?appointment_type=Illness" \
  -d '{}'

curl -sS -X DELETE -w 'HTTP %{http_code}\n' -o "$OUT_DIR/delete-t12-with-new-default.json" "${HDR[@]}" \
  "$BASE/v1/scribe/admin_panel/appointment_rules/12?appointment_type=Illness" \
  -d '{
    "new_default_template_id": 45,
    "providers_without_template": [{"provider_id": 902, "action": "ADD_TEMPLATE"}]
  }'
```

---

## My rules

**UI:** `scope` (`top`|`all`) → **My rules**. Needs site `scribe_appointment_rules` + account `scribe_appointment_rules_provider_view`.

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

```bash
curl -sS -X PUT -w 'HTTP %{http_code}\n' -o "$OUT_DIR/choose-template.json" "${HDR[@]}" \
  "$BASE/v1/scribe/appointment_rules/me" \
  -d '{"appointment_type": "Illness", "template_id": 45}'
```
