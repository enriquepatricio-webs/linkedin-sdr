"""Envoltorio sobre open-linkedin-api (https://github.com/EseToni/open-linkedin-api).

La sesión es la de Enrique: la extensión de Chrome (carpeta extension/) sincroniza las cookies
y el user agent de su navegador; también se pueden pegar li_at + JSESSIONID a mano. Las llamadas
que la librería no protege (respuestas no JSON, sesión caducada) se comprueban aquí para
poder marcar la sesión como inválida desde el panel.
"""

import json
import os
import re
import uuid
from typing import Dict, List, Optional, Tuple

from requests.cookies import RequestsCookieJar
from open_linkedin_api import Linkedin
from open_linkedin_api.utils.helpers import (
    generate_trackingId_as_charString,
    get_id_from_urn,
    get_urn_from_raw_update,
)

USER_AGENT = os.environ.get(
    "LINKEDIN_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
)

NOTE_MAX = 200  # las cuentas gratuitas sólo admiten 200 caracteres en la nota


class LinkedInError(Exception):
    pass


class SessionError(LinkedInError):
    """Las cookies ya no valen: hay que pegarlas de nuevo en Ajustes."""


COOKIE_NAME = re.compile(r"^[A-Za-z0-9_.\-]{1,64}$")


def clean_cookies(cookies: Dict) -> Dict[str, str]:
    """Cookies de linkedin.com tal y como las manda la extensión (nombre → valor), sin basura."""
    out = {}
    for name, value in (cookies or {}).items():
        if isinstance(value, str) and COOKIE_NAME.match(str(name)) and 0 < len(value) <= 4096:
            out[str(name)] = value.strip()
    return out


def make_client(settings: Dict) -> Linkedin:
    li_at = (settings.get("li_at") or os.environ.get("LINKEDIN_LI_AT") or "").strip()
    jsessionid = (settings.get("jsessionid") or os.environ.get("LINKEDIN_JSESSIONID") or "").strip()
    if not li_at or not jsessionid:
        raise SessionError("Faltan las cookies de LinkedIn (li_at y JSESSIONID) en Ajustes")

    jsessionid = jsessionid.strip('"')
    jar = RequestsCookieJar()
    # Como WaLead: todas las cookies del navegador (bcookie, bscookie, lidc...), no sólo li_at.
    # Un li_at sin el bcookie del navegador que lo creó es lo que LinkedIn trata como sesión robada.
    for name, value in clean_cookies(settings.get("li_cookies") or {}).items():
        if name not in ("li_at", "JSESSIONID"):
            jar.set(name, value, domain=".linkedin.com", path="/")
    jar.set("li_at", li_at, domain=".www.linkedin.com", path="/")
    jar.set("JSESSIONID", f'"{jsessionid}"', domain=".www.linkedin.com", path="/")

    proxy = (settings.get("li_proxy") or os.environ.get("LINKEDIN_PROXY") or "").strip()
    proxies = {"http": proxy, "https": proxy} if proxy else {}

    api = Linkedin("", "", cookies=jar, proxies=proxies)
    headers = api.client.session.headers
    headers["user-agent"] = (settings.get("li_user_agent") or "").strip() or USER_AGENT
    headers["accept-language"] = (settings.get("li_accept_language") or "").strip() or "es-ES,es;q=0.9,en;q=0.8"
    headers["x-li-lang"] = "es_ES" if headers["accept-language"].lower().startswith("es") else "en_US"
    return api


def _json(res, what: str):
    if res.status_code in (401, 403) or "/login" in (res.url or "") or "/checkpoint" in (res.url or ""):
        # Pistas para distinguir sesión anulada (li_at=delete me) de CSRF o bloqueo de IP.
        cookies = res.headers.get("set-cookie", "")
        hint = "LinkedIn borró li_at: sesión cerrada" if "li_at=delete" in cookies else res.text[:120].replace("\n", " ")
        raise SessionError(f"LinkedIn rechazó la sesión ({res.status_code}) en {what}. {hint}")
    if res.status_code >= 400:
        raise LinkedInError(f"LinkedIn devolvió {res.status_code} en {what}: {res.text[:200]}")
    try:
        return res.json()
    except ValueError:
        raise SessionError(f"Respuesta no JSON en {what}: probablemente la sesión ha caducado")


