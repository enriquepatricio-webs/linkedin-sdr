"""API del SDR (Vercel Python). Todas las rutas cuelgan de /api/py.

n8n y el panel la llaman con la cabecera x-api-key = SDR_API_KEY.
"""

import hmac
import os
import sys
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(__file__))

from fastapi import Depends, FastAPI, Header, HTTPException, Query  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from _sdr.db import DBError  # noqa: E402
from _sdr.jobs import SDR, JobError  # noqa: E402
from _sdr.li import LinkedInError  # noqa: E402

app = FastAPI(title="LinkedIn SDR", docs_url="/api/py/docs", openapi_url="/api/py/openapi.json")


def auth(
    x_api_key: Optional[str] = Header(default=None),
    authorization: Optional[str] = Header(default=None),
    key_param: Optional[str] = Query(default=None, alias="x-api-key"),
):
    # Los mensajes distinguen el fallo sin revelar la clave (sólo longitudes, para detectar espacios).
    expected = os.environ.get("SDR_API_KEY", "").strip()
    # Cabecera x-api-key, Authorization: Bearer o ?x-api-key= (credencial Query Auth de n8n).
    given = (x_api_key or key_param or (authorization or "").removeprefix("Bearer ")).strip()
    if not expected:
        raise HTTPException(status_code=500, detail="SDR_API_KEY no está configurada en este despliegue de Vercel")
    if not given:
        raise HTTPException(status_code=401, detail="Falta la cabecera x-api-key")
    if not hmac.compare_digest(expected, given):
        raise HTTPException(
            status_code=401,
            detail=f"API key inválida (recibidos {len(given)} caracteres, se esperan {len(expected)})",
        )


@app.exception_handler(LinkedInError)
async def _li_error(_, exc: LinkedInError):
    return JSONResponse(status_code=502, content={"ok": False, "error": str(exc)})


@app.exception_handler(DBError)
async def _db_error(_, exc: DBError):
    return JSONResponse(status_code=500, content={"ok": False, "error": f"Supabase: {exc}"})


@app.exception_handler(JobError)
async def _job_error(_, exc: JobError):
    return JSONResponse(status_code=400, content={"ok": False, "error": str(exc)})


class Run(BaseModel):
    force: bool = False
    limit: int = 5
    campaign_id: Optional[str] = None
    lead_id: Optional[str] = None
    message_id: Optional[str] = None


class Qualification(BaseModel):
    lead_id: str
    score: Any = 0
    qualified: Any = False
    reason: Optional[str] = ""
    summary: Optional[str] = ""
    company: Optional[str] = ""
    connection_note: Optional[str] = ""


class Draft(BaseModel):
    lead_id: str
    kind: Optional[str] = "followup"
    message: str


class ReplyAnalysis(BaseModel):
    lead_id: str
    message_id: Optional[str] = None
    intent: Optional[str] = "neutral"
    reason: Optional[str] = ""
    reply: Optional[str] = ""


class SearchPreview(BaseModel):
    search_keywords: str = ""
    search_title: str = ""
    search_company: str = ""
    search_regions: List[str] = []
    search_industries: List[str] = []
    network_depths: List[str] = ["S", "O"]


def _truthy(v: Any) -> bool:
    return v is True or str(v).strip().lower() in ("true", "1", "yes", "si", "sí")


@app.get("/api/py/health")
def health():
    return {"ok": True}


@app.get("/api/py/status", dependencies=[Depends(auth)])
def status():
    sdr = SDR()
    s = sdr.settings
    return {
        "ok": True,
        "session": {"status": s.get("li_session_status"), "checked_at": s.get("li_session_checked_at"), "profile": s.get("li_profile")},
        "usage": sdr.usage(),
    }


@app.get("/api/py/linkedin/check", dependencies=[Depends(auth)])
@app.post("/api/py/linkedin/check", dependencies=[Depends(auth)])
def linkedin_check():
    return SDR().check_session()


@app.post("/api/py/linkedin/search-preview", dependencies=[Depends(auth)])
def search_preview(body: SearchPreview):
    return SDR().search_preview(body.model_dump())


def _csv(value: str) -> List[str]:
    return [x.strip() for x in (value or "").split(",") if x.strip()]


@app.get("/api/py/research/search", dependencies=[Depends(auth)])
def research_search(
    keywords: str = "", title: str = "", company: str = "", regions: str = "", industries: str = "",
    depths: str = "S,O", sample: int = 5,
):
    segment = {
        "search_keywords": keywords, "search_title": title, "search_company": company,
        "search_regions": _csv(regions), "search_industries": _csv(industries), "network_depths": _csv(depths),
    }
    return SDR().research(segment, sample=max(0, min(sample, 25)))


@app.get("/api/py/research/profile", dependencies=[Depends(auth)])
def research_profile(public_id: str):
    return SDR().research_profile(public_id)


@app.post("/api/py/jobs/prospect", dependencies=[Depends(auth)])
def prospect(body: Run = Run()):
    return SDR().prospect(force=body.force, campaign_id=body.campaign_id)


@app.post("/api/py/jobs/qualify-batch", dependencies=[Depends(auth)])
def qualify_batch(body: Run = Run()):
    return SDR().next_to_qualify(limit=min(body.limit, 10), force=body.force)


@app.post("/api/py/jobs/qualification", dependencies=[Depends(auth)])
def qualification(body: Qualification):
    data = body.model_dump()
    data["qualified"] = _truthy(body.qualified)
    return SDR().save_qualification(body.lead_id, data)


@app.post("/api/py/jobs/invite", dependencies=[Depends(auth)])
def invite(body: Run = Run()):
    return SDR().invite(force=body.force, lead_id=body.lead_id)


@app.post("/api/py/jobs/check-connections", dependencies=[Depends(auth)])
def check_connections(body: Run = Run()):
    return SDR().check_connections(limit=min(body.limit, 25), force=body.force)


@app.post("/api/py/jobs/due-messages", dependencies=[Depends(auth)])
def due_messages(body: Run = Run()):
    return SDR().due_messages(limit=min(body.limit, 10), force=body.force)


@app.post("/api/py/jobs/draft", dependencies=[Depends(auth)])
def draft(body: Draft):
    kind = body.kind if body.kind in ("first_message", "followup", "reply", "manual") else "followup"
    return SDR().save_draft(body.lead_id, kind, body.message)


@app.post("/api/py/jobs/send-outbox", dependencies=[Depends(auth)])
def send_outbox(body: Run = Run()):
    return SDR().send_outbox(force=body.force, message_id=body.message_id)


@app.post("/api/py/jobs/sync-inbox", dependencies=[Depends(auth)])
def sync_inbox(body: Run = Run()):
    return SDR().sync_inbox(force=body.force)


@app.post("/api/py/jobs/reply-analysis", dependencies=[Depends(auth)])
def reply_analysis(body: ReplyAnalysis):
    return SDR().save_reply_analysis(body.lead_id, body.model_dump())
