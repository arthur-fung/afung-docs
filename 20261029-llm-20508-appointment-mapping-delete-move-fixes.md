# LLM-20508 — Appointment mapping: Delete and Move fixes

PRs: scribe-mobile #6406 (`b0b7a442b`) and #6407 (`2ac41510a`).

Files are under `lib/src/features/admin_panel_template_manager/views/appointment_mapping/`.

API spec: [Provider templates + rule-scoped template coverage](20261028-llm-20508-provider-templates-and-rule-scoped-coverage-api-spec.md) §3 "What to call" (below as "spec §3"), and [Template Appointment Linking — FE API spec](20261025-template-appointment-linking-fe-api-spec.md) §5.5 (delete).

| # | Issue | Fix |
|---|---|---|
| 1 | Change template / Delete send `rule_template_id` = the picked template | Rebase #6407 onto #6406 `b0b7a442b` |
| 2 | Deleting a non-default rule asks for a template the backend ignores, then moves only some providers | No picker on non-default delete; coverage for the default; drop the follow-up move |
| 3 | Move provider never checks whether the provider has the target template | Call `GET /providers/{id}/templates` on Move; send `providers_without_template` when missing |

Fix them in this order. Fixing 1 makes 2 louder: once coverage returns real providers, the non-default delete gets a 400.

---

## 1. Change template / Delete send `rule_template_id` = the picked template

