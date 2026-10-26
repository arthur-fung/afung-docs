# Template Appointment Linking — Frontend API Spec

For the FE engineers building the **admin panel Appointment Rules tab** (§3–§6) and the **provider Note Preferences card** (§8).

This replaces [`20261008-template-appointment-linking-api-spec.md`](20261008-template-appointment-linking-api-spec.md) (admin) and [`20261013-template-appointment-linking-provider-api-spec.md`](20261013-template-appointment-linking-provider-api-spec.md) (provider) as the reference for the frontend. It was written against the code, not the design: admin endpoints at PR 10 (`391e3e8426`), provider endpoints at PR 13 (`bdc91cf707`), and the readers on `main` (`5dec3ab095`). §10 lists what changed from the earlier specs.

Design: [`20261008-template-appointment-linking-design.md`](20261008-template-appointment-linking-design.md) · Checklist: [`20261025-template-appointment-linking-pr-checklist.md`](20261025-template-appointment-linking-pr-checklist.md) · Figma: [Provider Facing](https://www.figma.com/design/kVfXnRnPzkBSPnHrZVVPo5/Appointment-Template-Linking?node-id=1-4829&m=dev)

---

## 0. Availability

| Endpoints | PR | Status (2026-10-26) |
|---|---|---|
| Visit list / pre-chart resolver (§7.1–7.2) | [#60062](https://github.com/getathelas/normandy/pull/60062) (PR 4) | Merged 2026-10-21 |
| `GET /appointment_rules` | [#60065](https://github.com/getathelas/normandy/pull/60065) (PR 5) | Merged 2026-10-22 |
| `GET /providers`, `GET /template_coverage` | [#60069](https://github.com/getathelas/normandy/pull/60069) (PR 6) | Merged 2026-10-22 |
| `POST /appointment_rules` | [#60070](https://github.com/getathelas/normandy/pull/60070) (PR 7) | Merged 2026-10-26 |
| `PATCH /{template_id}`, `PATCH /{template_id}/providers` | [#60355](https://github.com/getathelas/normandy/pull/60355) (PR 8) | Merged 2026-10-26 |
| `PUT /{template_id}/default`, `DELETE /{template_id}` | [#60358](https://github.com/getathelas/normandy/pull/60358) (PR 9) | Merged 2026-10-26 |
| `GET /missing`, `providers_without_template` actions, `GET /providers` without `appointment_type` | [#60362](https://github.com/getathelas/normandy/pull/60362) (PR 10) | Open, awaiting review |
| v0 route guards (§7.3) | [#60064](https://github.com/getathelas/normandy/pull/60064) (PR 3) | Open, awaiting review |
| `GET /appointment_rules/me` | [#60372](https://github.com/getathelas/normandy/pull/60372) (PR 12) | Open, awaiting review |
| `PUT /appointment_rules/me` | [#60385](https://github.com/getathelas/normandy/pull/60385) (PR 13) | Open, awaiting review |

Both feature flags are off everywhere. Until a PR is merged and deployed, its endpoint doesn't exist on staging.

---

## 1. Conventions

| Item | Value |
|---|---|
| Admin base path | `/v1/scribe/admin_panel/appointment_rules` |
| Provider base path | `/v1/scribe/appointment_rules/me` |
| Admin auth | Scribe user token. The caller must be a site admin with `scribe_admin_panel` on. |
| Provider auth | Scribe user token for any scribe user linked to a provider. Doesn't need to be an admin. |
| Flags | `scribe_appointment_rules` (site level) turns the feature on. It is the only kill switch. `scribe_appointment_rules_provider_view` (account level) only shows the provider card. It does not turn rules on by itself. |
| Site scope | Taken from the caller's provider. Never sent in the request. |
| Rule identity | `{appointment_type, template_id}`. Rules have no id. Admin write routes address a rule as `/{template_id}?appointment_type=…`: the template goes in the path, and the type goes in the query string because it is free text and may contain `/`. |
| `appointment_type` | Free text from the EHR. Matching is exact, so case and inner whitespace count. Send back the exact string you received from a list response. URL-encode it in query strings. Request **bodies** (`POST /appointment_rules`, `PUT /me`) trim leading and trailing whitespace. Query strings don't. |
| "Provider" | A provider at the site with an enabled scribe account. In production, accounts with an Athelas email don't count, except on internal sites. Each provider is evaluated against **one** account, the same one the nightly pre-chart sweep uses. `has_template`, missing counts and the primary template are all computed on that account. |
| "Has the template" | The template is assigned and active on that account, isn't deleted, and is a scribe note template. |
| Reads | Served from the replica, so they can lag writes by a few seconds. Write responses are read from the primary. Use the write response to refresh the UI, not an immediate re-`GET`. |
| Writes | Each request is atomic, except `ADD_TEMPLATE` (§4). Writes to the same site and appointment type are serialized. |
| Empty rules | Empty rules are deleted automatically. A non-default rule that loses its last provider stops existing. The **default** rule is also deleted when a write leaves it covering 0 providers because everyone is pinned to other rules. After that, the type has no default, so providers added later get no rule for it. The default is kept if the type has no other rule, for example on a site with no active providers. |
| Error body | `{"detail": "<message>"}`. Pydantic `422`s use FastAPI's standard `detail` array. |
| List sizes | `provider_ids` and `providers_without_template` in admin write bodies take at most 1000 items each. Longer lists get a `422`. |

---

## 2. Shared types (admin)

### `RuleSummary`

| Field | Type | Notes |
|---|---|---|
| `template_id` | int | |
| `template_name` | string | `""` if the template has no name or no longer exists |
| `template_deleted` | bool | The template was soft-deleted. The rule still exists, and its providers show as missing. |
| `is_default` | bool | |
| `provider_count` | int | Providers this rule covers. For the default, that is the site providers not pinned to another rule for the type. A write never leaves a rule at `0`, but `0` can still appear: on a type whose only rule is the default and the site has no active providers, when providers are deactivated, or with data written before this feature. |
| `providers_missing_template_count` | int | Covered providers who don't have the template |

### `AppointmentTypeRules`

| Field | Type | Notes |
|---|---|---|
| `appointment_type` | string | |
| `rules` | `RuleSummary[]` | The default comes first, then the rest by `provider_count`, highest first. `[]` means the type is unmapped. |

### `MissingRulesSummary`

| Field | Type | Notes |
|---|---|---|
| `provider_count` | int | Distinct providers who are covered by at least one rule whose template they don't have |
| `appointment_type_count` | int | Distinct appointment types with at least one such provider |

### `RuleProvider`

| Field | Type | Notes |
|---|---|---|
| `provider_id` | int | |
| `name` | string | Provider's proper name |
| `email` | string \| null | Email of the provider's scribe account |
| `has_template` | bool | The provider has the template in context (see §1) |
| `is_explicit` | bool | `true` means the provider is pinned to a non-default rule. `false` means the default covers them. Always `false` in `template_coverage`. |

### `ProviderWithoutTemplate`

| Field | Type | Required | Notes |
|---|---|---|---|
| `provider_id` | int ≥ 1 | yes | |
| `action` | `"ADD_TEMPLATE"` \| `"PERSONAL_RULES"` | yes | See §4 |

### `WriteResponse` (every admin write)

| Field | Type | Notes |
|---|---|---|
| `appointment_type` | `AppointmentTypeRules` | The refreshed card for the type this write touched. If the type is now unmapped, `rules` is `[]`. |
| `missing_rules` | `MissingRulesSummary` | The refreshed site-wide summary. The facility filter doesn't apply. |
| `errors` | `ActionError[]` | `ADD_TEMPLATE` failures, one entry per provider. The rest of the write still succeeded. Usually `[]`. |

### `ActionError`

| Field | Type | Notes |
|---|---|---|
| `provider_id` | int | |
| `action` | `"ADD_TEMPLATE"` | |
| `error` | string | Raw reason. Log it; don't show it verbatim. |

---

## 3. Admin read endpoints

All of these are `403` when `scribe_appointment_rules` is off for the site.

### 3.1 `GET /appointment_rules`: Appointment Rules tab

| Query param | Type | Required | Notes |
|---|---|---|---|
| `facility_id` | int | no | Only counts providers mapped to that facility: `provider_count`, `providers_missing_template_count`, `total_provider_count` and `missing_rules`. The list of rules isn't filtered. |

**Response `200`**

| Field | Type | Notes |
|---|---|---|
| `appointment_types` | `AppointmentTypeRules[]` | Mapped types in alphabetical order, then unmapped types seen at the site in the last 180 days, also alphabetical |
| `total_provider_count` | int | |
| `missing_rules` | `MissingRulesSummary` | |

```json
{
  "appointment_types": [
    {
      "appointment_type": "Illness",
      "rules": [
        {"template_id": 12, "template_name": "WellNow - Base Template", "template_deleted": false,
         "is_default": true, "provider_count": 150, "providers_missing_template_count": 2},
        {"template_id": 45, "template_name": "WellNow - Ortho Template", "template_deleted": false,
         "is_default": false, "provider_count": 10, "providers_missing_template_count": 0}
      ]
    },
    {"appointment_type": "School Physical", "rules": []}
  ],
  "total_provider_count": 166,
  "missing_rules": {"provider_count": 2, "appointment_type_count": 1}
}
```

### 3.2 `GET /appointment_rules/providers`: side-panel provider list for one rule, or every site provider

| Query param | Type | Required | Notes |
|---|---|---|---|
| `appointment_type` | string | no | URL-encoded. Omit it to list every site provider (below); don't send it empty. PR 10 |
| `template_id` | int ≥ 1 | yes | With `appointment_type`: the rule. Without: the template `has_template` is checked against |
| `facility_id` | int | no | |
| `search` | string | no | Case-insensitive substring match on the name or email, trimmed |
| `page` | int ≥ 1 | no | Default `1` |
| `items_per_page` | int, 1–100 | no | If omitted, page 1 has 5 rows and later pages have 20, so page *n* ≥ 2 starts at offset `5 + (n − 2) × 20`. If set, every page has that many rows. |

Sorted by name (case-insensitive), then `provider_id`. All rows have the same `is_explicit`: `false` on the default rule and `true` on any other rule.

**Without `appointment_type` (PR 10):** returns every active site provider, the same set writes accept in `provider_ids` (§1), so providers with only Athelas accounts are left out. Used by the **Select providers** picker in the Add rule modal (§5.1, `apply_to: SELECTED`): the admin picks the template first, then sends its id as `template_id`. `has_template` says whether each provider has that template, and `is_explicit` is always `false`. There is no rule lookup, but `template_id` must be a live scribe template (the same check as §3.3), or the response is `404`. `search`, `facility_id` and paging work the same.

**Response `200`**

| Field | Type | Notes |
|---|---|---|
| `providers` | `RuleProvider[]` | |
| `page` | int | |
| `items_per_page` | int | The page size actually used for this page (5 or 20 when you didn't send one) |
| `total_count` | int | After `search` and `facility_id` |
| `total_pages` | int | `0` when `total_count` is `0` |

```json
{
  "providers": [
    {"provider_id": 881, "name": "Keiko Yamamoto", "email": "keiko@wellnow.example",
     "has_template": true, "is_explicit": false}
  ],
  "page": 1,
  "items_per_page": 5,
  "total_count": 150,
  "total_pages": 30
}
```

| Status | When |
|---|---|
| `200` with `providers: []` | Nothing matches `search`, or the rule covers 0 providers (see `provider_count`) |
| `404` | `appointment_type` sent and there is no rule for `(appointment_type, template_id)`: `"No appointment rule for that type and template"` |
| `404` | `appointment_type` omitted and the template doesn't exist, is deleted, or isn't a scribe template: `"Template not found"` |
| `422` | `items_per_page` > 100, `page` < 1, `appointment_type` sent empty, or a required param is missing |

### 3.3 `GET /appointment_rules/template_coverage`: Add/Edit modal preview

| Query param | Type | Required | Notes |
|---|---|---|---|
| `template_id` | int ≥ 1 | yes | |
| `facility_id` | int | no | |

**Response `200`**

| Field | Type | Notes |
|---|---|---|
| `template_id` | int | |
| `total_provider_count` | int | Site providers, after the facility filter |
| `providers_without_template` | `RuleProvider[]` | Providers who don't have the template. All have `has_template: false` and `is_explicit: false`. Sorted by name. |

The client intersects `providers_without_template` with its own selection to render text like "applies to 148 of 150; 2 providers don't have this template".

```json
{
  "template_id": 12,
  "total_provider_count": 150,
  "providers_without_template": [
    {"provider_id": 902, "name": "Adrian Ivanov", "email": "adrian.ivanov@wellnow.example",
     "has_template": false, "is_explicit": false}
  ]
}
```

| Status | When |
|---|---|
| `404` | The template doesn't exist, is deleted, or isn't a scribe template |

### 3.4 `GET /appointment_rules/missing`: missing-rules pop-up

| Query param | Type | Required | Notes |
|---|---|---|---|
| `facility_id` | int | no | |

**Response `200`**

| Field | Type | Notes |
|---|---|---|
| `groups` | `MissingRuleGroup[]` | One group per rule with at least one provider missing its template. Types are in alphabetical order. Within a type, the default comes first, then by `template_id`. |
| `summary` | `MissingRulesSummary` | Uses the same logic as `missing_rules` in §3.1 |

`MissingRuleGroup`

| Field | Type | Notes |
|---|---|---|
| `appointment_type` | string | |
| `template_id` | int | |
| `template_name` | string | `""` if the template has no name |
| `is_default` | bool | |
| `providers` | `RuleProvider[]` | All have `has_template: false`. Sorted by name. |

```json
{
  "groups": [
    {"appointment_type": "Workers' Comp", "template_id": 77,
     "template_name": "WellNow - Workers' Comp Template", "is_default": true,
     "providers": [
       {"provider_id": 902, "name": "Adrian Ivanov", "email": "adrian.ivanov@wellnow.example",
        "has_template": false, "is_explicit": false},
       {"provider_id": 903, "name": "Adrian Jelani", "email": "adrian.jelani@wellnow.example",
        "has_template": false, "is_explicit": false}
     ]}
  ],
  "summary": {"provider_count": 12, "appointment_type_count": 3}
}
```

**Resolving a group:** call `PATCH /appointment_rules/{template_id}?appointment_type=…` with only `providers_without_template` (§5.3). Only providers in that group are in scope.

The FE chooses which options to show for each group, using `GET /appointment_rules`. The backend doesn't enforce this.
- **The type has a default rule:** show "Add template to account" (`ADD_TEMPLATE`) and "Create personal rule" (`PERSONAL_RULES`).
- **The type has no default rule:** show only "Create personal rule". Acting is optional: the admin can close the pop-up, add a default, and come back.

### 3.5 Reused endpoints (unchanged)

| Endpoint | Used for |
|---|---|
| `GET /v1/scribe/admin_panel/site_user_template_assignments` | Template dropdown in the Add/Edit modal. Not for picking providers: rows are scribe accounts with no `provider_id`. Use `GET /providers` without `appointment_type` (§3.2). |
| `GET /v1/scribe/admin_panel/provider_groups/mapped_facilities_filter_options` | Facility filter options |

---

## 4. `providers_without_template`

Accepted by create, edit, move providers and delete. Set default doesn't take a body. This field lets the admin choose, for each provider, what happens when that provider doesn't have the template they are about to land on.

- It is optional: `null`, omitted or `[]` means no actions. A `provider_id` may appear only once, or the request gets a `422`. At most 1000 entries (§1).
- A provider who lacks the landing template and **isn't** listed still moves, and then shows up in missing rules.
- **Landing template:**
  - create: the new rule's template
  - edit: `new_template_id` if set, otherwise the rule's template
  - move: the target rule
  - delete: the type's default, or `new_default_template_id` when deleting the default
- **If there is no landing template, every entry is ignored and not validated.** That happens when you delete a non-default rule on a type with no default, or delete the last rule.
- **In scope:**

  | Endpoint | Providers in scope |
  |---|---|
  | create | The selected providers, or every site provider for `ALL` |
  | edit | `provider_ids` if sent, otherwise the providers the rule covers now |
  | move | `provider_ids` |
  | delete | The deleted rule's providers. For the default rule, that is everyone it covers. |

- Every entry is validated **before** anything is written. Any one of these fails the whole request with `400` and writes nothing:
  - the provider isn't in scope
  - the provider already has the landing template
  - `PERSONAL_RULES` has no template to use (see below)

| Action | Effect |
|---|---|
| `ADD_TEMPLATE` | The provider stays on the landing rule. **After** the rule write commits, the landing template is added to every enabled scribe account the provider has at the site. If the template is already active on an account, that account isn't changed. Otherwise the template is added or reactivated so it never becomes the account's primary template. If the account has numbered priorities, it gets the highest number plus one. If none are numbered, it is added without a priority; when its id is lower than the current primary's, the current primary is given priority `1` so it stays first. If this fails, the provider is still on the rule (and still missing), and the failure appears in `errors`. Some of the provider's accounts may already have been updated. To retry, resolve the provider from the missing pop-up. |
| `PERSONAL_RULES` | The provider is pinned to a rule with a template they have, instead of the landing template. This is applied in the same transaction as the rule write, as its last step. |

**Which template `PERSONAL_RULES` uses:**
1. The provider's current non-default rule for the type, unless it's the rule this write is moving them off: the rule being edited or deleted, or the landing rule.
2. Otherwise, the provider's **primary template**: the usable template with the lowest `priority` on their account, with no-priority templates last and ties broken by the lower `template_id`.
3. If neither exists, the whole request fails with `400`.

| The chosen template is… | Result |
|---|---|
| Already a non-default rule for the type | The provider joins that rule |
| Not a rule for the type yet | A new non-default rule is created with just this provider |
| The type's default template | The provider's pin is removed, and the default covers them |

Moving a provider can delete their previous rule if they were its last provider. That includes the default (§1).

---

## 5. Admin write endpoints

Every write returns a `WriteResponse` (§2). Every route except create addresses an existing rule:

| Param | In | Type | Required | Notes |
|---|---|---|---|---|
| `template_id` | path | int | yes | The rule's template. For move, this is the **target** rule. |
| `appointment_type` | query | string | yes | URL-encoded. At least 1 character. |

### 5.1 `POST /appointment_rules`: add a rule

| Field | Type | Required | Notes |
|---|---|---|---|
| `appointment_type` | string | yes | Trimmed. Must not be blank. |
| `template_id` | int ≥ 1 | yes | At least one provider at the site must have it |
| `is_default` | bool | yes | |
| `apply_to` | `"ALL"` \| `"SELECTED"` | yes | |
| `provider_ids` | int[] | no | Must be empty or omitted for `ALL`, and non-empty for `SELECTED`. Duplicates are removed. Every id must be a site provider (§1). |
| `providers_without_template` | `ProviderWithoutTemplate[]` \| null | no | |

```json
{
  "appointment_type": "Illness",
  "template_id": 45,
  "is_default": false,
  "apply_to": "SELECTED",
  "provider_ids": [881, 882],
  "providers_without_template": null
}
```

| `apply_to` | `is_default` | Result |
|---|---|---|
| `ALL` | `true` | The new rule becomes the default, and **every pin for the type is removed, including picks providers made themselves (§8)**. Everyone, now and in future, uses the new rule, and all other rules for the type stop existing. Product decided the UI shows **no** warning for this. |
| `ALL` | `false` | Every current site provider is pinned to the new rule. The other non-default rules stop existing, and so does the default, since it no longer covers anyone. Providers added later get no rule for the type. |
| `SELECTED` | `false` | The listed providers are pinned to the new rule, moving off any other rule. A rule left with no providers stops existing; if that's the default, see §1. |
| `SELECTED` | `true` | The new rule becomes the default and the old default stops existing. The listed providers' pins are removed, so they fall to the new default. Providers who were on the old default and weren't listed are pinned to the old template, so their template doesn't change. Unlisted providers on other rules stay there. |

**Response:** `201 WriteResponse`.

| Status | When |
|---|---|
| `400` | No provider at the site has the template; the template has been deleted; some `provider_ids` aren't site providers; or a `providers_without_template` entry fails validation (§4) |
| `409` | The template is already a rule for the type |
| `422` | `provider_ids` or `providers_without_template` has more than 1000 items |

### 5.2 `PUT /appointment_rules/{template_id}/default`: make a rule the default

There is no body.

```
PUT /v1/scribe/admin_panel/appointment_rules/45/default?appointment_type=Illness
```

| Case | Result |
|---|---|
| The rule isn't the default | It becomes the default. The old default's providers move to it, and the old default stops existing. Providers pinned to this rule stay on it, now covered by the default. |
| The rule is already the default | Nothing changes, and the current state is returned |

Providers who don't have the new default's template aren't handled here; they show up in `missing_rules`.

**Response:** `200 WriteResponse`. Returns `404` if there's no such rule, and `400` if the rule isn't the default and its template has been deleted (no provider could use it). Re-running on the current default still succeeds.

### 5.3 `PATCH /appointment_rules/{template_id}`: edit a rule

This is a partial update: fields that are omitted or `null` aren't changed. If every field is empty, the call changes nothing and returns `200` with the current state.

| Field | Type | Required | Notes |
|---|---|---|---|
| `new_template_id` | int ≥ 1 \| null | no | Points the rule at another template, which at least one provider at the site must have. If a rule for that template already exists, the two rules merge; if either was the default, the merged rule is the default. Pointing a non-default rule at the default's template moves its providers into the default. The rule's URL changes to the new `template_id`, so refresh from the response. |
| `provider_ids` | int[] \| null | no | Replaces the rule's pinned providers, and removed providers fall to the default. Adding providers who were on the default can leave it empty, and then it is deleted (§1). Must be non-empty if sent (to remove everyone, delete the rule). Duplicates are removed. Not allowed on the default rule, or together with a `new_template_id` that is the default's template. |
| `providers_without_template` | `ProviderWithoutTemplate[]` \| null | no | |

Change the template:

```
PATCH /v1/scribe/admin_panel/appointment_rules/45?appointment_type=Illness
```

```json
{"new_template_id": 46}
```

Resolve a missing-rules group (the rule doesn't change; only the actions run):

```
PATCH /v1/scribe/admin_panel/appointment_rules/77?appointment_type=Workers%27%20Comp
```

```json
{
  "providers_without_template": [
    {"provider_id": 902, "action": "ADD_TEMPLATE"},
    {"provider_id": 903, "action": "PERSONAL_RULES"}
  ]
}
```

Edit never changes which rule is the default. Use `PUT /{template_id}/default` for that.

**Response:** `200 WriteResponse`.

| Status | When |
|---|---|
| `400` | `provider_ids` sent on the default rule; `provider_ids` sent with a `new_template_id` that is the default's template; no provider at the site has `new_template_id`; `new_template_id` has been deleted; some `provider_ids` aren't site providers; or a `providers_without_template` entry fails validation |
| `404` | There's no such rule |
| `422` | `provider_ids: []`, or `provider_ids` or `providers_without_template` has more than 1000 items |

### 5.4 `PATCH /appointment_rules/{template_id}/providers`: move providers onto a rule

`template_id` is the rule the providers move **to**, and it must already exist for the type.

| Field | Type | Required | Notes |
|---|---|---|---|
| `provider_ids` | int[] | yes | At least one. Duplicates are removed. All must be site providers. |
| `providers_without_template` | `ProviderWithoutTemplate[]` \| null | no | |

```
PATCH /v1/scribe/admin_panel/appointment_rules/12/providers?appointment_type=Illness
```

```json
{"provider_ids": [881]}
```

Moving providers to the default removes their pins. A rule that loses its last provider stops existing, and that includes the default (§1). The FE should confirm with the admin before moving a rule's last provider.

**Response:** `200 WriteResponse`.

| Status | When |
|---|---|
| `400` | Some `provider_ids` aren't site providers, or a `providers_without_template` entry fails validation |
| `404` | There's no such rule |
| `422` | `provider_ids` is empty, or `provider_ids` or `providers_without_template` has more than 1000 items |

### 5.5 `DELETE /appointment_rules/{template_id}`: delete a rule

This route takes an optional JSON body, and sending no body is the same as `{}`. Check that the FE HTTP client sends bodies on `DELETE`.

| Field | Type | Required | Notes |
|---|---|---|---|
| `new_default_template_id` | int ≥ 1 \| null | conditional | Required when deleting the default while other rules exist. It must be one of those other rules. |
| `providers_without_template` | `ProviderWithoutTemplate[]` \| null | no | Ignored when there's no landing template (§4) |

```
DELETE /v1/scribe/admin_panel/appointment_rules/12?appointment_type=Illness
```

```json
{
  "new_default_template_id": 45,
  "providers_without_template": [{"provider_id": 902, "action": "ADD_TEMPLATE"}]
}
```

| Rule deleted | Result |
|---|---|
| Non-default, and the type has a default | Its providers fall to the default |
| Non-default, and the type has no default | Its providers no longer have a rule for the type |
| Default, and other rules exist | The `new_default_template_id` rule becomes the default, and the old default's providers move to it |
| Default, and no other rules exist | The type is unmapped again (`rules: []`) |

**Response:** `200 WriteResponse`.

| Status | When |
|---|---|
| `400` | You're deleting the default while other rules exist, and `new_default_template_id` is missing or isn't one of them |
| `400` | `PERSONAL_RULES` would put a provider back on the rule being deleted, because its template is the provider's primary template. Use `ADD_TEMPLATE` for that provider, or leave them out. |
| `400` | A `providers_without_template` entry fails validation |
| `404` | There's no such rule |
| `422` | `providers_without_template` has more than 1000 items |

---

## 6. Admin errors (all endpoints)

| Status | Endpoint(s) | When |
|---|---|---|
| `400` | all | The caller's site couldn't be resolved |
| `400` | writes | The cases listed under each endpoint in §5 |
| `403` | all | The caller isn't a site admin, `scribe_admin_panel` is off for the caller, or `scribe_appointment_rules` is off for the site |
| `404` | `GET /providers`, `PATCH /{id}`, `PUT /{id}/default`, `PATCH /{id}/providers`, `DELETE /{id}` | There's no rule for `(appointment_type, template_id)` |
| `404` | `GET /template_coverage` | Unknown, deleted or non-scribe template |
| `409` | `POST /` | The template is already a rule for the type |
| `409` | writes | The write conflicted with a concurrent change. Refetch and retry. |
| `422` | all | Request validation (see each endpoint) |
| `500` | writes | `"Appointment rule was <done> but the updated list could not be loaded"`. **The write succeeded**: refetch `GET /appointment_rules` and don't retry. Any other `500` means nothing was written. |

---

## 7. Changed existing endpoints

### 7.1 `POST /v1/scribe/appointments/visits_paginated`

The request and response shapes don't change. `ScribeVisit.template_id_to_use: int | null` is still filled only when `scribe_auto_select_template` is on.

**When `scribe_appointment_rules` is on**, the server picks a template for the viewer:
1. The rendering provider's pin for the appointment type, if there is one. Rules pinned to other providers are never candidates.
2. Otherwise, the type's default rule.
3. `null` if there's no rule, or the viewer doesn't have the chosen template. A pin the viewer can't use does **not** fall back to the default. When the value is `null`, the client keeps its existing fallback to the viewer's primary template.

**When it's off**, the old behavior applies: default rows only, and if several match, the viewer's highest-ranked template wins.

### 7.2 Pre-chart drafts (`POST /v1/scribe/pre_chart/refresh/{id}` and the nightly sweep)

The request and response shapes don't change. The draft template is resolved the same way as §7.1, using the appointment's rendering provider, and is checked against the drafting account. `null` keeps the existing fallback to that account's primary template. A refresh without `template_id` goes through the same resolution.

A rule write doesn't touch drafts that already exist (up to the 3-day horizon). They keep the template they were built on, and the visit list pre-selects the new one.

### 7.3 v0 `/v1/scribe/admin_panel/appointment_type_templates` (PR 3, open)

| Route | `scribe_appointment_rules` off | `scribe_appointment_rules` on |
|---|---|---|
| `GET /` | Returns default rows only (`provider_id IS NULL`). The response gains `provider_id`, which is always `null`. | Same |
| `POST /` | `409` if the type already has a default | `409` |
| `PUT /{id}` | `404` unless the row is a default row | `409` |
| `DELETE /{id}` | `404` unless the row is a default row | `409` |

These routes are removed after the new UI ships to all sites (PR 11).

---

## 8. Provider endpoints (Note Preferences card)

The card lists the provider's most frequent appointment types, each with a template dropdown. A **View all appointments** drawer lists every type in the same format. A provider's pick is stored exactly like an admin pin, so the admin panel shows it as a non-default rule, and it counts toward that rule's `provider_count`.

**Access:** these endpoints return `403` unless **both** of these hold: `scribe_appointment_rules` is on for the caller's site, and `scribe_appointment_rules_provider_view` is on for the caller's account. They also return `403` if the caller has no provider or no site. Show or hide the card using `feature_flags` from `user_info`, which already includes both flags.

### `ProviderRuleItem`

| Field | Type | Notes |
|---|---|---|
| `appointment_type` | string | |
| `template_id` | int \| null | The template the caller gets for this type right now, resolved with the same logic as §7.1 for the caller's own account: their pin (theirs or an admin's), otherwise the default. `null` if there's no rule, or the caller doesn't have the chosen template. The app then uses the provider's primary template. |
| `template_name` | string \| null | `null` whenever `template_id` is `null` |

### 8.1 `GET /v1/scribe/appointment_rules/me`

| Query param | Type | Required | Notes |
|---|---|---|---|
| `scope` | `"top"` \| `"all"` | no | Default `top`. Any other value returns `422`. |

- **`top`**: the caller's 7 most frequent appointment types, counted from appointments where they are the rendering provider at the site in the last 180 days. Cancelled, no-show, archived and deleted visits don't count. Sorted by count, highest first, then by name. Only types the caller has actually seen are included, so a new provider gets `items: []`.
- **`all`**: every type the caller has seen, every type seen at the site in the last 180 days, and every type that has a rule. Sorted by the caller's count, highest first, then types the caller hasn't seen, alphabetically. Capped at 500. There's **no server-side search or paging**; the client filters the list.

Render the rows in the order they arrive.

**Response `200`**

```json
{
  "items": [
    {"appointment_type": "Illness", "template_id": 45, "template_name": "WellNow - Ortho Template"},
    {"appointment_type": "Injury", "template_id": 12, "template_name": "WellNow - Base Template"},
    {"appointment_type": "Workers' Comp", "template_id": null, "template_name": null}
  ]
}
```

**Page load:** make one call when Note Preferences opens, `GET /me?scope=top`. It isn't part of `user_info`. The dropdown options are the provider's own templates (`GET /v1/scribe/templates/user_templates`). The drawer calls `?scope=all` when it opens.

### 8.2 `PUT /v1/scribe/appointment_rules/me`: choose a template

| Body field | Type | Required | Notes |
|---|---|---|---|
| `appointment_type` | string | yes | Trimmed. Must not be blank. Sent in the body, so it needs no URL-encoding. |
| `template_id` | int | yes | Must be active on the caller's own account, not deleted, and a scribe template |

```json
{"appointment_type": "Illness", "template_id": 45}
```

| Case | Result |
|---|---|
| The caller has no pick yet, or already has one | The pick is created or replaced. If this moves the caller off another rule and they were its last provider, that rule stops existing. This includes the default, which is deleted if every site provider is now pinned (§1). |
| `template_id` is the type's default | The pick is **removed**, so the caller follows the default. This is how a provider goes back to the site default. |
| The type has no default | The pick is still created |

Sending the same pair twice gives the same result, so retrying is safe.

**Response:** `200 ProviderRuleItem`, re-read from the primary after the write. Update the row in place with it.

| Status | When |
|---|---|
| `400` | `"Template is not one of your active scribe templates"` |
| `403` | A flag is off, or the caller has no provider or site |
| `409` | Conflict with a concurrent write. Retry. |
| `422` | `appointment_type` is blank or missing, or `template_id` is missing |

**Limits:**
- A provider can't remove a pick on a type that has no default, because there's no reset route.
- An admin `ALL` + default create (§5.1) erases every provider's pick for that type.
- Provider writes aren't written to the admin action log.

---

## 9. Decisions (2026-10-21)

1. **Empty default (OQ1):** the default rule is deleted automatically once every provider is pinned to another rule. It's kept while the type has no other rule (§1).
2. **Admin `ALL` + default wiping provider picks:** allowed, with **no** warning in the UI (§5.1).
3. **Athelas accounts:** `ADD_TEMPLATE` uses the same Athelas-account filter as every other endpoint, applied in production only, so staging behaves the same everywhere.

---

## 10. Changes from the 2026-10-08 / 2026-10-13 / 2026-10-21 specs

| Area | Before | Now |
|---|---|---|
| Site provider list (2026-10-25) | No endpoint returned every site provider with `provider_id` | `GET /providers` without `appointment_type` (§3.2, PR 10) |
| `ADD_TEMPLATE` timing | Ran before the rule write | Runs after the rule write commits. Same result for the user, and a failed write no longer adds anything. |
| `ADD_TEMPLATE` reactivation (OQ6) | Pending | Never becomes the primary template: it is added or reactivated at the lowest priority |
| `PERSONAL_RULES` target (OQ3) | Primary template; which account wins was pending | The provider's existing non-default rule wins first, then the primary template on the provider's one account |
| `PERSONAL_RULES` → default (OQ2) | Pending | Confirmed: the provider falls to the default |
| No landing template | Not covered | `providers_without_template` is ignored |
| New `400`s | — | Create, edit `new_template_id` or set default on a deleted template; edit `provider_ids` with a `new_template_id` that is the default's template; delete with `PERSONAL_RULES` pointing back at the deleted rule; site can't be resolved |
| "Template isn't active at the site" `400` | All writes | Only on create, and on edit with `new_template_id` |
| `template_coverage` | No error listed | `404` for an unknown, deleted or non-scribe template |
| `/providers` paging | — | `items_per_page` is capped at 100, and the response echoes the page size actually used |
| `409` / `500` | `409` only for a duplicate create | Also `409` for concurrent-write conflicts, and a `500` that means the write succeeded but the response couldn't be built |
| `appointment_type` | Matched byte-for-byte | The same, but request **bodies** trim leading and trailing whitespace |
| List ordering | Not specified | Mapped types alphabetical, then unmapped types (180-day window) alphabetical. The missing groups are ordered too (§3.4). |
| `template_name` | string | `""` when the template has no name |
| Flags | Rules were read when either flag was on (provider spec §6.2) | Only `scribe_appointment_rules` turns rules on. The provider-view flag only gates `/me`. |
| §7.1 flag off | "Default rule only" | Old v0 behavior (default rows, ranked by the viewer) |
| Drafts on rule change (OQ5) | Pending | Left as they are |
| Provider `GET /me` item | "Their pick, else the default" | A pick or default the caller can't use shows `null` |
| Provider frequency (§6.1) | Pending | Top 7 over 180 days, excluding cancelled, no-show, archived and deleted |
| Reused endpoint paths | Some had no `/v1` | Full `/v1/scribe/...` paths |
| Empty default (OQ1) | Kept with 0 providers; still covers future providers | Deleted once everyone is pinned elsewhere. Kept only if the type has no other rule. |
| Admin `ALL` + default | Warning to be decided | No warning |
