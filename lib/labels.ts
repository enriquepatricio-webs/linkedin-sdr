import type { LeadStatus, Message } from "./types";

export const STATUS: Record<LeadStatus, { label: string; color: string }> = {
  new: { label: "Nuevo", color: "bg-slate-100 text-slate-700" },
  invite_review: { label: "Revisar invitación", color: "bg-amber-100 text-amber-800" },
  to_invite: { label: "Listo para invitar", color: "bg-sky-100 text-sky-800" },
  disqualified: { label: "Descartado", color: "bg-slate-100 text-slate-500" },
  invited: { label: "Invitado", color: "bg-indigo-100 text-indigo-800" },
  connected: { label: "Conectado", color: "bg-violet-100 text-violet-800" },
  messaged: { label: "En secuencia", color: "bg-blue-100 text-blue-800" },
  replied: { label: "Ha respondido", color: "bg-emerald-100 text-emerald-800" },
  interested: { label: "Interesado", color: "bg-green-100 text-green-800" },
  meeting: { label: "Reunión", color: "bg-green-600 text-white" },
  not_interested: { label: "No interesado", color: "bg-rose-100 text-rose-700" },
  no_response: { label: "Sin respuesta", color: "bg-slate-200 text-slate-600" },
  do_not_contact: { label: "No contactar", color: "bg-rose-600 text-white" },
  error: { label: "Error", color: "bg-red-100 text-red-700" },
};

export const STATUS_ORDER: LeadStatus[] = [
  "new",
  "invite_review",
  "to_invite",
  "invited",
  "connected",
  "messaged",
  "replied",
  "interested",
  "meeting",
  "not_interested",
  "no_response",
  "disqualified",
  "do_not_contact",
  "error",
];

export const KIND: Record<Message["kind"], string> = {
  first_message: "Primer mensaje",
  followup: "Seguimiento",
  reply: "Respuesta",
  manual: "Manual",
  inbound: "Recibido",
};

export const MESSAGE_STATUS: Record<Message["status"], string> = {
  draft: "Pendiente de aprobar",
  approved: "En cola",
  sent: "Enviado",
  failed: "Falló",
  rejected: "Rechazado",
  cancelled: "Cancelado",
  received: "Recibido",
};

export const EVENT: Record<string, string> = {
  prospect: "Prospección",
  qualified: "Cualificado",
  disqualified: "Descartado",
  invite_sent: "Invitación enviada",
  invite_pending: "Invitación ya pendiente",
  invite_failed: "Invitación fallida",
  invite_expired: "Invitación caducada",
  connected: "Conexión aceptada",
  draft_created: "Borrador creado",
  message_sent: "Mensaje enviado",
  message_failed: "Mensaje fallido",
  reply_received: "Respuesta recibida",
  reply_classified: "Respuesta analizada",
  no_response: "Sin respuesta",
  session_invalid: "Sesión de LinkedIn inválida",
  manual: "Acción manual",
  posts_collected: "Publicaciones recogidas",
  post_liked: "Me gusta",
  post_commented: "Comentario publicado",
  engagement_failed: "Interacción fallida",
};

export const INTENT: Record<string, string> = {
  interested: "Interesado",
  meeting: "Quiere reunión",
  question: "Pregunta",
  not_interested: "No interesado",
  referral: "Deriva a otra persona",
  out_of_office: "Fuera de la oficina",
  neutral: "Neutral",
};

export function fmtDate(iso: string | null | undefined, withTime = true): string {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("es-ES", {
    day: "2-digit",
    month: "short",
    ...(withTime ? { hour: "2-digit", minute: "2-digit" } : {}),
    timeZone: "Europe/Madrid",
  }).format(new Date(iso));
}
