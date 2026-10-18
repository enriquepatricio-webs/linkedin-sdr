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
    "sdr_engagements": dict(status="new", lead_id=None, want_like=False, liked_at=None, comment="",
                            comment_status="none", locked_until=None, author_headline="", post_age=""),
}


class FakeDB:
    def __init__(self):
        self.t = {k: [] for k in ("sdr_settings", "sdr_campaigns", "sdr_leads", "sdr_messages", "sdr_events", "sdr_engagements")}

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
        self.likes, self.comments = [], []
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
        monkeypatch.setattr(li, "profile_posts", lambda api, urn, count=3: [
            {"post_urn": f"urn:li:activity:{urn}1", "post_url": "u", "author_name": "Lead", "author_headline": "CEO",
             "post_text": "Hemos abierto nueva sede", "post_age": "2d •"},
            {"post_urn": f"urn:li:activity:{urn}2", "post_url": "u", "author_name": "Lead", "author_headline": "CEO",
             "post_text": "Post antiguo", "post_age": "3mo •"}])
        monkeypatch.setattr(li, "feed_posts", lambda api, limit=20: [
            {"post_urn": "urn:li:activity:900", "post_url": "u", "author_name": "Otra", "author_headline": "",
             "post_text": "Cómo captar clientes", "post_age": "5h"},
            {"post_urn": "urn:li:activity:901", "post_url": "u", "author_name": "Enrique", "author_headline": "",
             "post_text": "Mi propio post", "post_age": "1d"}])
        monkeypatch.setattr(li, "like_post", lambda api, urn: self.likes.append(urn))
        monkeypatch.setattr(li, "comment_post", lambda api, urn, text: self.comments.append((urn, text)))


