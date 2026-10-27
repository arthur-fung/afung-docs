# Appointment Mapping QA bug list (2026-10-27)

Found during staging QA (site 4) of the admin panel **Template Library → Appointment Mapping** screen ([scribe-mobile#6397](https://github.com/getathelas/scribe-mobile/pull/6397)). API contract: [Template Appointment Linking — Frontend API Spec](https://arthur-fung.github.io/afung-docs/20261025-template-appointment-linking-fe-api-spec.html) ("spec §N" below).

| # | Bug | Repo |
|---|---|---|
| 1 | Rule card count includes providers missing the template | `scribe-mobile` |
| 2 | Side panel can't list only the providers who have the template | `normandy` |
| 3 | Add Rule template dropdown offers the wrong templates | `scribe-mobile` |
| 4 | Review (missing-template) pop-up display | `scribe-mobile` |
| 5 | Rule card treats the first rule as the default | `scribe-mobile` |
| — | Other issues on the same screen | `scribe-mobile` |

## Bug 1: rule card count `scribe-mobile`

Each rule card shows "N Providers" using `provider_count`, which counts every provider the rule **covers**, including providers who don't have the rule's template. Those providers don't get the template: their visits fall back to their primary template (spec §7.1). So the card overstates how many providers use the template.

**Expected:** the card shows the providers who actually get the template:

```
provider_count - providers_missing_template_count
```

Providers missing the template are already surfaced and resolved through the missing-rules banner ("N providers are missing template mapping for M appointments" → **Review**).

Example (staging site 4):

| Rule | `provider_count` | `providers_missing_template_count` | Shows today | Should show |
|---|---|---|---|---|
| Follow Up → SOAP Template (default) | 14 | 3 | 14 Providers | **11 Providers** |
| MD New Patient 30 → SOAP Note (default) | 13 | 8 | 13 Providers | **5 Providers** |
| MD New Patient 30 → Progress Note | 1 | 1 | 1 Providers | **0 Providers** |
| New Patient → SOAP Note (default) | 14 | 8 | 14 Providers | **6 Providers** |

Both numbers are already on every rule in `GET /v1/scribe/admin_panel/appointment_rules` and in every write response (`RuleSummary`, spec §2):

```json
{"template_id": 1362, "template_name": "SOAP Template", "template_deleted": false,
 "is_default": true, "provider_count": 14, "providers_missing_template_count": 3}
```

**Fix:** frontend only; no backend change.

Related:

- **Side panel must match the card.** See Bug 2.
- **0 count.** If every covered provider lacks the template, the card reads "0 Providers" while the rule still exists and still covers them (deleting it moves them). Consider "0 Providers · 3 missing" for that case.
- **Spec:** add the display rule to spec §2 / §3.1.

## Bug 2: side panel can't list only the providers who have the template `normandy`

Clicking a rule's template opens the side panel, backed by `GET /v1/scribe/admin_panel/appointment_rules/providers?appointment_type=…&template_id=…` (spec §3.2). It returns every **covered** provider, including those without the template:

```json
{
  "providers": [
    {"provider_id": 7, "name": "…", "email": "…", "has_template": false, "is_explicit": false}
  ],
  "page": 1, "items_per_page": 5, "total_count": 14, "total_pages": 3
}
```

With Bug 1 fixed the card says 11, but the panel lists 14. The FE can't fix this on its own:

- Each row has `has_template`, but there is no `has_template` filter param (only `facility_id`, `search`, `page`, `items_per_page`).
- Paging is server-side (5 rows on page 1, then 20) and `total_count` / `total_pages` include the missing providers. Filtering rows client-side leaves short pages ("3 of 5") and totals that don't match the card.
- `search` runs server-side, so search results also include missing providers.

**Expected:** the panel lists only providers who have the template, with totals matching the card (11 for Follow Up → SOAP Template).

**Fix (`normandy`):** add an optional `has_template` query param to `GET /appointment_rules/providers`, applied before paging so `total_count` / `total_pages` match:

- `has_template=true`: providers who have the template (the side panel)
- `has_template=false`: covered providers missing it
- omitted: today's behavior (all covered providers)

Update spec §3.2 first, then the endpoint and its tests. Follow-up in `scribe-mobile`: the side panel passes `has_template=true`.

Workaround until then: the FE fetches every page (`items_per_page=100`) and filters on `has_template`. Fine for small sites like site 4 (14 providers), heavy for large ones.

## Bug 3: Add Rule template dropdown offers the wrong templates `scribe-mobile`

On a type's **+ Add Rule**, the template dropdown lists templates that are already a rule for that type.

Cause (`scribe-mobile`: `lib/src/features/admin_panel_template_manager/views/appointment_mapping/appointment_mapping_viewmodel.dart:102`): the options come from `templateOptions`, which collects every template used by **any rule on the site**, across all types:

```dart
/// Templates referenced by any currently mapped rule ...
List<AppointmentRuleTemplateOption> get templateOptions {
  for (final at in _appointmentTypes) {
    for (final rule in at.rules) { counts[rule.templateId] = ... }
  }
  ...
}
```

| # | Problem | Effect |
|---|---|---|
| 3a | Templates already a rule for this type aren't excluded | Picking one returns `409 "The template is already a rule for the type"` |
| 3b | Only templates already used by some rule are offered | Site templates no rule uses yet can't be picked. On staging site 4 the options are only SOAP Template, SOAP Note and Progress Note; Daily Note, Meeting Note etc. are missing |
| 3c | Add is disabled when the site has no rules (`enabled: _viewModel.templateOptions.isNotEmpty`) | A site can't create its first rule |

**Expected (spec §3.5):** the Add / Change template dropdown comes from the site's template catalogue, `GET /v1/scribe/admin_panel/site_user_template_assignments` (the code's comment points at `AppointmentRuleTemplateOption.rankedFromAssignments`). For Add Rule on a type, exclude templates that already have a rule for that type. Add must be enabled even when the site has no rules.

**Fix:** frontend only.

## Bug 4: Review (missing-template) pop-up display `scribe-mobile`

Backend data is correct: each group's providers and counts match `GET /appointment_rules/missing` (spec §3.4). The pop-up has display issues.

`/missing` response on staging site 4 at the time:

| Group | `is_default` | Providers |
|---|---|---|
| Follow Up → Progress Note | false | 2 |
| MD New Patient 30 → SOAP Note | **true** | 8 |
| MD New Patient 30 → Progress Note | false | 1 |
| New Patient → SOAP Note | false | 8 |

| # | Issue | Expected |
|---|---|---|
| 4a | Every group shows a **Default** badge, including the three with `is_default: false` | Show the badge only when the group's `is_default` is true (here only MD New Patient 30 → SOAP Note) |
| 4b | **Add template to N accounts** is offered on every group, including types with no default (Follow Up and New Patient had no default rule at the time) | Spec §3.4: when the type has no default rule (no `is_default: true` rule for it in `GET /appointment_rules`), show only the personal-rule option. Also hide it when the group's template is deleted (`template_deleted`) |
| 4c | Avatar initials overflow the circle ("DEE PTI", "ABC DEF") | 1–2 initials that fit |
| 4d | The personal-rule button label is truncated ("Use their personal default …") | Full label, or a shorter one (spec name: "Create personal rule") |

**Fix:** frontend only.

## Bug 5: rule card treats the first rule as the default `scribe-mobile`

The **Default** badge on the Appointment Mapping cards comes from the rule's position, not from the API's `is_default` (`scribe-mobile`: `lib/src/features/admin_panel_template_manager/views/appointment_mapping/appointment_mapping_view.dart:416`):

```dart
isDefault: i == 0,
```

The spec puts the default first, but a type can have **no** default (for example after "All providers" without "default", which pins everyone and deletes the default, spec §5.1 / §1). The first rule is then just the largest non-default rule, and the card still says Default.

Staging site 4: the card shows **Follow Up → Progress Note · Default · 14 Providers**, while `GET /appointment_rules` returns:

```json
{"template_id": 64, "template_name": "Progress Note", "template_deleted": false,
 "is_default": false, "provider_count": 14, "providers_missing_template_count": 2}
```

The same assumption feeds the side panel: `defaultTemplateId` is taken from the first rule (`appointment_mapping_view.dart:449`), so a non-default rule can be treated as the default (hiding **Set as default**, or requiring a new default when deleting it).

**Expected:** use each rule's `is_default` for the badge and for `defaultTemplateId` (null when the type has no default). Same root cause as Bug 4a.

**Fix:** frontend only.

## Other issues on the same screen `scribe-mobile`

- Appointment types lose acronym casing: "Md New Patient 30", "Qa Follow Up" (actual `MD New Patient 30`, `QA Follow Up`). Display-only casing is fine, but requests must send the exact original string, since type matching is exact.
- "1 Providers" should be "1 Provider".
