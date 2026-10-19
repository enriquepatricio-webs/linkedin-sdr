"use server";

import { randomBytes } from "node:crypto";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { db, must } from "@/lib/supabase";
import { describe, py } from "@/lib/py";
import { SESSION_COOKIE, safeEqual, sessionToken } from "@/lib/auth";
import type { LeadStatus } from "@/lib/types";

export type ActionState = { message: string; ok: boolean } | null;

const str = (fd: FormData, k: string) => String(fd.get(k) ?? "").trim();
const int = (fd: FormData, k: string, fallback: number) => {
  const n = parseInt(str(fd, k), 10);
  return Number.isFinite(n) ? n : fallback;
};
const list = (fd: FormData, k: string) =>
  str(fd, k)
    .split(/[\s,;]+/)
    .map((x) => x.trim())
    .filter(Boolean);

async function logManual(detail: string, lead_id: string | null = null) {
  await db().from("sdr_events").insert({ type: "manual", detail, lead_id });
}

function touch() {
  revalidatePath("/", "layout");
}

// ---------- acceso ----------

export async function login(_: ActionState, fd: FormData): Promise<ActionState> {
  const password = str(fd, "password");
  if (!process.env.PANEL_PASSWORD || !safeEqual(password, process.env.PANEL_PASSWORD)) {
    return { ok: false, message: "Contraseña incorrecta" };
  }
  (await cookies()).set(SESSION_COOKIE, await sessionToken(), {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 24 * 30,
  });
  redirect("/");
}

export async function logout() {
  (await cookies()).delete(SESSION_COOKIE);
  redirect("/login");
}

// ---------- ajustes ----------

export async function toggleSetting(fd: FormData) {
  const field = str(fd, "field");
  if (!["engine_enabled", "autopilot", "auto_reply", "engagement_enabled", "auto_comment"].includes(field)) return;
  must(await db().from("sdr_settings").update({ [field]: str(fd, "value") === "true", updated_at: new Date().toISOString() }).eq("id", 1));
  await logManual(`${field} = ${str(fd, "value")}`);
  touch();
}

export async function saveSettings(_: ActionState, fd: FormData): Promise<ActionState> {
  const values = {
    company_name: str(fd, "company_name"),
    company_website: str(fd, "company_website"),
    company_pitch: str(fd, "company_pitch"),
    value_props: str(fd, "value_props"),
    case_studies: str(fd, "case_studies"),
    cta: str(fd, "cta"),
    sender_name: str(fd, "sender_name"),
    sender_role: str(fd, "sender_role"),
    icp: str(fd, "icp"),
    tone: str(fd, "tone"),
    language: str(fd, "language") || "es",
    extra_instructions: str(fd, "extra_instructions"),
    min_score: int(fd, "min_score", 60),
    daily_invite_limit: int(fd, "daily_invite_limit", 15),
    weekly_invite_limit: int(fd, "weekly_invite_limit", 80),
    daily_message_limit: int(fd, "daily_message_limit", 30),
    working_days: fd.getAll("working_days").map((d) => parseInt(String(d), 10)),
    work_start_hour: int(fd, "work_start_hour", 9),
    work_end_hour: int(fd, "work_end_hour", 19),
    timezone: str(fd, "timezone") || "Europe/Madrid",
    updated_at: new Date().toISOString(),
  };
  const { error } = await db().from("sdr_settings").update(values).eq("id", 1);
  if (error) return { ok: false, message: error.message };
  touch();
  return { ok: true, message: "Ajustes guardados" };
}

