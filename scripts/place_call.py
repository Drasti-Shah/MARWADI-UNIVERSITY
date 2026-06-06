"""Place an OUTBOUND test call via Twilio, pointing it at the /voice flow.

Twilio dials the target number; when answered it fetches PUBLIC_BASE_URL/voice
and runs the normal Gujarati admission-agent conversation.

Requires: server running + ngrok tunnel live at PUBLIC_BASE_URL, and the target
number verified on a Twilio trial account.

Usage:  python -m scripts.place_call +919724556935
"""
from __future__ import annotations

import sys

from twilio.rest import Client

from app import config


def normalize(num: str) -> str:
    """Best-effort E.164. Bare 10-digit Indian numbers get +91."""
    n = num.strip().replace(" ", "").replace("-", "")
    if n.startswith("+"):
        return n
    if len(n) == 10:
        return "+91" + n
    if n.startswith("91") and len(n) == 12:
        return "+" + n
    return n if n.startswith("+") else "+" + n


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python -m scripts.place_call <number>")
        return 2

    to = normalize(sys.argv[1])
    voice_url = f"{config.PUBLIC_BASE_URL}/voice"

    print(f"  from      : {config.TWILIO_FROM_NUMBER}")
    print(f"  to        : {to}")
    print(f"  voice_url : {voice_url}")
    print(f"  status_cb : {config.PUBLIC_BASE_URL}/status")

    client = Client(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)
    call = client.calls.create(
        to=to,
        from_=config.TWILIO_FROM_NUMBER,
        url=voice_url,
        method="POST",
        status_callback=f"{config.PUBLIC_BASE_URL}/status",
        status_callback_method="POST",
    )
    print(f"\n  CALL PLACED  sid={call.sid}  status={call.status}")
    print("  The phone should ring now. Answer to talk to the agent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