@pytest.fixture
def env(monkeypatch):
    db = FakeDB()
    db.insert("sdr_settings", {"id": 1, "engine_enabled": True, "autopilot": False, "auto_reply": False,
                               "company_name": "The Coto Company", "company_website": "https://thecotocompany.com",
                               "company_pitch": "Captación de clientes", "sender_name": "Enrique", "min_score": 60,
                               "daily_invite_limit": 2, "weekly_invite_limit": 10, "daily_message_limit": 10,
                               "working_days": [1, 2, 3, 4, 5, 6, 7], "work_start_hour": 0, "work_end_hour": 24,
                               "timezone": "Europe/Madrid", "li_session_status": "ok", "li_profile": {"urn_id": ME},
                               "li_proxy": "http://u:p@proxy.es:8000",
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
            assert "(key:title,value:List(CEO COO))" in params["filters"]
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


def test_search_total():
    class Res:
        status_code, url = 200, "https://www.linkedin.com/voyager/api/graphql"

        def json(self):
            return {"data": {"searchDashClustersByAll": {"metadata": {"totalResultCount": 1234}}}}

    class Api:
        def _fetch(self, uri):
            assert "key:geoUrn,value:List(105646813)" in uri and "keywords:catering eventos," in uri
            return Res()

    assert li.search_total(Api(), {"search_keywords": "catering, eventos", "search_regions": ["105646813"]}) == 1234


def test_engagement_flow(env):
    db, fake = env
    sdr(db).prospect()
    db.t["sdr_leads"][0].update(status="invited", score=90)
    db.t["sdr_settings"][0].update(li_profile={"urn_id": ME, "name": "Enrique"}, engagement_enabled=True,
                                   auto_comment=False, daily_like_limit=25, daily_comment_limit=8)

    batch = sdr(db).engage_batch(leads=4, feed=10, limit=10)
    urns = {r["post_urn"] for r in db.t["sdr_engagements"]}
    assert urns == {"urn:li:activity:ACoAA01", "urn:li:activity:900"}  # sin posts viejos ni propios
    assert len(batch["items"]) == 2 and "{" not in batch["items"][0]["system_prompt"]
    assert sdr(db).engage_batch(leads=4, feed=0)["items"] == []  # bloqueados mientras la IA decide

    lead_post = next(r for r in db.t["sdr_engagements"] if r["source"] == "lead")
    feed_post = next(r for r in db.t["sdr_engagements"] if r["source"] == "feed")
    assert sdr(db).save_engagement(lead_post["id"], {"relevant": True, "score": 80, "like": True,
                                                     "comment": "Enhorabuena por la nueva sede"})["comment_status"] == "draft"
    assert sdr(db).save_engagement(feed_post["id"], {"relevant": False, "like": True})["status"] == "skipped"

    r = sdr(db).engage_run()
    assert r["liked"] == 1 and r["commented"] == 0  # el comentario espera aprobación
    assert fake.likes == ["urn:li:activity:ACoAA01"]
    assert db.one("sdr_engagements", {"id": f"eq.{lead_post['id']}"})["status"] == "ready"

    db.update("sdr_engagements", {"id": f"eq.{lead_post['id']}"}, {"comment_status": "approved"})
    r = sdr(db).engage_run()
    assert r["commented"] == 1 and fake.comments == [("urn:li:activity:ACoAA01", "Enhorabuena por la nueva sede")]
    row = db.one("sdr_engagements", {"id": f"eq.{lead_post['id']}"})
    assert row["status"] == "done" and row["comment_status"] == "posted"
    assert fake.likes == ["urn:li:activity:ACoAA01"]  # no repite el me gusta

    db.update("sdr_settings", {"id": "eq.1"}, {"engagement_enabled": False})
    assert sdr(db).engage_run()["skipped"] == "interacción con publicaciones desactivada"


def test_age_and_profile_posts():
    assert li.age_days("3d •") == 3 and li.age_days("2w • Edited") == 14 and li.age_days("1mo") == 30
    assert li.age_days("5h") == 0 and li.age_days("") is None

    class Api:
        def get_profile_posts(self, urn_id, post_count):
            return [
                {"updateMetadata": {"urn": "urn:li:activity:111"}, "actor": {"name": {"text": "Ana"},
                 "description": {"text": "CEO"}, "subDescription": {"text": "2d •"}},
                 "commentary": {"text": {"text": "Abrimos sede"}}},
                {"updateMetadata": {"urn": "urn:li:activity:222"}, "resharedUpdate": {}},
            ]

    posts = li.profile_posts(Api(), "X")
    assert posts == [{"post_urn": "urn:li:activity:111", "post_url": "https://www.linkedin.com/feed/update/urn:li:activity:111/",
                      "author_name": "Ana", "author_headline": "CEO", "post_text": "Abrimos sede", "post_age": "2d •"}]


BROWSER = {"li_at": "AQEnuevo", "JSESSIONID": '"ajax:123"', "bcookie": '"v=2&abc"', "lidc": "b=x", "bad name": "x"}


def test_session_sync(env, monkeypatch):
    db, _ = env
    calls = []
    monkeypatch.setattr(li, "me", lambda api: calls.append(api) or {"urn_id": ME, "name": "Enrique"})

    r = sdr(db).sync_session(BROWSER, "Mozilla/5.0 Navegador", "es-ES,es")
    s = db.one("sdr_settings", {"id": "eq.1"})
    assert r["ok"] and r["changed"] and len(calls) == 1
    assert s["li_at"] == "AQEnuevo" and s["jsessionid"] == "ajax:123" and s["li_session_status"] == "ok"
    assert s["li_cookies"]["bcookie"] == '"v=2&abc"' and "bad name" not in s["li_cookies"]
    assert s["li_user_agent"] == "Mozilla/5.0 Navegador" and s["li_session_source"] == "extension"
    assert db.count("sdr_events", {"type": "eq.session_synced"}) == 1

    # Mismo navegador, sesión ya comprobada: no se vuelve a llamar a LinkedIn.
    r = sdr(db).sync_session(BROWSER, "Mozilla/5.0 Navegador")
    assert r == {"ok": True, "changed": False, "profile": s["li_profile"]} and len(calls) == 1

    # Otra cuenta: se rechaza y no se toca la sesión guardada.
    monkeypatch.setattr(li, "me", lambda api: {"urn_id": "OTRA", "name": "Otra"})
    with pytest.raises(jobs_mod.JobError):
        sdr(db).sync_session({**BROWSER, "li_at": "AQEotra"})
    assert db.one("sdr_settings", {"id": "eq.1"})["li_at"] == "AQEnuevo"

    # LinkedIn la rechaza: se guarda (es la más reciente) pero queda inválida.
    def boom(api):
        raise li.SessionError("401")

    monkeypatch.setattr(li, "me", boom)
    assert sdr(db).sync_session({**BROWSER, "li_at": "AQEcaducada"})["ok"] is False
    s = db.one("sdr_settings", {"id": "eq.1"})
    assert s["li_at"] == "AQEcaducada" and s["li_session_status"] == "invalid"

    with pytest.raises(jobs_mod.JobError):
        sdr(db).sync_session({"bcookie": "x"})


def test_make_client_uses_browser_cookies():
    api = li.make_client({"li_at": "AQE", "jsessionid": "ajax:1", "li_cookies": BROWSER, "li_proxy": "http://p.es:1",
                          "li_user_agent": "UA-navegador", "li_accept_language": "es-ES,es;q=0.9"})
    jar = api.client.session.cookies
    assert jar.get("bcookie") == '"v=2&abc"' and jar.get("lidc") == "b=x"
    assert jar.get("li_at", domain=".www.linkedin.com") == "AQE"
    h = api.client.session.headers
    assert h["csrf-token"] == "ajax:1" and h["user-agent"] == "UA-navegador" and h["x-li-lang"] == "es_ES"


def test_api_session_extension_token(monkeypatch):
    monkeypatch.setenv("SDR_API_KEY", "secreto")
    from fastapi.testclient import TestClient
    import index

    got = {}

    class Stub:
        settings = {"extension_token": "tok-ext"}

        def sync_session(self, cookies, ua, lang, source):
            got.update(cookies=cookies, ua=ua, source=source)
            return {"ok": True}

    monkeypatch.setattr(index, "SDR", Stub)
    client = TestClient(index.app)
    body = {"cookies": {"li_at": "a", "JSESSIONID": "b", "n": 1}, "user_agent": "UA", "source": "alarm"}
    assert client.post("/api/py/linkedin/session", json=body).status_code == 401
    assert client.post("/api/py/linkedin/session", json=body, headers={"x-extension-token": "otro"}).status_code == 401
    assert client.post("/api/py/linkedin/session", json=body, headers={"x-extension-token": "tok-ext"}).json() == {"ok": True}
    assert got == {"cookies": {"li_at": "a", "JSESSIONID": "b"}, "ua": "UA", "source": "alarm"}
    assert client.post("/api/py/linkedin/session", json=body, headers={"x-api-key": "secreto"}).status_code == 200


def test_extension_zip_is_up_to_date():
    import zipfile

    root = os.path.join(os.path.dirname(__file__), "..")
    with zipfile.ZipFile(os.path.join(root, "public", "coto-sdr-extension.zip")) as z:
        packed = {n.split("/", 1)[1]: z.read(n) for n in z.namelist() if not n.endswith("/")}
    files = {}
    for name in os.listdir(os.path.join(root, "extension")):
        with open(os.path.join(root, "extension", name), "rb") as f:
            files[name] = f.read()
    assert packed == files, "Ejecuta scripts/pack-extension.sh"


def test_server_keeps_rotated_cookies(env):
    import requests

    db, _ = env
    db.update("sdr_settings", {"id": "eq.1"}, {"li_at": "AQE", "jsessionid": "ajax:1", "li_cookies": {"bcookie": "b", "lidc": "viejo"}})
    s = SDR(db=db, client_factory=li.make_client)
    session = s.api.client.session

    def respond(**cookies):
        res = requests.Response()
        res.status_code = 200
        for k, v in cookies.items():
            res.cookies.set(k, v, domain=".linkedin.com")
        for hook in session.hooks["response"]:
            hook(res)

    respond(lidc="nuevo")
    row = db.one("sdr_settings", {"id": "eq.1"})
    assert row["li_cookies"]["lidc"] == "nuevo" and row["li_cookies"]["bcookie"] == "b" and row["li_cookies_refreshed_at"]

    respond(lidc="otro")  # cambio menor en la misma ronda: no se escribe otra vez
    assert db.one("sdr_settings", {"id": "eq.1"})["li_cookies"]["lidc"] == "nuevo"

    respond(JSESSIONID='"ajax:2"', li_at="AQEnuevo")  # cambios de sesión: se guardan siempre
    row = db.one("sdr_settings", {"id": "eq.1"})
    assert row["jsessionid"] == "ajax:2" and row["li_at"] == "AQEnuevo" and session.headers["csrf-token"] == "ajax:2"

    respond(li_at="delete me")
    assert db.one("sdr_settings", {"id": "eq.1"})["li_at"] == "AQEnuevo"

    res = requests.Response()
    res.status_code = 401
    res.cookies.set("JSESSIONID", '"ajax:anonimo"', domain=".linkedin.com")
    for hook in session.hooks["response"]:
        hook(res)
    assert db.one("sdr_settings", {"id": "eq.1"})["jsessionid"] == "ajax:2"


def test_no_linkedin_without_proxy(env, monkeypatch):
    db, fake = env
    db.update("sdr_settings", {"id": "eq.1"}, {"li_proxy": None})
    monkeypatch.delenv("LINKEDIN_PROXY", raising=False)
    monkeypatch.delenv("LINKEDIN_ALLOW_NO_PROXY", raising=False)
    calls = []
    monkeypatch.setattr(li, "me", lambda api: calls.append(1) or {"urn_id": ME})

    assert sdr(db).invite(force=True)["skipped"].startswith("falta el proxy")
    assert sdr(db).prospect(force=True)["skipped"].startswith("falta el proxy")
    r = sdr(db).check_session()
    assert r["proxy_required"] and not calls
    assert db.one("sdr_settings", {"id": "eq.1"})["li_session_status"] == "ok"  # no la da por caducada

    r = sdr(db).sync_session(BROWSER, "UA")
    row = db.one("sdr_settings", {"id": "eq.1"})
    assert r["proxy_required"] and not calls and row["li_at"] == "AQEnuevo" and row["li_session_status"] == "unknown"
    with pytest.raises(li.ProxyRequired):
        li.make_client({"li_at": "a", "jsessionid": "b"})

    monkeypatch.setenv("LINKEDIN_ALLOW_NO_PROXY", "1")
    assert li.make_client({"li_at": "a", "jsessionid": "b"})


def test_check_session_reports_proxy(env, monkeypatch):
    db, _ = env
    monkeypatch.setattr(li, "proxy_info", lambda p: {"ip": "1.2.3.4", "city": "Madrid", "country": "ES", "org": "Movistar"})
    r = sdr(db).check_session()
    assert r["ok"] and r["proxy"]["city"] == "Madrid"

    def down(p):
        raise li.LinkedInError("El proxy no responde")

    monkeypatch.setattr(li, "proxy_info", down)
    assert sdr(db).check_session()["error"] == "El proxy no responde"
    assert db.one("sdr_settings", {"id": "eq.1"})["li_session_status"] == "ok"


def test_proxy_formats():
    assert li.normalize_proxy("geo.iproyal.com:12321:user:pa:ss_country-es") == "http://user:pa:ss_country-es@geo.iproyal.com:12321"
    assert li.normalize_proxy("u:p@1.2.3.4:80") == "http://u:p@1.2.3.4:80"
    assert li.normalize_proxy("http://u:p@1.2.3.4:80") == "http://u:p@1.2.3.4:80"
    assert li.normalize_proxy("1.2.3.4:80") == "http://1.2.3.4:80"
    assert li.normalize_proxy("") == ""
    with pytest.raises(li.LinkedInError):
        li.normalize_proxy("basura")


def test_api_network_error_is_not_500(monkeypatch):
    monkeypatch.setenv("SDR_API_KEY", "secreto")
    from fastapi.testclient import TestClient
    import requests
    import index

    def boom():
        raise requests.exceptions.ProxyError("proxy caído")

    monkeypatch.setattr(index, "SDR", lambda: type("S", (), {"check_session": lambda self: boom()})())
    r = TestClient(index.app).post("/api/py/linkedin/check", headers={"x-api-key": "secreto"})
    assert r.status_code == 502 and "proxy" in r.json()["error"]
