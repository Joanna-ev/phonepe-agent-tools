"""FastAPI tool server for a Vapi voice agent."""

from __future__ import annotations

import json
import logging
from typing import Any, Iterator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

import tools

logger = logging.getLogger("vapi_tools")
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

app = FastAPI(title="PhonePe agent tools")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


def parse_arguments(raw: Any) -> dict:
    """Vapi sends arguments either as an object or as a JSON-encoded string."""
    if raw in (None, ""):
        return {}
    if isinstance(raw, str):
        raw = json.loads(raw)  # JSONDecodeError is a ValueError
    if not isinstance(raw, dict):
        raise ValueError("arguments must be a JSON object")
    return raw


def extract_tool_calls(message: dict) -> Iterator[tuple[Any, Any, Any]]:
    """Yield (id, name, raw_arguments) from toolCallList, else toolWithToolCallList."""
    calls = message.get("toolCallList")
    if calls:
        for call in calls:
            fn = call.get("function") or {}
            yield call.get("id"), fn.get("name") or call.get("name"), fn.get("arguments", call.get("arguments"))
        return
    for item in message.get("toolWithToolCallList") or []:
        call = item.get("toolCall") or {}
        fn = call.get("function") or {}
        name = fn.get("name") or item.get("name") or (item.get("function") or {}).get("name")
        yield call.get("id"), name, fn.get("arguments", call.get("arguments"))


@app.post("/vapi/tools")
async def vapi_tools(request: Request):
    raw_body = await request.body()
    logger.info("Raw request body: %s", raw_body.decode("utf-8", errors="replace"))

    try:
        body = json.loads(raw_body)
    except ValueError:
        return JSONResponse(status_code=400, content={"error": "Request body must be JSON."})
    message = body.get("message") if isinstance(body, dict) else None
    if not isinstance(message, dict):
        return JSONResponse(status_code=400, content={"error": "Missing 'message' object."})

    results = []
    for call_id, name, raw_args in extract_tool_calls(message):
        try:
            output = tools.call_tool(name, parse_arguments(raw_args))
        except ValueError:
            output = {"error": "Tool arguments were not valid JSON."}
        logger.info("Tool %s -> %s", name, output)
        results.append({
            "toolCallId": call_id,
            "result": json.dumps(output, ensure_ascii=False, separators=(",", ":")),
        })
    return {"results": results}