export async function saveLinkedInSession(_: ActionState, fd: FormData): Promise<ActionState> {
  const values: Record<string, unknown> = { li_proxy: str(fd, "li_proxy") || null, updated_at: new Date().toISOString() };
  if (str(fd, "li_at")) values.li_at = str(fd, "li_at");
  if (str(fd, "jsessionid")) values.jsessionid = str(fd, "jsessionid");
  if (values.li_at || values.jsessionid) Object.assign(values, { li_session_status: "unknown", li_session_source: "manual" });
  const { error } = await db().from("sdr_settings").update(values).eq("id", 1);
  if (error) return { ok: false, message: error.message };
  const r = await py("/linkedin/check");
  touch();
  const proxy = describeProxy(r.proxy as ProxyInfo | null | undefined);
  if (r.ok) {
    const p = r.profile as { name?: string } | undefined;
    return { ok: true, message: `Sesión válida: conectado como ${p?.name ?? "?"}.${proxy}` };
  }
  return { ok: false, message: `Guardado, pero la sesión no funciona: ${r.error}${proxy}` };
}

type ProxyInfo = { ip?: string; city?: string; region?: string; country?: string; org?: string };

// Lo que ve LinkedIn: si el proxy no sale por España se avisa, que es lo que hace caer la sesión.
function describeProxy(p: ProxyInfo | null | undefined): string {
  if (!p) return "";
  const where = [p.city, p.region, p.country].filter(Boolean).join(", ");
  const warn = p.country && p.country !== "ES" ? " ⚠️ No sale por España: LinkedIn puede volver a cerrar la sesión." : "";
  return ` LinkedIn te ve desde ${p.ip ?? "?"} (${where}${p.org ? ` · ${p.org}` : ""}).${warn}`;
}

// Clave propia de la extensión de Chrome (no es SDR_API_KEY). Se crea la primera vez que se conecta.
export async function extensionToken(): Promise<{ ok: boolean; token?: string; message?: string }> {
  const { data, error } = await db().from("sdr_settings").select("extension_token").eq("id", 1).single();
  if (error) return { ok: false, message: error.message };
  if (data?.extension_token) return { ok: true, token: data.extension_token };
  const token = randomBytes(32).toString("hex");
  const { error: e2 } = await db().from("sdr_settings").update({ extension_token: token }).eq("id", 1);
  if (e2) return { ok: false, message: e2.message };
  return { ok: true, token };
}

export async function refreshPanel() {
  touch();
}

// ---------- trabajos manuales ----------

const JOBS: Record<string, string> = {
  prospect: "/jobs/prospect",
  invite: "/jobs/invite",
  "check-connections": "/jobs/check-connections",
  "send-outbox": "/jobs/send-outbox",
  "sync-inbox": "/jobs/sync-inbox",
  "engage-run": "/jobs/engage-run",
  check: "/linkedin/check",
};

export async function runJob(_: ActionState, fd: FormData): Promise<ActionState> {
  const path = JOBS[str(fd, "job")];
  if (!path) return { ok: false, message: "Trabajo desconocido" };
  const body: Record<string, unknown> = { force: true };
  if (str(fd, "campaign_id")) body.campaign_id = str(fd, "campaign_id");
  const r = await py(path, body);
  touch();
  return { ok: !r.error, message: describe(r) };
}

// ---------- campañas ----------

export async function saveCampaign(_: ActionState, fd: FormData): Promise<ActionState> {
  const id = str(fd, "id");
  const values = {
    name: str(fd, "name") || "Campaña sin nombre",
    search_keywords: str(fd, "search_keywords"),
    search_title: str(fd, "search_title"),
    search_company: str(fd, "search_company"),
    search_regions: list(fd, "search_regions"),
    search_industries: list(fd, "search_industries"),
    network_depths: fd.getAll("network_depths").map(String),
    search_batch: Math.min(int(fd, "search_batch", 25), 49),
    pipeline_buffer: int(fd, "pipeline_buffer", 40),
    icp_notes: str(fd, "icp_notes"),
    ai_instructions: str(fd, "ai_instructions"),
    send_connection_note: fd.get("send_connection_note") === "on",
    first_message_delay_hours: int(fd, "first_message_delay_hours", 1),
    followup_delays_days: list(fd, "followup_delays_days")
      .map((x) => parseInt(x, 10))
      .filter((n) => Number.isFinite(n) && n > 0),
    updated_at: new Date().toISOString(),
  };
  if (id) {
    const { error } = await db().from("sdr_campaigns").update(values).eq("id", id);
    if (error) return { ok: false, message: error.message };
    touch();
    return { ok: true, message: "Campaña guardada" };
  }
  const { data, error } = await db().from("sdr_campaigns").insert(values).select("id").single();
  if (error) return { ok: false, message: error.message };
  touch();
  redirect(`/campanas/${data.id}`);
}

