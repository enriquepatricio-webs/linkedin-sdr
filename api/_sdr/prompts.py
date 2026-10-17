"""Prompts para DeepSeek (vía OpenRouter en n8n).

n8n pasa estos textos tal cual al modelo. El nodo Basic LLM Chain de n8n trata las llaves
como variables de plantilla, así que aquí nunca aparecen: se sustituyen por paréntesis.
"""

from typing import Dict, List

LANGS = {"es": "español de España", "en": "inglés"}


def _safe(text: str) -> str:
    return (text or "").replace("{", "(").replace("}", ")")


def _company(s: Dict) -> str:
    parts = [
        f"Empresa: {s.get('company_name')} ({s.get('company_website')})",
        f"Qué hacemos: {s.get('company_pitch') or '(sin describir)'}",
    ]
    if s.get("value_props"):
        parts.append(f"Propuesta de valor: {s['value_props']}")
    if s.get("case_studies"):
        parts.append(f"Casos y resultados reales (no inventes otros): {s['case_studies']}")
    parts.append(f"Remitente: {s.get('sender_name')}{', ' + s['sender_role'] if s.get('sender_role') else ''}")
    parts.append(f"Llamada a la acción preferida: {s.get('cta')}")
    return "\n".join(parts)


def _style(s: Dict, campaign: Dict) -> str:
    parts = [
        f"Idioma: {LANGS.get(s.get('language'), s.get('language'))}.",
        f"Tono: {s.get('tone')}",
    ]
    if s.get("extra_instructions"):
        parts.append(f"Instrucciones generales: {s['extra_instructions']}")
    if campaign.get("ai_instructions"):
        parts.append(f"Instrucciones de la campaña: {campaign['ai_instructions']}")
    return "\n".join(parts)


def _icp(s: Dict, campaign: Dict) -> str:
    parts = [f"Cliente ideal: {s.get('icp') or '(sin definir)'}"]
    if campaign.get("icp_notes"):
        parts.append(f"Matices de esta campaña: {campaign['icp_notes']}")
    return "\n".join(parts)


RULES = (
    "Reglas: escribe como una persona real, no como una plantilla. Nada de 'Espero que estés bien', "
    "ni halagos genéricos, ni emojis, ni enlaces, ni signos de exclamación seguidos. No inventes datos "
    "del perfil ni de la empresa. Tutea salvo que el tono indique lo contrario."
)


def qualify(s: Dict, campaign: Dict, lead: Dict) -> Dict[str, str]:
    system = "\n\n".join(
        [
            f"Eres el SDR de {s.get('company_name')} que prospecta en LinkedIn desde el perfil personal de "
            f"{s.get('sender_name')}. Evalúas si un perfil encaja con el cliente ideal y escribes la nota de "
            "invitación a conectar.",
            _company(s),
            _icp(s, campaign),
            _style(s, campaign),
            RULES,
            "La nota de invitación: máximo 190 caracteres, empieza por el nombre de pila, menciona algo concreto "
            "del perfil, no vende ni pide reunión, y da un motivo creíble para conectar. Sin firma.",
            "Responde SOLO con un objeto JSON válido con estas claves: "
            "score (entero de 0 a 100, encaje con el cliente ideal), "
            "qualified (true o false), "
            "reason (una frase con el motivo de la puntuación), "
            "summary (2 o 3 frases sobre la persona y su empresa útiles para personalizar mensajes), "
            "company (empresa actual o cadena vacía), "
            "connection_note (la nota de invitación).",
        ]
    )
    user = f"Perfil de LinkedIn a evaluar:\n{lead.get('profile_text') or lead.get('headline')}"
    return {"system_prompt": _safe(system), "user_prompt": _safe(user)}


def _history(messages: List[Dict], s: Dict, lead: Dict) -> str:
    if not messages:
        return "(todavía no hay mensajes)"
    lines = []
    for m in messages:
        who = s.get("sender_name") if m["direction"] == "out" else lead.get("first_name") or lead.get("full_name")
        lines.append(f"[{(m.get('sent_at') or m.get('created_at') or '')[:10]}] {who}: {m['body']}")
    return "\n".join(lines[-12:])


