"""Lógica del SDR. n8n llama a estos trabajos por HTTP; la IA (DeepSeek) vive en n8n y
devuelve sus resultados con save_qualification / save_draft / save_reply_analysis."""

import random
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

from . import li, prompts
from .db import DB, now_iso

PIPELINE = ("new", "invite_review", "to_invite")
LOCK_MINUTES = 20


class JobError(Exception):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _in(values) -> str:
    return "in.(" + ",".join(f'"{v}"' for v in values) + ")"


def _unlocked() -> str:
    return f"(locked_until.is.null,locked_until.lt.{_iso(_now())})"


class SDR:
    def __init__(self, db: Optional[DB] = None, client_factory=li.make_client):
        self.db = db or DB()
        self._client_factory = client_factory
        self._api = None
        self._settings = None
        self._cookies_saved_at = None

    # ---------- utilidades ----------

    @property
    def settings(self) -> Dict:
        if self._settings is None:
            self._settings = self.db.one("sdr_settings", {"id": "eq.1"}) or {}
        return self._settings

    @property
    def api(self):
        if self._api is None:
            self._api = self._client_factory(self.settings)
            if hasattr(getattr(self._api, "client", None), "session"):
                li.watch_cookies(self._api, self.remember_cookies)
        return self._api

    def remember_cookies(self, fresh: Dict) -> None:
        """Guarda las cookies que LinkedIn renueva. La sesión vive en el servidor (como en WaLead):
        la extensión sólo hace falta para conectarla o reconectarla, no para que el SDR funcione."""
        s = self.settings
        stored = {**(s.get("li_cookies") or {}), "li_at": s.get("li_at"), "JSESSIONID": f'"{(s.get("jsessionid") or "").strip(chr(34))}"'}
        fresh = li.clean_cookies({k: v for k, v in fresh.items() if v != "delete me"})
        changed = {k: v for k, v in fresh.items() if stored.get(k) != v}
        if not changed:
            return
        critical = "li_at" in changed or "JSESSIONID" in changed
        now = _now()
        if not critical and self._cookies_saved_at and now - self._cookies_saved_at < timedelta(minutes=2):
            return
        cookies = {**(s.get("li_cookies") or {}), **fresh}
        values = {"li_cookies": cookies, "li_cookies_refreshed_at": _iso(now)}
        if fresh.get("li_at"):
            values["li_at"] = fresh["li_at"]
        if fresh.get("JSESSIONID"):
            values["jsessionid"] = fresh["JSESSIONID"].strip('"')
        self.db.update("sdr_settings", {"id": "eq.1"}, values)
        self._settings = {**s, **values}
        self._cookies_saved_at = now

    def log(self, type_: str, detail: str = "", lead_id=None, campaign_id=None, data=None):
        self.db.insert(
            "sdr_events",
            {"type": type_, "detail": detail[:1000], "lead_id": lead_id, "campaign_id": campaign_id, "data": data},
        )

    def mark_session(self, ok: bool, error: str = "", profile: Optional[Dict] = None):
        values = {"li_session_status": "ok" if ok else "invalid", "li_session_checked_at": now_iso()}
        if profile:
            values["li_profile"] = profile
        self.db.update("sdr_settings", {"id": "eq.1"}, values)
        if not ok:
            self.log("session_invalid", error)

    def tz(self) -> ZoneInfo:
        try:
            return ZoneInfo(self.settings.get("timezone") or "Europe/Madrid")
        except Exception:
            return ZoneInfo("Europe/Madrid")

    def local_now(self) -> datetime:
        return _now().astimezone(self.tz())

    def working_now(self) -> bool:
        local = self.local_now()
        days = self.settings.get("working_days") or [1, 2, 3, 4, 5]
        start = self.settings.get("work_start_hour", 9)
        end = self.settings.get("work_end_hour", 19)
        return local.isoweekday() in days and start <= local.hour < end

    def day_start(self) -> str:
        local = self.local_now().replace(hour=0, minute=0, second=0, microsecond=0)
        return _iso(local)

    def week_start(self) -> str:
        local = self.local_now().replace(hour=0, minute=0, second=0, microsecond=0)
        return _iso(local - timedelta(days=local.weekday()))

    def count_events(self, type_: str, since: str) -> int:
        return self.db.count("sdr_events", {"type": f"eq.{type_}", "created_at": f"gte.{since}"})

    def usage(self) -> Dict:
        s = self.settings
        return {
            "invites_today": self.count_events("invite_sent", self.day_start()),
            "invites_week": self.count_events("invite_sent", self.week_start()),
            "messages_today": self.count_events("message_sent", self.day_start()),
            "daily_invite_limit": s.get("daily_invite_limit"),
            "weekly_invite_limit": s.get("weekly_invite_limit"),
            "daily_message_limit": s.get("daily_message_limit"),
            "working_now": self.working_now(),
            "engine_enabled": s.get("engine_enabled"),
        }

    def _guard(self, force: bool, need_hours: bool = True) -> Optional[str]:
        if li.proxy_required(self.settings):
            return "falta el proxy en España (Ajustes)"  # ni siquiera a mano: quemaría la sesión
        if force:
            return None
        if not self.settings.get("engine_enabled"):
            return "motor apagado"
        if need_hours and not self.working_now():
            return "fuera de horario"
        if self.settings.get("li_session_status") == "invalid":
            return "sesión de LinkedIn inválida: actualiza las cookies en Ajustes"
        return None

    def campaign(self, campaign_id) -> Dict:
        if not campaign_id:
            return {}
        return self.db.one("sdr_campaigns", {"id": f"eq.{campaign_id}"}) or {}

    def history(self, lead_id) -> List[Dict]:
        return self.db.select(
            "sdr_messages",
            {"lead_id": f"eq.{lead_id}", "status": _in(("sent", "received"))},
            order="created_at.asc",
        )

    def _session_failed(self, e: Exception) -> Dict:
        self.mark_session(False, str(e))
        return {"ok": False, "error": str(e)}

    # ---------- sesión ----------

    def check_session(self) -> Dict:
        if li.proxy_required(self.settings):
            return {"ok": False, "proxy_required": True, "error": li.PROXY_MSG}
        proxy = None
        if li.proxy_url(self.settings):
            try:
                proxy = li.proxy_info(li.proxy_url(self.settings))
            except li.LinkedInError as e:
                return {"ok": False, "error": str(e)}  # el proxy falla: la sesión no tiene la culpa
        try:
            profile = li.me(self.api)
        except li.LinkedInError as e:
            return {**self._session_failed(e), "proxy": proxy}
        self.mark_session(True, profile=profile)
        return {"ok": True, "profile": profile, "proxy": proxy}

    def sync_session(self, cookies: Dict, user_agent: str = "", accept_language: str = "", source: str = "extension") -> Dict:
        """Sesión enviada por la extensión desde el navegador de Enrique.

        Si es la misma que ya funciona sólo se apunta la hora (la extensión avisa cada 30 min);
        si cambia se comprueba con LinkedIn antes de dar paso al motor. Una cuenta distinta a la
        ya conectada se rechaza, como el "identity conflict" de WaLead.
        """
        cookies = li.clean_cookies(cookies)
        li_at = cookies.get("li_at", "")
        jsessionid = cookies.get("JSESSIONID", "").strip('"')
        if not li_at or not jsessionid:
            raise JobError("Faltan li_at o JSESSIONID: Enrique no tiene la sesión de LinkedIn abierta en el navegador")

        s = self.settings
        values = {
            "li_at": li_at,
            "jsessionid": jsessionid,
            "li_cookies": cookies,
            "li_user_agent": (user_agent or "").strip()[:500] or s.get("li_user_agent"),
            "li_accept_language": (accept_language or "").strip()[:200] or s.get("li_accept_language"),
            "li_session_source": source[:40] or "extension",
            "li_session_synced_at": now_iso(),
        }
        same = li_at == s.get("li_at") and jsessionid == (s.get("jsessionid") or "").strip('"')
        checked = s.get("li_session_checked_at")
        fresh = bool(checked) and _now() - datetime.fromisoformat(checked) < timedelta(hours=6)
        if same and s.get("li_session_status") == "ok" and fresh:
            self.db.update("sdr_settings", {"id": "eq.1"}, values)
            return {"ok": True, "changed": False, "profile": s.get("li_profile")}

        candidate = {**s, **values}
        if li.proxy_required(candidate):
            # Se guarda sin probarla: probarla desde el servidor sin proxy es lo que la quema.
            self.db.update("sdr_settings", {"id": "eq.1"}, {**values, "li_session_status": "unknown"})
            self._settings = {**candidate, "li_session_status": "unknown"}
            return {"ok": False, "proxy_required": True, "error": "Sesión guardada. " + li.PROXY_MSG}
        try:
            profile = li.me(self._client_factory(candidate))
        except li.LinkedInError as e:
            # Se guardan igualmente: son las cookies más recientes del navegador.
            self.db.update("sdr_settings", {"id": "eq.1"}, values)
            self._settings = candidate
            return self._session_failed(e)

        previous = (s.get("li_profile") or {}).get("urn_id")
        if previous and profile.get("urn_id") and previous != profile["urn_id"]:
            raise JobError(
                f"La sesión del navegador es de {profile.get('name') or 'otra cuenta'}, no de "
                f"{(s.get('li_profile') or {}).get('name') or 'la cuenta conectada'}. Entra en LinkedIn con la cuenta correcta."
            )

        self.db.update("sdr_settings", {"id": "eq.1"}, values)
        self._settings = candidate
        self.mark_session(True, profile=profile)
        if not same:
            self.log("session_synced", f"Sesión de LinkedIn actualizada desde {values['li_session_source']}")
        return {"ok": True, "changed": not same, "profile": profile}

    # ---------- 1. prospección ----------

    def prospect(self, force: bool = False, campaign_id: Optional[str] = None) -> Dict:
        reason = self._guard(force, need_hours=False)
        if reason:
            return {"ok": True, "skipped": reason}
        filters = {"id": f"eq.{campaign_id}"} if campaign_id else {"status": "eq.active"}
        summary = []
        for c in self.db.select("sdr_campaigns", filters):
            pipeline = self.db.count("sdr_leads", {"campaign_id": f"eq.{c['id']}", "status": _in(PIPELINE)})
            if pipeline >= c["pipeline_buffer"] and not force:
                summary.append({"campaign": c["name"], "skipped": f"ya hay {pipeline} leads en cola"})
                continue
            try:
                people = li.search_people(self.api, c, limit=c["search_batch"], offset=c["search_offset"])
            except li.SessionError as e:
                return self._session_failed(e)
            rows = [
                {
                    "campaign_id": c["id"],
                    "urn_id": p["urn_id"],
                    "public_id": p["public_id"],
                    "full_name": p["full_name"],
                    "first_name": p["first_name"],
                    "headline": p["headline"],
                    "location": p["location"],
                    "profile_url": p["profile_url"],
                    "distance": p["distance"],
                    "profile_text": li.profile_text(p, None),
                }
                for p in people
            ]
            inserted = self.db.insert("sdr_leads", rows, on_conflict="urn_id", ignore_duplicates=True) if rows else []
            self.db.update(
                "sdr_campaigns",
                {"id": f"eq.{c['id']}"},
                {"search_offset": c["search_offset"] + len(people), "last_prospected_at": now_iso()},
            )
            detail = f"{len(people)} perfiles encontrados, {len(inserted)} nuevos"
            if not people:
                detail = "La búsqueda no devuelve más resultados: amplía los filtros o reinicia el desplazamiento"
            self.log("prospect", detail, campaign_id=c["id"])
            summary.append({"campaign": c["name"], "found": len(people), "new": len(inserted)})
        return {"ok": True, "campaigns": summary}

    def research(self, segment: Dict, sample: int = 5) -> Dict:
        """Estudio de mercado: tamaño del segmento en LinkedIn y una muestra de perfiles."""
        try:
            total = li.search_total(self.api, segment)
            people = li.search_people(self.api, segment, limit=sample, offset=0) if sample else []
        except li.SessionError as e:
            return self._session_failed(e)
        return {"ok": True, "total": total, "people": people}

    def research_profile(self, public_id: str) -> Dict:
        try:
            profile = li.get_profile(self.api, public_id, public_id)
        except li.SessionError as e:
            return self._session_failed(e)
        return {"ok": bool(profile), "profile": profile}

    def search_preview(self, campaign: Dict, limit: int = 10) -> Dict:
        try:
            return {"ok": True, "people": li.search_people(self.api, campaign, limit=limit, offset=0)}
        except li.SessionError as e:
            return self._session_failed(e)

    # ---------- 2. enriquecer + cualificar (IA en n8n) ----------

    def next_to_qualify(self, limit: int = 5, force: bool = False) -> Dict:
        reason = self._guard(force, need_hours=False)
        if reason:
            return {"ok": True, "skipped": reason, "items": []}
        if not (self.settings.get("company_pitch") or "").strip():
            return {"ok": False, "error": "Describe la empresa en Ajustes antes de cualificar", "items": []}
        leads = self.db.select(
            "sdr_leads", {"status": "eq.new", "or": _unlocked()}, order="created_at.asc", limit=limit
        )
        items = []
        for lead in leads:
            lock = _iso(_now() + timedelta(minutes=LOCK_MINUTES))
            values: Dict = {"locked_until": lock}
            if lead.get("profile") is None:
                try:
                    profile = li.get_profile(self.api, lead.get("public_id"), lead["urn_id"])
                except li.SessionError as e:
                    return {**self._session_failed(e), "items": items}
                if profile:
                    values["profile"] = profile
                    values["profile_text"] = li.profile_text(lead, profile)
                    values["public_id"] = lead.get("public_id") or profile.get("public_id")
                    values["company"] = li.current_company(profile)
                else:
                    values["profile"] = {}  # no reintentar en cada vuelta
            lead = {**lead, **values}
            self.db.update("sdr_leads", {"id": f"eq.{lead['id']}"}, values)
            items.append(
                {
                    "lead_id": lead["id"],
                    "name": lead["full_name"],
                    **prompts.qualify(self.settings, self.campaign(lead.get("campaign_id")), lead),
                }
            )
        return {"ok": True, "items": items}

    def save_qualification(self, lead_id: str, result: Dict) -> Dict:
        lead = self.db.one("sdr_leads", {"id": f"eq.{lead_id}"})
        if not lead:
            raise JobError("Lead no encontrado")
        try:
            score = int(result.get("score") or 0)
        except (TypeError, ValueError):
            score = 0
        qualified = bool(result.get("qualified")) and score >= int(self.settings.get("min_score") or 0)
        note = (result.get("connection_note") or "").strip()[: li.NOTE_MAX]
        if not qualified:
            status = "disqualified"
        else:
            status = "to_invite" if self.settings.get("autopilot") else "invite_review"
        values = {
            "status": status,
            "score": score,
            "fit_reason": (result.get("reason") or "")[:500],
            "ai_summary": (result.get("summary") or "")[:1500],
            "connection_note": note,
            "locked_until": None,
        }
        if result.get("company") and not lead.get("company"):
            values["company"] = result["company"][:200]
        self.db.update("sdr_leads", {"id": f"eq.{lead_id}"}, values)
        self.log("qualified" if qualified else "disqualified", f"Puntuación {score}: {values['fit_reason']}", lead_id, lead.get("campaign_id"))
        return {"ok": True, "status": status}

    # ---------- 3. invitaciones ----------

    def invite(self, force: bool = False, lead_id: Optional[str] = None) -> Dict:
        reason = self._guard(force or bool(lead_id))
        if reason:
            return {"ok": True, "skipped": reason}
        s = self.settings
        if self.count_events("invite_sent", self.day_start()) >= s.get("daily_invite_limit", 15):
            return {"ok": True, "skipped": "límite diario de invitaciones alcanzado"}
        if self.count_events("invite_sent", self.week_start()) >= s.get("weekly_invite_limit", 80):
            return {"ok": True, "skipped": "límite semanal de invitaciones alcanzado"}
        if not force and not lead_id and random.random() < 0.25:
            return {"ok": True, "skipped": "pausa aleatoria para parecer humano"}

        if lead_id:
            leads = self.db.select("sdr_leads", {"id": f"eq.{lead_id}", "status": _in(("to_invite", "invite_review"))})
        else:
            leads = self.db.select("sdr_leads", {"status": "eq.to_invite"}, order="updated_at.asc", limit=1)
        if not leads:
            return {"ok": True, "skipped": "no hay leads listos para invitar"}
        lead = leads[0]
        campaign = self.campaign(lead.get("campaign_id"))
        note = lead.get("connection_note") if campaign.get("send_connection_note", True) else ""

        try:
            ok, detail = li.invite(self.api, lead["urn_id"], note or "")
            if not ok and note:
                # Las cuentas gratuitas tienen un cupo mensual de notas: reintentamos sin nota.
                ok, detail2 = li.invite(self.api, lead["urn_id"], "")
                if ok:
                    detail = "enviada sin nota (cupo de notas agotado o nota rechazada)"
                    note = ""
                else:
                    detail = detail2
        except li.SessionError as e:
            return self._session_failed(e)

        if ok or "CANT_RESEND_YET" in detail:
            self.db.update(
                "sdr_leads",
                {"id": f"eq.{lead['id']}"},
                {"status": "invited", "invited_at": now_iso(), "last_checked_at": now_iso(), "error": None},
            )
            if ok:
                self.log("invite_sent", detail if note == "" else f"Nota: {note}", lead["id"], lead.get("campaign_id"))
            else:
                self.log("invite_pending", "Ya había una invitación pendiente", lead["id"], lead.get("campaign_id"))
            return {"ok": True, "invited": lead["full_name"], "detail": detail}

        self.db.update("sdr_leads", {"id": f"eq.{lead['id']}"}, {"status": "error", "error": detail})
        self.log("invite_failed", detail, lead["id"], lead.get("campaign_id"))
        return {"ok": False, "error": detail}

    # ---------- 4. aceptaciones ----------

    def check_connections(self, limit: int = 10, force: bool = False) -> Dict:
        reason = self._guard(force, need_hours=False)
        if reason:
            return {"ok": True, "skipped": reason}
        recheck = _iso(_now() - timedelta(hours=6))
        leads = self.db.select(
            "sdr_leads",
            {"status": "eq.invited", "or": f"(last_checked_at.is.null,last_checked_at.lt.{recheck})"},
            order="last_checked_at.asc.nullsfirst",
            limit=limit,
        )
        connected, expired = [], 0
        for lead in leads:
            try:
                distance = li.network_distance(self.api, lead.get("public_id") or lead["urn_id"])
            except li.SessionError as e:
                return self._session_failed(e)
            if distance == "DISTANCE_1":
                campaign = self.campaign(lead.get("campaign_id"))
                delay = campaign.get("first_message_delay_hours", 24)
                self.db.update(
                    "sdr_leads",
                    {"id": f"eq.{lead['id']}"},
                    {
                        "status": "connected",
                        "connected_at": now_iso(),
                        "last_checked_at": now_iso(),
                        "next_action_at": _iso(_now() + timedelta(hours=delay)),
                    },
                )
                self.log("connected", "Ha aceptado la invitación", lead["id"], lead.get("campaign_id"))
                connected.append(lead["full_name"])
                continue
            invited_at = lead.get("invited_at")
            if invited_at and datetime.fromisoformat(invited_at) < _now() - timedelta(days=30):
                self.db.update("sdr_leads", {"id": f"eq.{lead['id']}"}, {"status": "no_response", "last_checked_at": now_iso()})
                self.log("invite_expired", "Sin aceptar tras 30 días", lead["id"], lead.get("campaign_id"))
                expired += 1
            else:
                self.db.update("sdr_leads", {"id": f"eq.{lead['id']}"}, {"last_checked_at": now_iso()})
        return {"ok": True, "checked": len(leads), "connected": connected, "expired": expired}

    # ---------- 5. mensajes y seguimientos (IA en n8n) ----------

    def due_messages(self, limit: int = 5, force: bool = False) -> Dict:
        reason = self._guard(force, need_hours=False)
        if reason:
            return {"ok": True, "skipped": reason, "items": []}
        leads = self.db.select(
            "sdr_leads",
            {"status": _in(("connected", "messaged")), "next_action_at": f"lte.{now_iso()}", "or": _unlocked()},
            order="next_action_at.asc",
            limit=limit,
        )
        items = []
        for lead in leads:
            campaign = self.campaign(lead.get("campaign_id"))
            delays = campaign.get("followup_delays_days") or []
            if lead["status"] == "connected":
                kind, number = "first_message", 0
            elif lead["followups_sent"] < len(delays):
                kind, number = "followup", lead["followups_sent"] + 1
            else:
                self.db.update("sdr_leads", {"id": f"eq.{lead['id']}"}, {"status": "no_response", "next_action_at": None})
                self.log("no_response", "Secuencia terminada sin respuesta", lead["id"], lead.get("campaign_id"))
                continue
            self.db.update(
                "sdr_leads",
                {"id": f"eq.{lead['id']}"},
                {"locked_until": _iso(_now() + timedelta(minutes=LOCK_MINUTES))},
            )
            items.append(
                {
                    "lead_id": lead["id"],
                    "name": lead["full_name"],
                    "kind": kind,
                    **prompts.message(self.settings, campaign, lead, kind, number, self.history(lead["id"])),
                }
            )
        return {"ok": True, "items": items}

    def save_draft(self, lead_id: str, kind: str, body: str, ai_generated: bool = True) -> Dict:
        body = (body or "").strip()
        if not body:
            raise JobError("Mensaje vacío")
        lead = self.db.one("sdr_leads", {"id": f"eq.{lead_id}"})
        if not lead:
            raise JobError("Lead no encontrado")
        s = self.settings
        auto = s.get("auto_reply") if kind == "reply" else s.get("autopilot")
        status = "approved" if auto else "draft"
        msg = self.db.insert(
            "sdr_messages",
            {"lead_id": lead_id, "direction": "out", "kind": kind, "body": body, "status": status, "ai_generated": ai_generated},
        )[0]
        self.db.update("sdr_leads", {"id": f"eq.{lead_id}"}, {"locked_until": None, "next_action_at": None})
        self.log("draft_created", f"{kind}: {body[:140]}", lead_id, lead.get("campaign_id"))
        return {"ok": True, "message_id": msg["id"], "status": status}

    # ---------- 6. envío de la cola ----------

    def send_outbox(self, force: bool = False, message_id: Optional[str] = None, max_per_run: int = 2) -> Dict:
        reason = self._guard(force or bool(message_id))
        if reason:
            return {"ok": True, "skipped": reason}
        sent_today = self.count_events("message_sent", self.day_start())
        if sent_today >= self.settings.get("daily_message_limit", 30) and not message_id:
            return {"ok": True, "skipped": "límite diario de mensajes alcanzado"}
        if not force and not message_id and random.random() < 0.2:
            return {"ok": True, "skipped": "pausa aleatoria para parecer humano"}

        if message_id:
            msgs = self.db.select("sdr_messages", {"id": f"eq.{message_id}", "status": _in(("draft", "approved", "failed"))})
        else:
            msgs = self.db.select("sdr_messages", {"status": "eq.approved", "direction": "eq.out"}, order="created_at.asc", limit=max_per_run)
        results = []
        for m in msgs:
            lead = self.db.one("sdr_leads", {"id": f"eq.{m['lead_id']}"})
            sequence = m["kind"] in ("first_message", "followup")
            if not lead or lead["status"] == "do_not_contact" or (sequence and lead["status"] not in ("connected", "messaged")):
                self.db.update("sdr_messages", {"id": f"eq.{m['id']}"}, {"status": "cancelled"})
                results.append({"message_id": m["id"], "cancelled": True})
                continue
            try:
                li.send_message(self.api, lead["urn_id"], m["body"], lead.get("conversation_urn_id"))
            except li.SessionError as e:
                return self._session_failed(e)
            except li.LinkedInError as e:
                self.db.update("sdr_messages", {"id": f"eq.{m['id']}"}, {"status": "failed", "error": str(e)[:500]})
                self.log("message_failed", str(e), lead["id"], lead.get("campaign_id"))
                results.append({"message_id": m["id"], "error": str(e)})
                continue
            self.db.update("sdr_messages", {"id": f"eq.{m['id']}"}, {"status": "sent", "sent_at": now_iso(), "error": None})
            values: Dict = {"last_outbound_at": now_iso()}
            if m["kind"] in ("first_message", "followup"):
                campaign = self.campaign(lead.get("campaign_id"))
                delays = campaign.get("followup_delays_days") or []
                done = lead["followups_sent"] + (1 if m["kind"] == "followup" else 0)
                wait = delays[done] if done < len(delays) else (delays[-1] if delays else 7)
                values.update({"status": "messaged", "followups_sent": done, "next_action_at": _iso(_now() + timedelta(days=wait))})
            self.db.update("sdr_leads", {"id": f"eq.{lead['id']}"}, values)
            self.log("message_sent", m["body"][:200], lead["id"], lead.get("campaign_id"))
            results.append({"message_id": m["id"], "sent": True})
        return {"ok": True, "results": results}

    # ---------- 7. bandeja de entrada (IA en n8n) ----------

    def sync_inbox(self, force: bool = False) -> Dict:
        reason = self._guard(force, need_hours=False)
        if reason:
            return {"ok": True, "skipped": reason, "items": []}
        me = (self.settings.get("li_profile") or {}).get("urn_id")
        try:
            if not me:
                me = li.me(self.api)["urn_id"]
            convs = li.conversations(self.api)
        except li.SessionError as e:
            return {**self._session_failed(e), "items": []}

        by_urn: Dict[str, Dict] = {}
        urns = {p for c in convs for p in c["participants"] if p != me}
        if urns:
            for lead in self.db.select("sdr_leads", {"urn_id": _in(urns)}):
                by_urn[lead["urn_id"]] = lead

        items, synced = [], 0
        for conv in convs:
            lead = next((by_urn[p] for p in conv["participants"] if p in by_urn), None)
            if not lead or lead["status"] in PIPELINE + ("disqualified",):
                continue
            last_sync = lead.get("inbox_synced_at")
            activity = datetime.fromtimestamp(conv["last_activity_ms"] / 1000, tz=timezone.utc)
            if last_sync and activity <= datetime.fromisoformat(last_sync):
                continue
            try:
                events = li.conversation_events(self.api, conv["id"])
            except li.SessionError as e:
                return {**self._session_failed(e), "items": items}
            new_inbound = self._store_events(lead, events, me)
            synced += 1
            values: Dict = {"inbox_synced_at": now_iso(), "conversation_urn_id": conv["id"]}
            if new_inbound:
                last = new_inbound[-1]
                values["last_inbound_at"] = last["created_at"]
                if lead["status"] in ("invited", "connected", "messaged", "no_response"):
                    values["status"] = "replied"
                values["next_action_at"] = None
                # Si ha respondido, la secuencia automática se detiene.
                self.db.update(
                    "sdr_messages",
                    {"lead_id": f"eq.{lead['id']}", "status": _in(("draft", "approved")), "kind": _in(("first_message", "followup"))},
                    {"status": "cancelled"},
                )
                self.log("reply_received", last["body"][:200], lead["id"], lead.get("campaign_id"))
            self.db.update("sdr_leads", {"id": f"eq.{lead['id']}"}, values)
            if new_inbound and lead.get("status") not in ("not_interested", "do_not_contact"):
                lead = {**lead, **values}
                items.append(
                    {
                        "lead_id": lead["id"],
                        "message_id": new_inbound[-1]["id"],
                        "name": lead["full_name"],
                        **prompts.reply(self.settings, self.campaign(lead.get("campaign_id")), lead, self.history(lead["id"])),
                    }
                )
        return {"ok": True, "conversations": len(convs), "synced": synced, "items": items}

    def _store_events(self, lead: Dict, events: List[Dict], me: str) -> List[Dict]:
        known = {
            m["linkedin_event_urn"]: m
            for m in self.db.select("sdr_messages", {"lead_id": f"eq.{lead['id']}"})
            if m.get("linkedin_event_urn")
        }
        unmatched_out = [
            m for m in self.db.select(
                "sdr_messages", {"lead_id": f"eq.{lead['id']}", "direction": "eq.out", "status": "eq.sent", "linkedin_event_urn": "is.null"}
            )
        ]
        new_inbound = []
        for ev in events:
            if not ev["urn"] or ev["urn"] in known:
                continue
            created = _iso(datetime.fromtimestamp(ev["created_ms"] / 1000, tz=timezone.utc))
            if ev["from"] == me:
                match = next((m for m in unmatched_out if m["body"].strip() == ev["text"]), None)
                if match:
                    self.db.update("sdr_messages", {"id": f"eq.{match['id']}"}, {"linkedin_event_urn": ev["urn"]})
                    unmatched_out.remove(match)
                else:
                    # Mensaje que Enrique escribió a mano desde LinkedIn.
                    self.db.insert(
                        "sdr_messages",
                        {"lead_id": lead["id"], "direction": "out", "kind": "manual", "body": ev["text"], "status": "sent",
                         "sent_at": created, "created_at": created, "linkedin_event_urn": ev["urn"]},
                        on_conflict="linkedin_event_urn", ignore_duplicates=True,
                    )
                continue
            rows = self.db.insert(
                "sdr_messages",
                {"lead_id": lead["id"], "direction": "in", "kind": "inbound", "body": ev["text"], "status": "received",
                 "created_at": created, "sent_at": created, "linkedin_event_urn": ev["urn"]},
                on_conflict="linkedin_event_urn", ignore_duplicates=True,
            )
            new_inbound.extend(rows)
        return new_inbound

    def save_reply_analysis(self, lead_id: str, result: Dict) -> Dict:
        lead = self.db.one("sdr_leads", {"id": f"eq.{lead_id}"})
        if not lead:
            raise JobError("Lead no encontrado")
        intent = (result.get("intent") or "neutral").strip().lower()
        if result.get("message_id"):
            self.db.update("sdr_messages", {"id": f"eq.{result['message_id']}"}, {"intent": intent})
        values: Dict = {"intent": intent, "locked_until": None}
        status_by_intent = {"interested": "interested", "meeting": "meeting", "not_interested": "not_interested"}
        if intent in status_by_intent and lead["status"] not in ("meeting", "do_not_contact"):
            values["status"] = status_by_intent[intent]
        self.db.update("sdr_leads", {"id": f"eq.{lead_id}"}, values)
        self.log("reply_classified", f"{intent}: {result.get('reason') or ''}", lead_id, lead.get("campaign_id"))
        draft = None
        reply_text = (result.get("reply") or "").strip()
        if reply_text and intent != "out_of_office":
            if intent == "not_interested":
                # Nunca se manda sola: Enrique decide si contesta.
                draft = self.db.insert(
                    "sdr_messages",
                    {"lead_id": lead_id, "direction": "out", "kind": "reply", "body": reply_text, "status": "draft", "ai_generated": True},
                )[0]["id"]
            else:
                draft = self.save_draft(lead_id, "reply", reply_text)["message_id"]
        return {"ok": True, "intent": intent, "draft_id": draft}

    # ---------- 8. interacción con publicaciones (IA en n8n) ----------

    def _engagement_guard(self, force: bool, need_hours: bool) -> Optional[str]:
        reason = self._guard(force, need_hours=need_hours)
        if reason:
            return reason
        if not force and not self.settings.get("engagement_enabled", True):
            return "interacción con publicaciones desactivada"
        return None

    def engage_batch(self, leads: int = 4, feed: int = 15, limit: int = 8, force: bool = False) -> Dict:
        """Recoge publicaciones nuevas (de leads y del feed) y devuelve las pendientes con su prompt."""
        reason = self._engagement_guard(force, need_hours=False)
        if reason:
            return {"ok": True, "skipped": reason, "items": []}
        collected = 0
        try:
            since = _iso(_now() - timedelta(days=10))
            targets = self.db.select(
                "sdr_leads",
                {
                    "status": _in(("invite_review", "to_invite", "invited", "connected", "messaged")),
                    "or": f"(last_engaged_at.is.null,last_engaged_at.lt.{since})",
                },
                order="score.desc.nullslast",
                limit=leads,
            )
            for lead in targets:
                fresh = [p for p in li.profile_posts(self.api, lead["urn_id"], count=3)
                         if (li.age_days(p["post_age"]) or 0) <= 21]
                if fresh:
                    rows = self.db.insert(
                        "sdr_engagements",
                        {**fresh[0], "lead_id": lead["id"], "source": "lead"},
                        on_conflict="post_urn", ignore_duplicates=True,
                    )
                    collected += len(rows)
                self.db.update("sdr_leads", {"id": f"eq.{lead['id']}"}, {"last_engaged_at": now_iso()})
            if feed:
                me = (self.settings.get("li_profile") or {}).get("name")
                posts = [p for p in li.feed_posts(self.api, limit=feed) if p["author_name"] != me]
                if posts:
                    collected += len(self.db.insert(
                        "sdr_engagements", [{**p, "source": "feed"} for p in posts],
                        on_conflict="post_urn", ignore_duplicates=True,
                    ))
        except li.SessionError as e:
            return {**self._session_failed(e), "items": []}

        pending = self.db.select(
            "sdr_engagements", {"status": "eq.new", "or": _unlocked()}, order="created_at.asc", limit=limit
        )
        items = []
        for post in pending:
            self.db.update(
                "sdr_engagements", {"id": f"eq.{post['id']}"},
                {"locked_until": _iso(_now() + timedelta(minutes=LOCK_MINUTES))},
            )
            lead = self.db.one("sdr_leads", {"id": f"eq.{post['lead_id']}"}) if post.get("lead_id") else {}
            items.append({"engagement_id": post["id"], **prompts.engagement(self.settings, post, lead or {})})
        if collected:
            self.log("posts_collected", f"{collected} publicaciones nuevas para revisar")
        return {"ok": True, "collected": collected, "items": items}

    def save_engagement(self, engagement_id: str, result: Dict) -> Dict:
        post = self.db.one("sdr_engagements", {"id": f"eq.{engagement_id}"})
        if not post:
            raise JobError("Publicación no encontrada")
        try:
            score = int(result.get("score") or 0)
        except (TypeError, ValueError):
            score = 0
        relevant = bool(result.get("relevant"))
        comment = (result.get("comment") or "").strip()[:1200] if relevant else ""
        values: Dict = {
            "relevance": score,
            "reason": (result.get("reason") or "")[:500],
            "locked_until": None,
            "want_like": relevant and bool(result.get("like")),
            "comment": comment,
            "comment_status": ("approved" if self.settings.get("auto_comment") else "draft") if comment else "none",
        }
        values["status"] = "ready" if (values["want_like"] or comment) else "skipped"
        self.db.update("sdr_engagements", {"id": f"eq.{engagement_id}"}, values)
        return {"ok": True, "status": values["status"], "comment_status": values["comment_status"]}

    def engage_run(self, force: bool = False, engagement_id: Optional[str] = None) -> Dict:
        """Da los me gusta pendientes y publica los comentarios aprobados, con límites diarios."""
        reason = self._engagement_guard(force or bool(engagement_id), need_hours=True)
        if reason:
            return {"ok": True, "skipped": reason}
        if not force and not engagement_id and random.random() < 0.2:
            return {"ok": True, "skipped": "pausa aleatoria para parecer humano"}
        s = self.settings
        likes_left = s.get("daily_like_limit", 25) - self.count_events("post_liked", self.day_start())
        comments_left = s.get("daily_comment_limit", 8) - self.count_events("post_commented", self.day_start())

        if engagement_id:
            rows = self.db.select("sdr_engagements", {"id": f"eq.{engagement_id}"})
        else:
            # Los comentarios en borrador esperan aprobación: no deben tapar los me gusta pendientes.
            rows = [
                r for r in self.db.select("sdr_engagements", {"status": "eq.ready"}, order="created_at.asc", limit=100)
                if (r["want_like"] and not r.get("liked_at")) or r["comment_status"] == "approved"
            ][:6]
        done = {"liked": 0, "commented": 0, "errors": []}
        for post in rows:
            values: Dict = {}
            try:
                if post["want_like"] and not post.get("liked_at") and likes_left > 0 and done["liked"] < 2:
                    li.like_post(self.api, post["post_urn"])
                    values["liked_at"] = now_iso()
                    likes_left -= 1
                    done["liked"] += 1
                    self.log("post_liked", f"{post['author_name']}: {post['post_text'][:120]}", post.get("lead_id"))
                if post["comment_status"] == "approved" and comments_left > 0 and done["commented"] < 1:
                    li.comment_post(self.api, post["post_urn"], post["comment"])
                    values.update({"comment_status": "posted", "commented_at": now_iso()})
                    comments_left -= 1
                    done["commented"] += 1
                    self.log("post_commented", f"{post['author_name']}: {post['comment'][:160]}", post.get("lead_id"))
            except li.SessionError as e:
                return self._session_failed(e)
            except li.LinkedInError as e:
                values.update({"error": str(e)[:500]})
                if post["comment_status"] == "approved":
                    values["comment_status"] = "failed"
                done["errors"].append(str(e))
                self.log("engagement_failed", str(e), post.get("lead_id"))
            merged = {**post, **values}
            like_pending = merged["want_like"] and not merged.get("liked_at") and "error" not in values
            comment_pending = merged["comment_status"] in ("draft", "approved")
            if not like_pending and not comment_pending:
                values["status"] = "failed" if "error" in values and not merged.get("liked_at") else "done"
            if values:
                self.db.update("sdr_engagements", {"id": f"eq.{post['id']}"}, values)
        return {"ok": True, **done}
