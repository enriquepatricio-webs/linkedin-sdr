"""Recorrido completo del SDR con Supabase y LinkedIn simulados.

    pip install -r requirements.txt pytest httpx && pytest tests
"""

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

from _sdr import jobs as jobs_mod  # noqa: E402
from _sdr import li  # noqa: E402
from _sdr.jobs import SDR  # noqa: E402


def _parse_list(raw):
    return [x.strip('"') for x in raw[raw.index("(") + 1 : -1].split(",")]


def _cmp(row, col, expr):
    op, _, val = expr.partition(".")
    cur = row.get(col)
    if op == "eq":
        return str(cur).lower() == val.lower() if isinstance(cur, bool) else str(cur) == val
    if op == "in":
        return str(cur) in _parse_list(expr[3:])
    if op == "is":
        return cur is None
    if cur is None:
        return False
    if op in ("lt", "lte", "gt", "gte"):
        a, b = datetime.fromisoformat(str(cur)), datetime.fromisoformat(val)
        return {"lt": a < b, "lte": a <= b, "gt": a > b, "gte": a >= b}[op]
    raise ValueError(expr)


def _match(row, filters):
    for col, expr in filters.items():
        if col in ("select", "order", "limit"):
            continue
        if col == "or":
            parts = expr[1:-1].split(",")
            if not any(_cmp(row, p.split(".", 1)[0], p.split(".", 1)[1]) for p in parts):
                return False
        elif not _cmp(row, col, expr):
            return False
    return True


DEFAULTS = {
    "sdr_leads": dict(status="new", followups_sent=0, profile=None, locked_until=None, next_action_at=None,
                      last_checked_at=None, inbox_synced_at=None, campaign_id=None, public_id=None, company="",
                      connection_note="", ai_summary="", invited_at=None, conversation_urn_id=None),
    "sdr_messages": dict(linkedin_event_urn=None, status="draft", ai_generated=False, sent_at=None),
}


class FakeDB:
    def __init__(self):
        self.t = {k: [] for k in ("sdr_settings", "sdr_campaigns", "sdr_leads", "sdr_messages", "sdr_events")}

    def select(self, table, filters=None, order=None, limit=None, columns="*"):
        rows = [dict(r) for r in self.t[table] if _match(r, filters or {})]
        if order:
            col = order.split(".")[0]
            rows.sort(key=lambda r: (r.get(col) is not None, str(r.get(col) or "")))
        return rows[:limit] if limit else rows

    def one(self, table, filters, columns="*"):
        rows = self.select(table, filters, limit=1)
        return rows[0] if rows else None

    def count(self, table, filters=None):
        return len(self.select(table, filters))

    def insert(self, table, rows, on_conflict=None, ignore_duplicates=False):
        rows = rows if isinstance(rows, list) else [rows]
        out = []
        for r in rows:
            if on_conflict and r.get(on_conflict) and any(x.get(on_conflict) == r[on_conflict] for x in self.t[table]):
                continue
            row = {**DEFAULTS.get(table, {}), "id": str(uuid.uuid4()),
                   "created_at": datetime.now(timezone.utc).isoformat(), **r}
            self.t[table].append(row)
            out.append(dict(row))
        return out

    def update(self, table, filters, values):
        out = []
        for r in self.t[table]:
            if _match(r, filters):
                r.update(values)
                out.append(dict(r))
        return out


ME = "ACoAAME"


class FakeLinkedIn:
    def __init__(self):
        self.invites, self.sent = [], []
        self.accepted = set()
        self.inbox = {}

    def install(self, monkeypatch):
        monkeypatch.setattr(li, "search_people", lambda api, c, limit, offset: [
            {"urn_id": f"ACoAA{i}", "public_id": f"persona-{i}", "full_name": f"Persona {i}", "first_name": "Persona",
             "headline": "CEO en Empresa", "location": "Madrid", "summary": "", "distance": "DISTANCE_2",
             "profile_url": f"https://www.linkedin.com/in/persona-{i}"} for i in range(offset, offset + 3)])
        monkeypatch.setattr(li, "get_profile", lambda api, pid, urn: {
            "public_id": pid, "headline": "CEO", "experience": [{"title": "CEO", "company": "Empresa", "period": "2020-actualidad"}]})
        monkeypatch.setattr(li, "invite", lambda api, urn, note: (self.invites.append((urn, note)) or True, "ok"))
        monkeypatch.setattr(li, "network_distance", lambda api, pid: "DISTANCE_1" if pid in self.accepted else "DISTANCE_2")
        monkeypatch.setattr(li, "send_message", lambda api, urn, text, conv=None: self.sent.append((urn, text)))
        monkeypatch.setattr(li, "me", lambda api: {"urn_id": ME, "name": "Enrique"})
        monkeypatch.setattr(li, "conversations", lambda api: [
            {"id": f"2-{urn}", "last_activity_ms": max(e["created_ms"] for e in evs), "participants": [ME, urn]}
            for urn, evs in self.inbox.items()])
        monkeypatch.setattr(li, "conversation_events", lambda api, cid: self.inbox[cid[2:]])