export async function setCampaignStatus(fd: FormData) {
  must(await db().from("sdr_campaigns").update({ status: str(fd, "status"), updated_at: new Date().toISOString() }).eq("id", str(fd, "id")));
  touch();
}

export async function resetCampaignOffset(fd: FormData) {
  must(await db().from("sdr_campaigns").update({ search_offset: 0, updated_at: new Date().toISOString() }).eq("id", str(fd, "id")));
  touch();
}

export type PreviewState = { error?: string; people?: { full_name: string; headline: string; location: string; profile_url: string }[] } | null;

export async function previewSearch(_: PreviewState, fd: FormData): Promise<PreviewState> {
  const r = await py("/linkedin/search-preview", {
    search_keywords: str(fd, "search_keywords"),
    search_title: str(fd, "search_title"),
    search_company: str(fd, "search_company"),
    search_regions: list(fd, "search_regions"),
    search_industries: list(fd, "search_industries"),
    network_depths: fd.getAll("network_depths").map(String),
  });
  if (r.error) return { error: r.error };
  return { people: (r.people as NonNullable<PreviewState>["people"]) ?? [] };
}

// ---------- leads ----------

async function updateLead(id: string, values: Record<string, unknown>) {
  must(await db().from("sdr_leads").update({ ...values, updated_at: new Date().toISOString() }).eq("id", id));
}

export async function approveInvite(fd: FormData) {
  const id = str(fd, "id");
  await updateLead(id, { status: "to_invite", connection_note: str(fd, "connection_note").slice(0, 200) });
  touch();
}

export async function rejectInvite(fd: FormData) {
  await updateLead(str(fd, "id"), { status: "disqualified" });
  touch();
}

export async function approveAllInvites() {
  must(await db().from("sdr_leads").update({ status: "to_invite", updated_at: new Date().toISOString() }).eq("status", "invite_review"));
  await logManual("Aprobadas todas las invitaciones pendientes");
  touch();
}

export async function inviteNow(_: ActionState, fd: FormData): Promise<ActionState> {
  const id = str(fd, "id");
  if (fd.has("connection_note")) await updateLead(id, { connection_note: str(fd, "connection_note").slice(0, 200) });
  const r = await py("/jobs/invite", { lead_id: id });
  touch();
  return { ok: !r.error && !r.skipped, message: r.invited ? `Invitación enviada a ${r.invited}` : describe(r) };
}

export async function setLeadStatus(fd: FormData) {
  const id = str(fd, "id");
  const status = str(fd, "status") as LeadStatus;
  const values: Record<string, unknown> = { status };
  if (["do_not_contact", "not_interested", "meeting", "disqualified"].includes(status)) values.next_action_at = null;
  await updateLead(id, values);
  if (status === "do_not_contact" || status === "not_interested") {
    await db().from("sdr_messages").update({ status: "cancelled" }).eq("lead_id", id).in("status", ["draft", "approved"]);
  }
  await logManual(`Estado cambiado a ${status}`, id);
  touch();
}

export async function saveLeadNotes(fd: FormData) {
  await updateLead(str(fd, "id"), { notes: str(fd, "notes") });
  touch();
}

export async function regenerateMessage(fd: FormData) {
  const id = str(fd, "id");
  await db().from("sdr_messages").update({ status: "rejected" }).eq("lead_id", id).eq("status", "draft").in("kind", ["first_message", "followup"]);
  await updateLead(id, { next_action_at: new Date().toISOString(), locked_until: null });
  await logManual("Pedido nuevo mensaje a la IA", id);
  touch();
}