def me(api: Linkedin) -> Dict:
    data = _json(api._fetch("/me"), "/me")
    mini = data.get("miniProfile") or {}
    urn = mini.get("entityUrn") or ""
    return {
        "urn_id": urn.split(":")[-1] if urn else None,
        "public_id": mini.get("publicIdentifier"),
        "name": " ".join(x for x in [mini.get("firstName"), mini.get("lastName")] if x),
        "headline": mini.get("occupation"),
    }


def _clean(value: str) -> str:
    # La búsqueda viaja dentro de las variables de GraphQL: paréntesis, comas y dos puntos la rompen.
    return " ".join(re.sub(r"[(),:]", " ", value or "").split())


def _public_id(url: str) -> Optional[str]:
    m = re.search(r"linkedin\.com/in/([^/?#]+)", url or "")
    return m.group(1) if m else None


def _search_params(campaign: Dict) -> Dict:
    filters = ["(key:resultType,value:List(PEOPLE))"]
    depths = [d for d in campaign.get("network_depths") or [] if d in ("F", "S", "O")]
    if depths:
        filters.append(f"(key:network,value:List({' | '.join(depths)}))")
    if campaign.get("search_regions"):
        filters.append(f"(key:geoUrn,value:List({' | '.join(campaign['search_regions'])}))")
    if campaign.get("search_industries"):
        filters.append(f"(key:industry,value:List({' | '.join(campaign['search_industries'])}))")
    if _clean(campaign.get("search_title")):
        filters.append(f"(key:title,value:List({_clean(campaign['search_title'])}))")
    if _clean(campaign.get("search_company")):
        filters.append(f"(key:company,value:List({_clean(campaign['search_company'])}))")

    params = {"filters": f"List({','.join(filters)})"}
    if _clean(campaign.get("search_keywords")):
        params["keywords"] = _clean(campaign["search_keywords"])
    return params


def search_total(api: Linkedin, campaign: Dict) -> Optional[int]:
    """Número de resultados que LinkedIn dice tener para estos filtros (una sola petición)."""
    params = _search_params(campaign)
    keywords = f"keywords:{params['keywords']}," if params.get("keywords") else ""
    res = api._fetch(
        f"/graphql?variables=(start:0,origin:GLOBAL_SEARCH_HEADER,"
        f"query:({keywords}flagshipSearchIntent:SEARCH_SRP,"
        f"queryParameters:{params['filters']},includeFiltersInResponse:false))"
        f"&queryId=voyagerSearchDashClusters.b0928897b71bd00a5a7291755dcd64f0"
    )
    data = _json(res, "búsqueda")
    clusters = (data.get("data") or {}).get("searchDashClustersByAll") or {}
    total = (clusters.get("metadata") or {}).get("totalResultCount")
    if total is None:
        total = (clusters.get("paging") or {}).get("total")
    return total


def search_people(api: Linkedin, campaign: Dict, limit: int, offset: int = 0) -> List[Dict]:
    params = _search_params(campaign)

    try:
        raw = api.search(params, limit=limit, offset=offset)
    except ValueError:
        raise SessionError("La búsqueda no devolvió JSON: probablemente la sesión ha caducado")

    people = []
    for item in raw:
        distance = (item.get("entityCustomTrackingInfo") or {}).get("memberDistance")
        if distance == "OUT_OF_NETWORK":
            continue  # "Miembro de LinkedIn" sin nombre: no se puede personalizar
        entity = item.get("entityUrn") or ""
        try:
            urn_id = get_id_from_urn(get_urn_from_raw_update(entity))
        except (IndexError, AttributeError):
            continue
        name = (item.get("title") or {}).get("text") or ""
        url = item.get("navigationUrl") or ""
        public_id = _public_id(url)
        people.append(
            {
                "urn_id": urn_id,
                "public_id": public_id,
                "full_name": name,
                "first_name": name.split(" ")[0] if name else "",
                "headline": (item.get("primarySubtitle") or {}).get("text") or "",
                "location": (item.get("secondarySubtitle") or {}).get("text") or "",
                "summary": (item.get("summary") or {}).get("text") or "",
                "distance": distance,
                "profile_url": f"https://www.linkedin.com/in/{public_id or urn_id}",
            }
        )
    return people