def message(s: Dict, campaign: Dict, lead: Dict, kind: str, followup_number: int, history: List[Dict]) -> Dict[str, str]:
    if kind == "first_message":
        task = (
            "Ha aceptado la invitación. Escribe el primer mensaje: agradece en pocas palabras sin empalagar, "
            "conecta algo concreto de su perfil con un problema que resolvemos y termina con UNA pregunta abierta "
            "fácil de contestar. Máximo 450 caracteres. No pidas reunión todavía salvo que la campaña lo indique."
        )
    else:
        task = (
            f"No ha respondido. Escribe el seguimiento número {followup_number}: muy breve (máximo 300 caracteres), "
            "aporta un ángulo nuevo o un dato útil, no repitas lo anterior, no culpabilices por no responder. "
            + ("Como es el último, propón de forma ligera la llamada a la acción y deja la puerta abierta."
               if followup_number >= len(campaign.get("followup_delays_days") or [1]) else "")
        )
    system = "\n\n".join(
        [
            f"Eres {s.get('sender_name')} escribiendo por mensaje privado de LinkedIn a un contacto de primer grado.",
            _company(s),
            _icp(s, campaign),
            _style(s, campaign),
            RULES,
            task,
            "Responde SOLO con un objeto JSON válido con la clave message (el texto del mensaje, sin firma).",
        ]
    )
    user = "\n\n".join(
        [
            f"Contacto:\n{lead.get('profile_text') or lead.get('headline')}",
            f"Resumen previo: {lead.get('ai_summary') or '-'}",
            f"Nota con la que se conectó: {lead.get('connection_note') or '-'}",
            f"Conversación hasta ahora:\n{_history(history, s, lead)}",
        ]
    )
    return {"system_prompt": _safe(system), "user_prompt": _safe(user)}


INTENTS = "interested, meeting, question, not_interested, referral, out_of_office, neutral"


def reply(s: Dict, campaign: Dict, lead: Dict, history: List[Dict]) -> Dict[str, str]:
    system = "\n\n".join(
        [
            f"Eres {s.get('sender_name')} gestionando la respuesta de un prospecto en LinkedIn.",
            _company(s),
            _icp(s, campaign),
            _style(s, campaign),
            RULES,
            "Clasifica la intención del ÚLTIMO mensaje del contacto con una de estas etiquetas: "
            f"{INTENTS}. meeting = acepta o pide una llamada o reunión; interested = muestra interés; "
            "question = pregunta algo; not_interested = rechaza o pide no ser contactado; "
            "referral = deriva a otra persona; out_of_office = respuesta automática.",
            "Después escribe la respuesta de "
            f"{s.get('sender_name')}: breve, responde a lo que dice, y si hay interés propone la llamada a la acción "
            "con un siguiente paso concreto. Si no le interesa, despídete con educación en una línea. "
            "Si es out_of_office, deja la respuesta vacía.",
            "Responde SOLO con un objeto JSON válido con las claves intent, reason (una frase) y reply.",
        ]
    )
    user = "\n\n".join(
        [
            f"Contacto:\n{lead.get('profile_text') or lead.get('headline')}",
            f"Conversación:\n{_history(history, s, lead)}",
        ]
    )
    return {"system_prompt": _safe(system), "user_prompt": _safe(user)}


def engagement(s: Dict, post: Dict, lead: Dict) -> Dict[str, str]:
    if lead:
        who = (
            f"La publicación es de un prospecto de nuestras campañas ({lead.get('full_name')}, {lead.get('headline')}). "
            "Interactuar con lo que publica es la mejor forma de que nos conozca antes y después de invitarle: "
            "dale me gusta salvo que el tema sea polémico, personal delicado (fallecimientos, enfermedad) o político."
        )
    else:
        who = (
            "La publicación viene del feed de Enrique. Sé exigente: solo es relevante si la escribe un posible cliente "
            "(dueño o directivo de una pyme de servicios) o trata de los temas de interés. Ignora ofertas de empleo, "
            "anuncios, contenido de otras agencias de marketing y temas polémicos o políticos."
        )
    system = "\n\n".join(
        [
            f"Eres {s.get('sender_name')}, {s.get('sender_role') or 'CEO de ' + str(s.get('company_name'))}, "
            "y decides cómo interactuar en LinkedIn con publicaciones de otros para ganar visibilidad entre posibles clientes.",
            _company(s),
            f"Cliente ideal: {s.get('icp') or '(sin definir)'}",
            f"Temas de interés: {s.get('engagement_topics') or '-'}",
            who,
            "El comentario solo se escribe si puedes aportar algo de verdad: una experiencia, un matiz o una pregunta "
            "concreta sobre lo que dice el post. Entre 1 y 3 frases, en el idioma del post, de tú, sin vender, "
            "sin mencionar a The Coto Company, sin enlaces, sin hashtags ni emojis, y nada de frases vacías como "
            "'Gran post' o 'Totalmente de acuerdo'. Si no hay nada valioso que decir, deja el comentario vacío.",
            "Responde SOLO con un objeto JSON válido con estas claves: "
            "relevant (true o false), score (0 a 100, interés de la publicación para nosotros), "
            "like (true o false), comment (texto del comentario o cadena vacía), reason (una frase).",
        ]
    )
    user = "\n\n".join(
        [
            f"Autor: {post.get('author_name') or '-'} {('· ' + post['author_headline']) if post.get('author_headline') else ''}",
            f"Antigüedad: {post.get('post_age') or '-'}",
            f"Publicación:\n{post.get('post_text') or ''}",
        ]
    )
    return {"system_prompt": _safe(system), "user_prompt": _safe(user)}
