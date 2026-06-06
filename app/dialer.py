"""Outbound calling + campaign runner.

place_call() wraps the Twilio REST client (which is synchronous, so callers
should run it via asyncio.to_thread). run_campaign() dials a campaign's numbers
one at a time, waiting for each call to finish before the next.
"""
from __future__ import annotations

import asyncio

from twilio.rest import Client

from . import config, db

_client: Client | None = None

TERMINAL = {"completed", "failed", "busy", "no-answer", "canceled"}


def client() -> Client:
    global _client
    if _client is None:
        _client = Client(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)
    return _client


def normalize(num: str) -> str:
    """Best-effort E.164. Bare 10-digit numbers are treated as Indian (+91)."""
    n = num.strip().replace(" ", "").replace("-", "")
    if n.startswith("+"):
        return n
    if len(n) == 10:
        return "+91" + n
    if n.startswith("91") and len(n) == 12:
        return "+" + n
    return "+" + n


def place_call(to: str, campaign_id: int | None = None):
    """Place an outbound call (blocking Twilio REST). Records it in the DB."""
    to = normalize(to)
    call = client().calls.create(
        to=to,
        from_=config.TWILIO_FROM_NUMBER,
        url=f"{config.PUBLIC_BASE_URL}/voice",
        method="POST",
        status_callback=f"{config.PUBLIC_BASE_URL}/status",
        status_callback_method="POST",
        status_callback_event=["initiated", "ringing", "answered", "completed"],
    )
    db.record_call(call.sid, to, config.TWILIO_FROM_NUMBER, "outbound",
                   call.status, campaign_id)
    return call


async def place_call_async(to: str, campaign_id: int | None = None):
    return await asyncio.to_thread(place_call, to, campaign_id)


async def _wait_for_end(sid: str, timeout: float = 150.0) -> str:
    """Poll the DB (updated by the /status webhook) until the call ends."""
    waited = 0.0
    while waited < timeout:
        call = db.get_call(sid)
        if call and call["status"] in TERMINAL:
            return call["status"]
        await asyncio.sleep(3.0)
        waited += 3.0
    return "timeout"


async def run_campaign(campaign_id: int) -> None:
    """Dial each number sequentially; advance when the prior call ends."""
    db.set_campaign_status(campaign_id, "running")
    try:
        for n in db.get_campaign_numbers(campaign_id):
            if n["status"] in ("done", "failed"):
                continue
            db.set_number_status(n["id"], "calling")
            try:
                call = await place_call_async(n["number"], campaign_id)
                db.set_number_status(n["id"], "calling", call.sid)
                status = await _wait_for_end(call.sid)
                db.set_number_status(
                    n["id"], "done" if status == "completed" else "failed", call.sid)
            except Exception as e:
                print(f"[campaign {campaign_id}] {n['number']} failed: {e!r}", flush=True)
                db.set_number_status(n["id"], "failed")
            await asyncio.sleep(2.0)   # small gap between calls
    finally:
        db.set_campaign_status(campaign_id, "completed")