def get_profile(api: Linkedin, public_id: Optional[str], urn_id: str) -> Optional[Dict]:
    """Perfil compacto. El endpoint profileView falla a veces: entonces devolvemos None
    y la cualificación se hace con los datos de la búsqueda."""
    try:
        p = api.get_profile(public_id=public_id) if public_id else api.get_profile(urn_id=urn_id)
    except Exception:
        return None
    if not p:
        return None
    experience = []
    for e in (p.get("experience") or [])[:5]:
        tp = e.get("timePeriod") or {}
        start = (tp.get("startDate") or {}).get("year")
        end = (tp.get("endDate") or {}).get("year") or "actualidad"
        experience.append(
            {
                "title": e.get("title"),
                "company": e.get("companyName"),
                "period": f"{start}-{end}" if start else "",
                "description": (e.get("description") or "")[:400],
            }
        )
    return {
        "public_id": p.get("public_id"),
        "headline": p.get("headline"),
        "summary": (p.get("summary") or "")[:1200],
        "location": p.get("geoLocationName") or p.get("locationName"),
        "industry": p.get("industryName"),
        "experience": experience,
        "education": [
            {"school": e.get("schoolName"), "degree": e.get("degreeName"), "field": e.get("fieldOfStudy")}
            for e in (p.get("education") or [])[:2]
        ],
        "skills": [s.get("name") for s in (p.get("skills") or [])[:12] if s.get("name")],
    }


def profile_text(lead: Dict, profile: Optional[Dict]) -> str:
    lines = [
        f"Nombre: {lead.get('full_name')}",
        f"Titular: {(profile or {}).get('headline') or lead.get('headline')}",
        f"Ubicación: {(profile or {}).get('location') or lead.get('location')}",
    ]
    if lead.get("summary"):
        lines.append(f"Resumen en la búsqueda: {lead['summary']}")
    if profile:
        if profile.get("industry"):
            lines.append(f"Sector: {profile['industry']}")
        if profile.get("summary"):
            lines.append(f"Extracto: {profile['summary']}")
        for e in profile.get("experience") or []:
            line = f"Experiencia: {e.get('title')} en {e.get('company')} ({e.get('period')})"
            if e.get("description"):
                line += f" - {e['description']}"
            lines.append(line)
        for e in profile.get("education") or []:
            lines.append(f"Formación: {e.get('degree') or ''} {e.get('field') or ''} - {e.get('school')}")
        if profile.get("skills"):
            lines.append(f"Aptitudes: {', '.join(profile['skills'])}")
    return "\n".join(lines)


def current_company(profile: Optional[Dict]) -> str:
    for e in (profile or {}).get("experience") or []:
        if e.get("period", "").endswith("actualidad") and e.get("company"):
            return e["company"]
    return ""


def invite(api: Linkedin, urn_id: str, note: str = "") -> Tuple[bool, str]:
    """Envía la invitación. Devuelve (ok, detalle). Igual que Linkedin.add_connection pero
    conservando la respuesta para saber por qué falla."""
    payload = {"invitee": {"inviteeUnion": {"memberProfile": f"urn:li:fsd_profile:{urn_id}"}}}
    if note:
        payload["customMessage"] = note[:NOTE_MAX]
    res = api._post(
        "/voyagerRelationshipsDashMemberRelationships",
        data=json.dumps(payload),
        headers={"accept": "application/vnd.linkedin.normalized+json+2.1"},
        params={
            "action": "verifyQuotaAndCreateV2",
            "decorationId": "com.linkedin.voyager.dash.deco.relationships.InvitationCreationResultWithInvitee-2",
        },
    )
    if res.status_code == 401:
        raise SessionError("LinkedIn rechazó la sesión al invitar")
    if res.ok:
        return True, "ok"
    return False, f"{res.status_code} {res.text[:300]}"