@pytest.fixture
def env(monkeypatch):
    db = FakeDB()
    db.insert("sdr_settings", {"id": 1, "engine_enabled": True, "autopilot": False, "auto_reply": False,
                               "company_name": "The Coto Company", "company_website": "https://thecotocompany.com",
                               "company_pitch": "Captación de clientes", "sender_name": "Enrique", "min_score": 60,
                               "daily_invite_limit": 2, "weekly_invite_limit": 10, "daily_message_limit": 10,
                               "working_days": [1, 2, 3, 4, 5, 6, 7], "work_start_hour": 0, "work_end_hour": 24,
                               "timezone": "Europe/Madrid", "li_session_status": "ok", "li_profile": {"urn_id": ME},
                               "language": "es", "tone": "cercano", "cta": "llamada"})
    db.insert("sdr_campaigns", {"name": "CEOs Madrid", "status": "active", "search_batch": 3, "search_offset": 0,
                                "pipeline_buffer": 40, "send_connection_note": True, "first_message_delay_hours": 0,
                                "followup_delays_days": [3, 5]})
    fake = FakeLinkedIn()
    fake.install(monkeypatch)
    monkeypatch.setattr(jobs_mod.random, "random", lambda: 0.99)
    return db, fake


def sdr(db):
    return SDR(db=db, client_factory=lambda s: object())


def test_full_sequence(env):
    db, fake = env

    r = sdr(db).prospect()
    assert r["campaigns"][0]["new"] == 3
    assert sdr(db).prospect()["campaigns"][0]["new"] == 3  # avanza el desplazamiento
    assert len(db.t["sdr_leads"]) == 6

    batch = sdr(db).next_to_qualify(limit=2)
    assert len(batch["items"]) == 2
    assert "{" not in batch["items"][0]["system_prompt"]
    assert len(sdr(db).next_to_qualify(limit=10)["items"]) == 4  # los bloqueados no se repiten

    a, b = batch["items"]
    assert sdr(db).save_qualification(a["lead_id"], {"score": 80, "qualified": True, "connection_note": "Hola Persona, " + "x" * 300})["status"] == "invite_review"
    assert sdr(db).save_qualification(b["lead_id"], {"score": 30, "qualified": True})["status"] == "disqualified"
    lead = db.one("sdr_leads", {"id": f"eq.{a['lead_id']}"})
    assert len(lead["connection_note"]) == li.NOTE_MAX

    # Sin aprobar no se invita.
    assert sdr(db).invite()["skipped"] == "no hay leads listos para invitar"
    db.update("sdr_leads", {"id": f"eq.{a['lead_id']}"}, {"status": "to_invite"})
    assert sdr(db).invite()["invited"] == "Persona 0"
    assert fake.invites[0][1].startswith("Hola Persona")

    # Aceptación -> primer mensaje.
    fake.accepted.add(lead["public_id"])
    assert sdr(db).check_connections()["checked"] == 0  # recién invitado: se revisa a las 6 h
    db.update("sdr_leads", {"id": f"eq.{a['lead_id']}"}, {"last_checked_at": "2020-01-01T00:00:00+00:00"})
    assert sdr(db).check_connections()["connected"] == ["Persona 0"]
    due = sdr(db).due_messages()
    assert [i["kind"] for i in due["items"]] == ["first_message"]
    d = sdr(db).save_draft(a["lead_id"], "first_message", "Gracias por conectar")
    assert d["status"] == "draft"
    assert sdr(db).send_outbox()["results"] == []  # borrador sin aprobar no sale
    db.update("sdr_messages", {"id": f"eq.{d['message_id']}"}, {"status": "approved"})
    assert sdr(db).send_outbox()["results"][0]["sent"]
    lead = db.one("sdr_leads", {"id": f"eq.{a['lead_id']}"})
    assert lead["status"] == "messaged" and lead["next_action_at"] > datetime.now(timezone.utc).isoformat()

    # Seguimiento vencido.
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    db.update("sdr_leads", {"id": f"eq.{a['lead_id']}"}, {"next_action_at": past})
    due = sdr(db).due_messages()
    assert due["items"][0]["kind"] == "followup"
    f = sdr(db).save_draft(a["lead_id"], "followup", "Te dejo un dato")

    # Responde: se cancela el seguimiento pendiente y se pide análisis a la IA.
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    fake.inbox[lead["urn_id"]] = [
        {"urn": "ev1", "created_ms": now_ms - 5000, "from": ME, "text": "Gracias por conectar"},
        {"urn": "ev2", "created_ms": now_ms, "from": lead["urn_id"], "text": "Me interesa, hablamos?"},
    ]
    inbox = sdr(db).sync_inbox()
    assert len(inbox["items"]) == 1
    assert db.one("sdr_messages", {"id": f"eq.{f['message_id']}"})["status"] == "cancelled"
    assert db.one("sdr_leads", {"id": f"eq.{a['lead_id']}"})["status"] == "replied"
    assert sdr(db).sync_inbox()["items"] == []  # no se duplica
    sent_msgs = db.select("sdr_messages", {"lead_id": f"eq.{a['lead_id']}", "direction": "eq.out", "status": "eq.sent"})
    assert len(sent_msgs) == 1 and sent_msgs[0]["linkedin_event_urn"] == "ev1"

    res = sdr(db).save_reply_analysis(a["lead_id"], {"message_id": inbox["items"][0]["message_id"], "intent": "meeting", "reply": "Genial, te va el jueves?"})
    assert db.one("sdr_leads", {"id": f"eq.{a['lead_id']}"})["status"] == "meeting"
    assert db.one("sdr_messages", {"id": f"eq.{res['draft_id']}"})["status"] == "draft"


