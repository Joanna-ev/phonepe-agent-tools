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
| `get_merchant_profile` | `phone` (any format: `+91 90000 00001`, `09000000001`, …) | merchant id, plan, fee, tenure, language |
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

Errors are returned as `{"error": "..."}` inside the result string so the agent can read them out. HTTP status stays 200.

### Cancellations

Call `process_cancellation` with `confirm: false` first. The agent reads the fee and pickup details to the merchant and gets
their agreement before calling again with `confirm: true`. A missing `confirm` is an error, never a cancellation.
Confirmed cancellations are appended to `data/cancellations.json` (override with `CANCELLATIONS_PATH`), with the same
Render persistence caveat as tickets below. Confirming again for the same merchant returns the existing record instead of
creating a duplicate.

### Callback tickets

`schedule_callback` appends tickets to `data/tickets.json`. The file is created on first use and git-ignored.
Set `TICKETS_PATH` to store them elsewhere. Ticket IDs continue from the highest existing `CB-` number, starting at `CB-1001`.
Note that Render's filesystem is ephemeral, so tickets are lost on every redeploy or restart unless you attach a persistent disk
and point `TICKETS_PATH` at it. Writes are serialised with an in-process lock, so run a single worker.

## Sample request

```bash
curl -s -X POST http://localhost:8000/vapi/tools -H "Content-Type: application/json" -d '{
  "message": {"type": "tool-calls", "toolCallList": [
    {"id": "call_1", "type": "function",
     "function": {"name": "get_merchant_profile", "arguments": {"phone": "+91 90000 00001"}}}
  ]}}'
```

## Deploy to Render

Push this repo to GitHub, then on Render choose **New → Blueprint** and select the repo. `render.yaml` sets the build/start
commands and the `/health` check. Use `https://<your-service>.onrender.com/vapi/tools` as the tool Server URL in Vapi.