// ---------- mensajes ----------

export async function approveMessage(fd: FormData) {
  must(await db().from("sdr_messages").update({ status: "approved", body: str(fd, "body") }).eq("id", str(fd, "id")));
  touch();
}

export async function rejectMessage(fd: FormData) {
  must(await db().from("sdr_messages").update({ status: "rejected" }).eq("id", str(fd, "id")));
  touch();
}

export async function sendMessageNow(_: ActionState, fd: FormData): Promise<ActionState> {
  const id = str(fd, "id");
  if (fd.has("body")) must(await db().from("sdr_messages").update({ body: str(fd, "body") }).eq("id", id));
  const r = await py("/jobs/send-outbox", { message_id: id });
  touch();
  const results = (r.results as { sent?: boolean; error?: string; cancelled?: boolean }[] | undefined) ?? [];
  if (results[0]?.sent) return { ok: true, message: "Mensaje enviado" };
  if (results[0]?.cancelled) return { ok: false, message: "Cancelado: el estado del lead no permite este mensaje" };
  return { ok: false, message: results[0]?.error ?? describe(r) };
}

export async function composeMessage(_: ActionState, fd: FormData): Promise<ActionState> {
  const lead_id = str(fd, "lead_id");
  const body = str(fd, "body");
  if (!body) return { ok: false, message: "Escribe un mensaje" };
  const { data, error } = await db()
    .from("sdr_messages")
    .insert({ lead_id, direction: "out", kind: "manual", body, status: "approved" })
    .select("id")
    .single();
  if (error) return { ok: false, message: error.message };
  if (str(fd, "mode") === "queue") {
    touch();
    return { ok: true, message: "Mensaje en cola: saldrá en la próxima ronda de envío" };
  }
  const send = new FormData();
  send.set("id", data.id);
  return sendMessageNow(null, send);
}

// ---------- interacción con publicaciones ----------

export async function saveEngagementSettings(_: ActionState, fd: FormData): Promise<ActionState> {
  const { error } = await db()
    .from("sdr_settings")
    .update({
      daily_like_limit: int(fd, "daily_like_limit", 25),
      daily_comment_limit: int(fd, "daily_comment_limit", 8),
      engagement_topics: str(fd, "engagement_topics"),
      updated_at: new Date().toISOString(),
    })
    .eq("id", 1);
  if (error) return { ok: false, message: error.message };
  touch();
  return { ok: true, message: "Guardado" };
}

export async function approveComment(fd: FormData) {
  must(
    await db()
      .from("sdr_engagements")
      .update({ comment: str(fd, "comment"), comment_status: "approved", updated_at: new Date().toISOString() })
      .eq("id", str(fd, "id")),
  );
  touch();
}

export async function rejectComment(fd: FormData) {
  const id = str(fd, "id");
  const row = must(await db().from("sdr_engagements").select("want_like,liked_at").eq("id", id).single()) as {
    want_like: boolean;
    liked_at: string | null;
  };
  const likePending = row.want_like && !row.liked_at;
  must(
    await db()
      .from("sdr_engagements")
      .update({ comment_status: "rejected", status: likePending ? "ready" : "done", updated_at: new Date().toISOString() })
      .eq("id", id),
  );
  touch();
}

export async function commentNow(_: ActionState, fd: FormData): Promise<ActionState> {
  const id = str(fd, "id");
  must(
    await db()
      .from("sdr_engagements")
      .update({ comment: str(fd, "comment"), comment_status: "approved", updated_at: new Date().toISOString() })
      .eq("id", id),
  );
  const r = await py("/jobs/engage-run", { engagement_id: id });
  touch();
  if (r.commented) return { ok: true, message: "Comentario publicado" };
  return { ok: false, message: (r.errors as string[] | undefined)?.[0] ?? describe(r) };
}