`delete_rule_dialog.dart:127-138`, `change_template_dialog.dart:~116` (#6407)

When a template is picked, the coverage call sends the same ID twice. `rule_template_id` must identify the rule being changed (its current template). The backend looks up a rule that doesn't exist, returns 404 `No appointment rule for that type and template`, and the dialog treats that as "nobody missing". The write then goes out with `providers_without_template: []`.

#6406 already fixed this in `b0b7a442b`. #6407 isn't rebased onto it.

AS-IS (#6407 `2ac41510a`)
```dart
.templateCoverage(
  templateId: templateId,
  appointmentType: widget.appointmentType,
  ruleTemplateId: templateId,
)
```

TO-BE (already in #6406 `b0b7a442b`)
```dart
.templateCoverage(
  templateId: templateId,
  appointmentType: widget.appointmentType,
  // The rule being deleted (its current template), not the candidate.
  ruleTemplateId: widget.currentTemplateId,
)
```

### Reproduce

**Setup:** `Follow Up` has two rules:
- **Progress Note** (64), default, apply to All.
- **Meeting Note** (65), Select providers → Jorge.

**A. Change template**
1. Click the **Meeting Note** rule to open its side panel.
2. Click **Change template** and pick **Daily Note** (79). Jorge doesn't have it.
3. In Network, find `GET …/template_coverage`.

| | Request | Response | Dialog |
|---|---|---|---|
| Actual | `template_id=79&appointment_type=Follow Up&rule_template_id=79` | **404** `No appointment rule for that type and template` | Says every provider has the template; no missing-template choice |
| Expected | `template_id=79&appointment_type=Follow Up&rule_template_id=65` | 200, `providers_without_template` = [Jorge] | Lists Jorge with "Add to their account / Use their personal default" |

4. Click **Apply**. The `PATCH …/appointment_rules/65` body has no `providers_without_template`. After the write, the missing-rules banner shows Jorge.

**B. Delete (default rule)**: start from the Setup above. If you ran A step 4, change the rule back to Meeting Note first.
1. Add one more rule: `Follow Up` → **SOAP** (1362), Select providers → Deepti Test2.
2. Click the **Progress Note** (default) rule → **Delete Rule** → pick **Meeting Note** (65) as the new default.
3. `template_coverage` actual: `template_id=65&…&rule_template_id=65` → 404. Expected: `rule_template_id=64` → 200.

**Fix:** rebase #6407 onto #6406 `b0b7a442b`. Re-run A and B: both requests use the rule's current template and return 200.

---

## 2. Deleting a non-default rule asks for a template the backend ignores, then moves only some providers

`delete_rule_dialog.dart` (#6406), `rule_detail_panel.dart:244-280` (#6407)

**Spec (§5.5):** deleting a **non-default** rule sends its providers to the type's **default**. The admin picks a template only when deleting the **default** (`new_default_template_id`). Spec §3:

| Scenario | Call |
|---|---|
| Delete a non-default rule (the type has a default) | `GET /template_coverage?template_id={default}&appointment_type={type}&rule_template_id={rule}` |
| Delete the default (other rules exist) | `GET /template_coverage?template_id={new_default_template_id}&appointment_type={type}&rule_template_id={default}` |
| Delete when there's nowhere to land (no default, or the last rule) | No call; skip the missing-template step |

**What the code does:** the dialog asks "Which template should they use instead?" for every rule. For a non-default rule X with pick T:
1. `DELETE X`. The backend moves **all** of X's providers to the default D.
2. The panel then moves `_providers` to T. That list is the panel's display list: at most 100, narrowed by the search box, and only providers with `hasTemplate: true`.

So some providers end up on T and the rest on D. `providers_without_template` is also built for T, but the backend checks it against D. Once #1 is fixed, that returns 400 `Provider … already has the landing template`.

### Reproduce

**Setup:** `Follow Up` has three rules:
- **D** = Progress Note (64), default, apply to All.
- **X** = Meeting Note (65), Select providers → Deepti Test1, Deepti Test2, Deepti RANA001.
- **T** = SOAP (1362), Select providers → Jorge.

**Steps**
1. Click rule **X**. The side panel lists Deepti Test1, Deepti Test2 and Deepti RANA001.
2. Type `test` in the panel's provider search. Only Deepti Test1 and Deepti Test2 are listed.
3. Click **Delete Rule**. The dialog asks "Which template should they use instead?". Pick **T** (SOAP) and confirm.
4. In Network, look at the requests the delete sends.

| | Requests | Result |
|---|---|---|
| Actual | `DELETE …/appointment_rules/65?appointment_type=Follow Up`, then `PATCH …/appointment_rules/1362/providers` with `provider_ids` = [Deepti Test1, Deepti Test2] | Test1 and Test2 are on **T** (SOAP), RANA001 is on **D** (Progress Note) |
| Expected | Only `DELETE …/appointment_rules/65`. No template picker in the dialog | All three are on **D**, the default |

Other ways to trigger it: a provider on X who lacks Meeting Note (hidden by `hasTemplate: true`), or a rule with more than 100 providers. In both cases, providers missing from the panel list end up on D.

**After #1 is fixed:** the dialog builds `providers_without_template` for T, but the backend checks it against D. If any provider on X lacks SOAP but has Progress Note, `DELETE` returns **400** `Provider … already has the landing template`.

### `delete_rule_dialog.dart` (#6406)

AS-IS
```dart
// Picker shown for every rule; coverage computed for the picked template
onChanged: (id) {
  setState(() { _selectedTemplateId = id; _coverageProviders = []; });
  _loadCoverage(id);
},
...
final canApply = _selectedTemplateId != null && !_isSaving;
...
await widget.onConfirm(
  newDefaultTemplateId: widget.isDefault ? _selectedTemplateId : null,
  providersWithoutTemplate: providersWithoutTemplate,
);
if (mounted) Navigator.of(context).pop(_selectedTemplateId);
```

TO-BE
```dart
@override
void initState() {
  super.initState();
  // Non-default: providers land on the default, so check coverage for it now.
  if (!widget.isDefault && widget.defaultTemplateId != null) {
    _loadCoverage(widget.defaultTemplateId!);
  }
}

// Picker only when deleting the default
onChanged: (id) {
  setState(() { _selectedTemplateId = id; _coverageProviders = []; });
  _loadCoverage(id);
},
...
final canApply = !_isSaving && (!widget.isDefault || _selectedTemplateId != null);
...
await widget.onConfirm(
  newDefaultTemplateId: widget.isDefault ? _selectedTemplateId : null,
  providersWithoutTemplate: providersWithoutTemplate,
);
if (mounted) Navigator.of(context).pop(true);

// build
if (widget.isDefault)
  EclipseSelectField<int>(hint: 'Select new default', ...)
else
  Text(widget.defaultTemplateId != null
      ? '$n providers will move to the default template.'
      : '$n providers will no longer have a rule for this type.'),
```

`_loadCoverage` keeps `ruleTemplateId: widget.currentTemplateId` (#1). When there's no default and the rule isn't the default, skip coverage: there's nowhere to land.

### `rule_detail_panel.dart:244-280` (#6407)

AS-IS
```dart
final targetTemplateId = await showDeleteRuleDialog(...);
// After delete succeeds, move all providers to the selected template
if (targetTemplateId != null) {
  if (_providers.isNotEmpty) {
    await widget.onMoveProvider(
      targetTemplateId: targetTemplateId,
      providerIds: _providers.map((p) => p.providerId).toList(),
    );
  }
  if (mounted) widget.onClose();
}
```

TO-BE
```dart
final deleted = await showDeleteRuleDialog(...);
if (deleted == true && mounted) widget.onClose();
```

The backend moves every provider on the rule in the same request, so the 100-provider, search-box and `hasTemplate` limits no longer apply.

**After the fix:** re-run the repro. There's no picker, and the dialog says the providers will move to the default. Only `DELETE` is sent, all three providers are on D, and the `DELETE` body has entries only for providers who lack Progress Note.

---

## 3. Move provider never checks whether the provider has the target template

`move_provider_dialog.dart` (#6406 and #6407)

**Spec §3:**

| Scenario | Call |
|---|---|
| Move providers onto a rule | `GET /providers/{provider_id}/templates` for each selected provider; missing = target template not in `templates` |

"Call when the action is confirmed, not from data loaded earlier." (`template_coverage` is for Change template and Delete, not Move.)

**What the code does:**
- #6407: no check. Every other rule is listed, and `PATCH /{target}/providers` never sends `providers_without_template`.
- #6406: loads `providerTemplates` once on open and **hides** rules the provider lacks. It still never sends entries, and the missing-template choice can't be reached.

Backend: with no entry, a provider who lacks the target is pinned anyway and shows as missing. An entry for a provider who has the template gets 400 `already has the landing template`.

### Reproduce

**Setup:** `Follow Up` has three rules:
- **D** = Progress Note (64), default, apply to All.
- **T** = SOAP (1362), Select providers → Jorge.
- **U** = Daily Note (79), Select providers → Deepti Test1. Jorge doesn't have Daily Note.

**Steps**
1. Click rule **T**. The side panel lists Jorge.
2. Click **Move** next to Jorge.
3. Open the rule picker.

| | Rule picker | After picking **U** → Move |
|---|---|---|
| Actual (#6407) | Lists D and U | No missing-template choice. `PATCH …/appointment_rules/79/providers` body is `{"provider_ids":[472297]}`, with no `providers_without_template`. Jorge is on U, and the missing-rules banner shows **1 provider** |
| Actual (#6406) | Lists D only: U is hidden because Jorge lacks Daily Note | Can't be done |
| Expected | Lists D and U | On Move: `GET …/providers/472297/templates` is sent and Daily Note isn't in it, so the dialog shows "Add to their account / Use their personal default". The PATCH body has `providers_without_template: [{"provider_id": 472297, "action": "ADD_TEMPLATE"}]`. Jorge is on U, his account has Daily Note, and the banner shows **0** |

4. Control case: move Jorge to **D** (Progress Note, which he has). Expected: no choice, and no `providers_without_template` in the PATCH.

AS-IS (#6407)
```dart
/// All template options except the currently active one.
List<AppointmentRuleTemplateOption> get _ruleOptions => widget.templateOptions
    .where((t) => t.id != widget.currentTemplateId)
    .toList();

Future<void> _onMove() async {
  if (_selectedRuleId == null || _isSaving) return;
  setState(() => _isSaving = true);
  try {
    await widget.onConfirm(
      targetTemplateId: _selectedRuleId!,
      providerIds: [widget.providerId],
    );
    if (mounted) Navigator.of(context).pop();
  } finally {
    if (mounted) setState(() => _isSaving = false);
  }
}
```

AS-IS (#6406, plus the same `_onMove`)
```dart
List<AppointmentRuleTemplateOption> get _ruleOptions {
  final owned = _providerTemplateIds; // loaded once in initState
  if (owned == null) return [];
  return widget.templateOptions
      .where((t) => t.id != widget.currentTemplateId && owned.contains(t.id))
      .toList();
}
```

TO-BE
```dart
class _MoveProviderDialog extends ConsumerStatefulWidget { ... }

/// Null until Move is tapped; then whether the provider lacks the target.
bool? _targetMissing;
bool _checking = false;
_MissingProviderAction _missingAction = _MissingProviderAction.addToAccount;

List<AppointmentRuleTemplateOption> get _ruleOptions => widget.templateOptions
    .where((t) => t.id != widget.currentTemplateId)
    .toList();

Future<void> _onMove() async {
  if (_selectedRuleId == null || _isSaving || _checking) return;
  final target = _selectedRuleId!;

  // First tap: check the provider's templates at confirm time (spec §3).
  if (_targetMissing == null) {
    setState(() => _checking = true);
    try {
      final pt = await ref
          .read(appointmentRulesV2RepositoryProvider)
          .providerTemplates(providerId: widget.providerId);
      if (!mounted || target != _selectedRuleId) return; // target changed
      final missing = !pt.templates.any((t) => t.templateId == target);
      setState(() => _targetMissing = missing);
      if (missing) return; // show the choice; the admin taps Move again
    } on Object catch (e, stackTrace) {
      logger.e('providerTemplates failed', error: e, stackTrace: stackTrace);
      unawaited(EclipseToast.error(title: 'Could not check provider templates'));
      return; // don't move
    } finally {
      if (mounted) setState(() => _checking = false);
    }
  }

  setState(() => _isSaving = true);
  try {
    await widget.onConfirm(
      targetTemplateId: target,
      providerIds: [widget.providerId],
      providersWithoutTemplate: _targetMissing == true
          ? [
              ProviderWithoutTemplateEntry(
                providerId: widget.providerId,
                action: _missingAction == _MissingProviderAction.addToAccount
                    ? ProviderWithoutTemplateAction.addTemplate
                    : ProviderWithoutTemplateAction.personalRules,
              ),
            ]
          : const [],
    );
    if (mounted) Navigator.of(context).pop();
  } finally {
    if (mounted) setState(() => _isSaving = false);
  }
}

// Rule picker: reset the check when the target changes
onChanged: (id) => setState(() {
  _selectedRuleId = id;
  _targetMissing = null;
}),

// build: when _targetMissing == true, show the same two chips as Add / Change
// ("Add to their account" / "Use their personal default").
// Disable Move while _checking or _isSaving.
```

**After the fix:** re-run steps 1–4; Expected applies. Also block `…/providers/*/templates` in DevTools (Network → Block request URL) and tap Move: an error toast appears and no PATCH is sent.