def network_distance(api: Linkedin, profile_id: str) -> Optional[str]:
    res = api._fetch(
        f"/identity/profiles/{profile_id}/networkinfo",
        headers={"accept": "application/vnd.linkedin.normalized+json+2.1"},
    )
    if res.status_code in (401, 403):
        raise SessionError("LinkedIn rechazó la sesión al comprobar conexiones")
    if res.status_code != 200:
        return None
    try:
        data = res.json().get("data") or {}
    except ValueError:
        return None
    return (data.get("distance") or {}).get("value")


def send_message(api: Linkedin, urn_id: str, text: str, conversation_id: Optional[str] = None) -> None:
    event = {
        "eventCreate": {
            "originToken": str(uuid.uuid4()),
            "value": {
                "com.linkedin.voyager.messaging.create.MessageCreate": {
                    "attributedBody": {"text": text, "attributes": []},
                    "attachments": [],
                }
            },
            "trackingId": generate_trackingId_as_charString(),
        },
        "dedupeByClientGeneratedToken": False,
    }
    if conversation_id:
        res = api._post(
            f"/messaging/conversations/{conversation_id}/events",
            params={"action": "create"},
            data=json.dumps(event),
        )
    else:
        event["recipients"] = [urn_id]
        event["subtype"] = "MEMBER_TO_MEMBER"
        res = api._post(
            "/messaging/conversations",
            params={"action": "create"},
            data=json.dumps({"keyVersion": "LEGACY_INBOX", "conversationCreate": event}),
        )
    if res.status_code in (401, 403):
        raise SessionError("LinkedIn rechazó la sesión al enviar el mensaje")
    if res.status_code not in (200, 201):
        raise LinkedInError(f"No se pudo enviar ({res.status_code}): {res.text[:300]}")


def _member_urn_id(member: Dict) -> Optional[str]:
    mini = ((member or {}).get("com.linkedin.voyager.messaging.MessagingMember") or {}).get("miniProfile") or {}
    urn = mini.get("entityUrn")
    return urn.split(":")[-1] if urn else None


def conversations(api: Linkedin) -> List[Dict]:
    data = _json(api._fetch("/messaging/conversations", params={"keyVersion": "LEGACY_INBOX"}), "conversaciones")
    result = []
    for c in data.get("elements") or []:
        urn = c.get("entityUrn") or ""
        result.append(
            {
                "id": urn.split(":")[-1],
                "last_activity_ms": c.get("lastActivityAt") or 0,
                "participants": [p for p in (_member_urn_id(m) for m in c.get("participants") or []) if p],
            }
        )
    return result


def conversation_events(api: Linkedin, conversation_id: str) -> List[Dict]:
    data = _json(api._fetch(f"/messaging/conversations/{conversation_id}/events"), "mensajes")
    events = []
    for e in data.get("elements") or []:
        content = (e.get("eventContent") or {}).get("com.linkedin.voyager.messaging.event.MessageEvent") or {}
        text = (content.get("attributedBody") or {}).get("text") or content.get("body") or ""
        if not text.strip():
            continue
        events.append(
            {
                "urn": e.get("entityUrn") or e.get("dashEntityUrn"),
                "created_ms": e.get("createdAt") or 0,
                "from": _member_urn_id(e.get("from") or {}),
                "text": text.strip(),
            }
        )
    events.sort(key=lambda x: x["created_ms"])
    return events


# ---------- publicaciones: leer, "me gusta" y comentar ----------

_ACTIVITY = re.compile(r"urn:li:activity:(\d+)")
_AGE = re.compile(r"(\d+)\s*(mo|yr|min|m|h|d|w|y|sem|mes|año|a)\b", re.IGNORECASE)
_AGE_DAYS = {"min": 0, "m": 0, "h": 0, "d": 1, "w": 7, "sem": 7, "mo": 30, "mes": 30, "yr": 365, "y": 365, "año": 365, "a": 365}


