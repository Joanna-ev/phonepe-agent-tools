# PhonePe agent tools

FastAPI tool server for a Vapi voice agent handling smart-speaker retention and cancellation.
Mock data lives in `data/merchants.json`; retention offers and cancellation fees in `data/rules.json`.

## Run locally

```bash
python -m venv .venv
source .venv/Scripts/activate      # Windows Git Bash; use .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

- `GET /health` → `{"status":"ok"}`
- `POST /vapi/tools` → Vapi tool-call webhook. Point every tool's Server URL here.

Every raw request body is logged to the console (`vapi_tools` logger) for debugging.
These bodies include caller phone numbers and transcripts, so be careful who can see your Render logs.

## Tests

```bash
python -m pytest -q
```

## Tools

| Tool | Arguments | Returns |
|---|---|---|
| `get_merchant_profile` | `phone` (any format: `+91 98765 43210`, `09876543210`, …) | merchant id, plan, fee, tenure, `speaker_alert_language` (the speaker's announcement language, not the call's) |
| `run_device_diagnostics` | `merchant_id` | status, battery, signal, last alert, issues, suggested fix |
| `check_retention_options` | `merchant_id`, `reason_code` | offers for the reason (see below) |
| `apply_retention_action` | `merchant_id`, `action`, optional `language` | confirmation message |
| `process_cancellation` | `merchant_id`, `confirm` (bool), optional `reason_code` | `confirm: false` → quote only (fee, pickup date today + 3 days IST, items); `confirm: true` → records it, returns `CN-` id |
| `schedule_callback` | `merchant_id`, `time`, optional `reason`, `escalation` (bool), `summary` | ticket id, e.g. `CB-1042` |

Reason codes: `COST`, `NOT_USEFUL`, `SWITCHING_COMPETITOR` (all offer `switch_to_zero_rental` if on the monthly plan,
plus `cost_per_payment_paise`), `NOT_WORKING` (`remote_troubleshoot` then `free_replacement`),
`LANGUAGE_OR_VOLUME` (`change_language`), `CLOSING_OR_MOVING` (no offers, `recommendation: release`).

Cancellation fee: tenure under 6 months is ₹1 on the first request and ₹550 after that.
Tenure of 6–12 months is ₹1 on the first request and ₹400 after that. Tenure over 12 months is ₹0.

### Spoken fields

`spoken.py` adds speakable versions next to numeric fields in every successful result, chosen by field name:

| Field | Added | Example |
|---|---|---|
| `*_inr` | `<field>_spoken_en`, `<field>_spoken_hi` | `nine hundred ninety-nine rupees` / `nau sau ninyanve rupaye` |
| `cost_per_payment_paise` | `<field>_spoken_en`, `<field>_spoken_hi` | `about thirty paisay per payment` / `har payment par lagbhag tees paise` |
| `*_months` | `<field>_spoken_en`, `<field>_spoken_hi` | `ten months` / `das mahine` |
| `payments_*` | `<field>_spoken_en`, `<field>_spoken_hi` | `four hundred ten payments` / `chaar sau das payments` |
| `*_percent` | `<field>_spoken_en`, `<field>_spoken_hi` | `seventy-eight percent` / `athattar percent` |
| `*_date` | `<field>_spoken_en`, `<field>_spoken_hi` | `the sixteenth of November` / `solah November` |
| `*_id` (containing digits) | `<field>_spoken` (digits only, with a type word) | `callback ticket one, zero, four, two`, `cancellation reference …`, `merchant number …` |

English fields spell paise as `paisay` so English voices pronounce it correctly; Hindi fields keep `paise`.
| `plan` | `plan_name_spoken` | `zero rental plan` |

Hindi is romanised and uses the Indian scale (sau, hazaar, lakh, karod). Whole numbers up to 99,99,99,999 are supported.

### Ready-to-say sentences

`say.py` adds `say_en` and `say_hi` to the results of `run_device_diagnostics`, `apply_retention_action`,
`process_cancellation`, `schedule_callback`, and to each offer in `check_retention_options`.
They are built after the spoken fields, from the result itself, so they can only quote amounts, dates, times and
references that the result contains. `tests/test_say.py` checks this for every tool and merchant.

`apply_retention_action` records each action in `data/retention_actions.json` (override with `RETENTION_ACTIONS_PATH`)
and returns a `request_id` like `RA-1001`. Repeating the same action for the same merchant returns the same request.

`schedule_callback` understands times like `tomorrow 11 AM`, `Monday 3:30 pm`, `5 pm`, or ISO (`2026-11-20T15:00+05:30`),
and returns `callback_date` and `callback_clock` (IST). Times in the past are rejected. A bare hour with no a.m./p.m.
is read as 8–11 a.m. or 12–7 p.m. Text it can't parse ("as soon as possible") is kept as-is and read back verbatim.

Errors are returned as `{"error": "..."}` inside the result string so the agent can read them out. HTTP status stays 200.

### Cancellations

Call `process_cancellation` with `confirm: false` first. The agent reads the fee and pickup details to the merchant and gets
their agreement before calling again with `confirm: true`. A missing `confirm` is an error, never a cancellation.
Confirmed cancellations are appended to `data/cancellations.json` (override with `CANCELLATIONS_PATH`), with the same
Render persistence caveat as tickets below. Confirming again for the same merchant returns the existing record instead of
creating a duplicate.

### Callback tickets

`schedule_callback` appends tickets to `data/tickets.json`. The file is created on first use and git-ignored.
Set `TICKETS_PATH` to store them elsewhere.
`merchant_id: "UNKNOWN"` (any case) is accepted when the caller could not be identified; the ticket is saved with no
merchant name or phone, so put identifying details in `summary`. Other unrecognised IDs are still rejected. Ticket IDs continue from the highest existing `CB-` number, starting at `CB-1001`.
Note that Render's filesystem is ephemeral, so tickets are lost on every redeploy or restart unless you attach a persistent disk
and point `TICKETS_PATH` at it. Writes are serialised with an in-process lock, so run a single worker.

## Resetting between tests

The tools never modify `merchants.json` or `rules.json`, but they do write tickets, cancellations and retention actions,
which change later results (a repeated confirm returns the earlier `CN-` cancellation, ticket numbers keep rising).
`POST /admin/reset` deletes those three files so the next call starts from the original mock state.

It requires the `X-Admin-Token` header to equal the `ADMIN_TOKEN` environment variable, and is disabled (503) when
`ADMIN_TOKEN` is unset. On Render, `render.yaml` generates the value; find it under the service's **Environment** tab.

```powershell
Invoke-RestMethod -Method Post -Uri https://phonepe-agent-tools.onrender.com/admin/reset -Headers @{ "X-Admin-Token" = "YOUR_TOKEN" }
```

Locally, set the variable before starting the server: `$env:ADMIN_TOKEN = "dev-secret"; uvicorn main:app --port 8000`.

## Sample request

```bash
curl -s -X POST http://localhost:8000/vapi/tools -H "Content-Type: application/json" -d '{
  "message": {"type": "tool-calls", "toolCallList": [
    {"id": "call_1", "type": "function",
     "function": {"name": "get_merchant_profile", "arguments": {"phone": "+91 98765 43210"}}}
  ]}}'
```

## Deploy to Render

Push this repo to GitHub, then on Render choose **New → Blueprint** and select the repo. `render.yaml` sets the build/start
commands and the `/health` check. Use `https://<your-service>.onrender.com/vapi/tools` as the tool Server URL in Vapi.