def test_limits_and_guards(env):
    db, fake = env
    sdr(db).prospect()
    for lead in db.t["sdr_leads"]:
        lead.update(status="to_invite", connection_note="hola")
    assert sdr(db).invite().get("invited")
    assert sdr(db).invite().get("invited")
    assert sdr(db).invite()["skipped"] == "límite diario de invitaciones alcanzado"

    db.update("sdr_settings", {"id": "eq.1"}, {"engine_enabled": False})
    assert sdr(db).prospect()["skipped"] == "motor apagado"
    assert sdr(db).send_outbox()["skipped"] == "motor apagado"


def test_session_error_marks_settings(env, monkeypatch):
    db, _ = env

    def boom(*a, **k):
        raise li.SessionError("caducada")

    monkeypatch.setattr(li, "search_people", boom)
    assert sdr(db).prospect()["ok"] is False
    assert db.one("sdr_settings", {"id": "eq.1"})["li_session_status"] == "invalid"
    assert sdr(db).invite()["skipped"].startswith("sesión de LinkedIn inválida")


def test_search_parsing(monkeypatch):
    class Api:
        def search(self, params, limit, offset):
            assert "(key:title,value:List(CEO  COO))" in params["filters"]
            return [
                {"entityUrn": "urn:li:fsd_entityResultViewModel:(urn:li:fsd_profile:ACoAAX,SEARCH_SRP,DEFAULT)",
                 "navigationUrl": "https://www.linkedin.com/in/ana-lopez?miniProfileUrn=x",
                 "title": {"text": "Ana López"}, "primarySubtitle": {"text": "CEO"},
                 "entityCustomTrackingInfo": {"memberDistance": "DISTANCE_2"}},
                {"entityUrn": "urn:li:fsd_entityResultViewModel:(urn:li:fsd_profile:ACoAAY,SEARCH_SRP,DEFAULT)",
                 "entityCustomTrackingInfo": {"memberDistance": "OUT_OF_NETWORK"}},
            ]

    people = li.search_people(Api(), {"search_title": "CEO, COO", "network_depths": ["S"]}, 10)
    assert people == [{
        "urn_id": "ACoAAX", "public_id": "ana-lopez", "full_name": "Ana López", "first_name": "Ana",
        "headline": "CEO", "location": "", "summary": "", "distance": "DISTANCE_2",
        "profile_url": "https://www.linkedin.com/in/ana-lopez"}]


def test_api_auth(monkeypatch):
    monkeypatch.setenv("SDR_API_KEY", "secreto")
    from fastapi.testclient import TestClient
    import index

    client = TestClient(index.app)
    assert client.get("/api/py/health").json() == {"ok": True}
    assert client.post("/api/py/jobs/invite").status_code == 401
    assert client.post("/api/py/jobs/invite", headers={"x-api-key": "otro"}).status_code == 401


def test_api_accepts_llm_nulls(monkeypatch):
    monkeypatch.setenv("SDR_API_KEY", "secreto")
    from fastapi.testclient import TestClient
    import index

    calls = {}

    class Stub:
        def save_qualification(self, lead_id, data):
            calls["q"] = data
            return {"ok": True}

        def save_reply_analysis(self, lead_id, data):
            calls["r"] = data
            return {"ok": True}

    monkeypatch.setattr(index, "SDR", Stub)
    client = TestClient(index.app)
    h = {"x-api-key": "secreto"}
    r = client.post("/api/py/jobs/qualification", headers=h, json={"lead_id": "x", "score": "75", "qualified": "true", "company": None, "extra": 1})
    assert r.status_code == 200 and calls["q"]["qualified"] is True
    r = client.post("/api/py/jobs/reply-analysis", headers=h, json={"lead_id": "x", "intent": "meeting", "reply": None})
    assert r.status_code == 200


def test_api_key_in_query(monkeypatch):
    monkeypatch.setenv("SDR_API_KEY", "secreto")
    from fastapi.testclient import TestClient
    import index

    monkeypatch.setattr(index, "SDR", lambda: type("S", (), {"invite": lambda self, **k: {"ok": True}})())
    client = TestClient(index.app)
    assert client.post("/api/py/jobs/invite?x-api-key=secreto").json() == {"ok": True}
    assert client.post("/api/py/jobs/invite?x-api-key=otro").status_code == 401
