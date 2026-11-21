# AFEP-3031: send one test event to Mixpanel `/import`

Manual test of Mixpanel's `/import` API against the **Ambient** project (project ID `3781252`, organization Athelas).

**Status (2026-11-21):** step 2 was run and returned HTTP 200 with `num_records_imported: 1`. The event `AFEP3031_TEST` showed up in the project's Events view. The dedupe test (step 4) has not been run yet.

**Warning:** Ambient looks like a live project. A test event stays in it and can't easily be removed. The event name `AFEP3031_TEST` and `distinct_id` `afep-3031-test` are easy to filter out of reports.

**Secrets:** never paste the API secret into docs, PRs or chat. The steps below read it into an env variable.

## 1. Set the secret (no echo, not saved to shell history)

```bash
read -rs MP_SECRET   # paste the API Secret, press Enter. Nothing is shown.
export MP_SECRET
```

## 2. Send one event

```bash
curl -sS -w '\nHTTP %{http_code}\n' -X POST \
  'https://api.mixpanel.com/import?strict=1&project_id=3781252' \
  -u "$MP_SECRET:" \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  -d "[{
    \"event\": \"AFEP3031_TEST\",
    \"properties\": {
      \"time\": $(date +%s),
      \"distinct_id\": \"afep-3031-test\",
      \"\$insert_id\": \"afep3031-test-0001\",
      \"source\": \"manual-import-test\"
    }
  }]"
```

- **Auth:** the project secret is the basic-auth username, and the password is blank, so the `-u` value ends in `:`.
- **`strict=1`:** Mixpanel validates the whole request and rejects it with a reason instead of silently dropping bad events.
- **Expected success:** HTTP 200 with `{"code":200,"status":"OK","num_records_imported":1,"error":null}`.

## 3. Check the event in Mixpanel

It appears within a minute or two. In the Ambient project, open **Events** (or Live View) and look for `AFEP3031_TEST`, or search for the user `afep-3031-test`.

## 4. Test the dedupe

Mixpanel's docs say dedupe uses the event name, `distinct_id`, `time` and `$insert_id` together. For a fair test, send the same event twice with an identical `time`. Replace `$(date +%s)` with a fixed number, for example `1763700000`, in both sends. Then count `AFEP3031_TEST` over a time range that covers that `time`. It should be **1**.

With a different `time` on the second send, Mixpanel may count it as a new event.

## If it fails

| Response | Likely cause |
|---|---|
| 401 | Wrong secret, or extra spaces or a trailing newline when it was pasted. |
| 400 mentioning `project_id` or the region | The project may be in the EU or India region. Use `api-eu.mixpanel.com` or `api-in.mixpanel.com`. |
| 400 `time` out of range | Mixpanel limits how old or far in the future `time` can be. Use the current time. |

## Clean up

```bash
unset MP_SECRET
```

## What this does not cover

- **Normandy:** it doesn't test the `funnel_events` endpoint (AFEP-3061), which doesn't exist yet.
- **Mapping:** it doesn't exercise the real event mapping (`{tag}.{action}`, `distinct_id` = recording UUID, `time` = phone timestamp, `$insert_id` = `event_id`).
- **Credentials:** the project API secret works for this call, but a service account scoped to one project is the better long-term credential. Only an organization owner or admin can create one.