def age_days(label: str) -> Optional[int]:
    """'3d •', '2w', '1mo', '5h' -> días aproximados (None si no se entiende)."""
    m = _AGE.search(label or "")
    if not m:
        return None
    return int(m.group(1)) * _AGE_DAYS[m.group(2).lower()]


def _text(node) -> str:
    if isinstance(node, dict):
        if isinstance(node.get("text"), str):
            return node["text"]
        return _text(node.get("text"))
    return node if isinstance(node, str) else ""


def profile_posts(api: Linkedin, urn_id: str, count: int = 3) -> List[Dict]:
    """Publicaciones propias recientes de un perfil (sin compartidos)."""
    try:
        raw = api.get_profile_posts(urn_id=urn_id, post_count=count)
    except ValueError:
        raise SessionError("Las publicaciones no devolvieron JSON: probablemente la sesión ha caducado")
    except (KeyError, TypeError):
        return []
    posts = []
    for el in raw or []:
        if not el or "resharedUpdate" in el:
            continue
        urn = (el.get("updateMetadata") or {}).get("urn") or ""
        m = _ACTIVITY.search(urn) or _ACTIVITY.search(json.dumps(el)[:4000])
        if not m:
            continue
        actor = el.get("actor") or {}
        age = _text(actor.get("subDescription"))
        posts.append(
            {
                "post_urn": f"urn:li:activity:{m.group(1)}",
                "post_url": f"https://www.linkedin.com/feed/update/urn:li:activity:{m.group(1)}/",
                "author_name": _text(actor.get("name")),
                "author_headline": _text(actor.get("description")),
                "post_text": _text(el.get("commentary"))[:3000],
                "post_age": age,
            }
        )
    return posts


def feed_posts(api: Linkedin, limit: int = 20) -> List[Dict]:
    """Publicaciones recientes del feed de Enrique (sin promocionadas)."""
    try:
        raw = api.get_feed_posts(limit=limit)
    except ValueError:
        raise SessionError("El feed no devolvió JSON: probablemente la sesión ha caducado")
    except (KeyError, TypeError, IndexError):
        return []
    posts = []
    for p in raw or []:
        m = _ACTIVITY.search(p.get("url") or "")
        if not m or not (p.get("content") or "").strip():
            continue
        posts.append(
            {
                "post_urn": f"urn:li:activity:{m.group(1)}",
                "post_url": f"https://www.linkedin.com/feed/update/urn:li:activity:{m.group(1)}/",
                "author_name": p.get("author_name") or "",
                "author_headline": "",
                "post_text": p["content"][:3000],
                "post_age": p.get("old") or "",
            }
        )
    return posts


def like_post(api: Linkedin, post_urn: str) -> None:
    activity_id = post_urn.split(":")[-1]
    res = api._post(
        "/voyagerSocialDashReactions",
        params={"threadUrn": f"urn:li:activity:{activity_id}"},
        data=json.dumps({"reactionType": "LIKE"}),
    )
    if res.status_code in (401, 403):
        raise SessionError("LinkedIn rechazó la sesión al dar me gusta")
    if res.status_code not in (200, 201):
        raise LinkedInError(f"No se pudo dar me gusta ({res.status_code}): {res.text[:200]}")


def comment_post(api: Linkedin, post_urn: str, text: str) -> None:
    """Comenta como lo hace la web de LinkedIn (endpoint interno, no lo trae la librería)."""
    payload = {
        "commentary": {
            "text": text,
            "attributesV2": [],
            "$type": "com.linkedin.voyager.dash.common.text.TextViewModel",
        },
        "threadUrn": post_urn,
    }
    res = api._post(
        "/voyagerSocialDashNormComments",
        params={"decorationId": "com.linkedin.voyager.dash.deco.social.NormComment-43"},
        data=json.dumps(payload),
        headers={"accept": "application/vnd.linkedin.normalized+json+2.1", "content-type": "application/json"},
    )
    if res.status_code in (401, 403):
        raise SessionError("LinkedIn rechazó la sesión al comentar")
    if res.status_code not in (200, 201):
        raise LinkedInError(f"No se pudo comentar ({res.status_code}): {res.text[:200]}")
