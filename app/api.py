"""JSON REST API for the dashboard (dialer, campaigns, call logs)."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from . import auth, db, dialer
from typing import Optional

# Every /api/* route below requires a valid session. Login/logout live in
# main.py (unprotected), as do the public Twilio webhooks.
router = APIRouter(prefix="/api", dependencies=[Depends(auth.require_auth)])


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #
class CallRequest(BaseModel):
    number: str


class CampaignRequest(BaseModel):
    name: str
    numbers: list[str]


class LeadCreate(BaseModel):
    name: str = ""
    phone: str
    qualification: str = ""
    interest: str = ""
    status: str = "new"
    notes: str = ""


class LeadUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    qualification: Optional[str] = None
    interest: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None


# --------------------------------------------------------------------------- #
# Dialer
# --------------------------------------------------------------------------- #
@router.post("/call")
async def api_place_call(req: CallRequest):
    number = req.number.strip()
    if not number:
        raise HTTPException(400, "number is required")
    try:
        call = await dialer.place_call_async(number)
    except Exception as e:
        raise HTTPException(502, f"Twilio call failed: {e}")
    return {"sid": call.sid, "to": dialer.normalize(number), "status": call.status}


# --------------------------------------------------------------------------- #
# Call logs
# --------------------------------------------------------------------------- #
@router.get("/calls")
async def api_calls(limit: int = 200):
    return {"calls": db.get_calls(limit)}


@router.get("/calls/{sid}")
async def api_call_detail(sid: str):
    call = db.get_call(sid)
    if not call:
        raise HTTPException(404, "call not found")
    return call


@router.get("/stats")
async def api_stats():
    return db.stats()


# --------------------------------------------------------------------------- #
# Campaigns
# --------------------------------------------------------------------------- #
@router.post("/campaigns")
async def api_create_campaign(req: CampaignRequest):
    numbers = [n.strip() for n in req.numbers if n and n.strip()]
    if not req.name.strip():
        raise HTTPException(400, "name is required")
    if not numbers:
        raise HTTPException(400, "at least one number is required")
    cid = db.create_campaign(req.name.strip(), numbers)
    return {"id": cid}


@router.get("/campaigns")
async def api_campaigns():
    return {"campaigns": db.get_campaigns()}


@router.get("/campaigns/{cid}")
async def api_campaign_detail(cid: int):
    camp = db.get_campaign(cid)
    if not camp:
        raise HTTPException(404, "campaign not found")
    return camp


@router.post("/campaigns/{cid}/start")
async def api_start_campaign(cid: int):
    camp = db.get_campaign(cid)
    if not camp:
        raise HTTPException(404, "campaign not found")
    if camp["status"] == "running":
        raise HTTPException(409, "campaign already running")
    # Fire-and-forget background runner; progress is polled via the detail endpoint.
    asyncio.ensure_future(dialer.run_campaign(cid))
    return {"id": cid, "status": "running"}


# --------------------------------------------------------------------------- #
# Leads
# --------------------------------------------------------------------------- #
@router.get("/leads")
async def api_leads(status: str | None = None):
    return {"leads": db.get_leads(status), "statuses": db.LEAD_STATUSES,
            "counts": db.lead_status_counts()}


@router.post("/leads")
async def api_create_lead(req: LeadCreate):
    if not req.phone.strip():
        raise HTTPException(400, "phone is required")
    lid = db.create_lead(
        name=req.name.strip(), phone=req.phone.strip(),
        qualification=req.qualification.strip(), interest=req.interest.strip(),
        status=req.status or "new", source="manual", notes=req.notes.strip())
    return {"id": lid}


@router.patch("/leads/{lead_id}")
async def api_update_lead(lead_id: int, req: LeadUpdate):
    ok = db.update_lead(lead_id, req.model_dump(exclude_unset=True))
    if not ok:
        raise HTTPException(404, "lead not found or nothing to update")
    return {"ok": True}


@router.delete("/leads/{lead_id}")
async def api_delete_lead(lead_id: int):
    if not db.delete_lead(lead_id):
        raise HTTPException(404, "lead not found")
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Dashboard + analytics
# --------------------------------------------------------------------------- #
@router.get("/overview")
async def api_overview():
    return db.overview()


@router.get("/analytics")
async def api_analytics():
    return db.analytics()
