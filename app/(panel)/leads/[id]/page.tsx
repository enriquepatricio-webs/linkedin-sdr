import Link from "next/link";
import { notFound } from "next/navigation";
import { composeMessage, regenerateMessage, saveLeadNotes, setLeadStatus } from "@/app/actions";
import { DraftEditor, InviteEditor } from "@/components/editors";
import { ActionForm, Submit } from "@/components/forms";
import { Card, PageHeader, StatusBadge, btnPrimary, btnSecondary, input } from "@/components/ui";
import { EVENT, INTENT, KIND, MESSAGE_STATUS, STATUS, STATUS_ORDER, fmtDate } from "@/lib/labels";
import { db, must } from "@/lib/supabase";
import type { Campaign, Lead, Message, SdrEvent } from "@/lib/types";

export default async function LeadPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const lead = (await db().from("sdr_leads").select("*").eq("id", id).maybeSingle()).data as Lead | null;
  if (!lead) notFound();
  const [messages, events, campaign] = await Promise.all([
    db().from("sdr_messages").select("*").eq("lead_id", id).order("created_at", { ascending: true }),
    db().from("sdr_events").select("*").eq("lead_id", id).order("created_at", { ascending: false }).limit(40),
    lead.campaign_id ? db().from("sdr_campaigns").select("id,name").eq("id", lead.campaign_id).maybeSingle() : Promise.resolve({ data: null }),
  ]);
  const thread = must(messages) as Message[];
  const log = must(events) as SdrEvent[];
  const camp = campaign.data as Pick<Campaign, "id" | "name"> | null;
  const canMessage = ["connected", "messaged", "replied", "interested", "meeting", "not_interested", "no_response"].includes(lead.status);

  return (
    <>
      <PageHeader
        title={lead.full_name || "Lead"}
        subtitle={
          <>
            {lead.headline}
            {lead.location && ` · ${lead.location}`}
          </>
        }
        actions={
          <>
            <a href={lead.profile_url} target="_blank" rel="noreferrer" className={btnSecondary}>
              Abrir en LinkedIn ↗
            </a>
            <Link href="/leads" className={btnSecondary}>
              ← Leads
            </Link>
          </>
        }
      />

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          {lead.status === "invite_review" || lead.status === "to_invite" ? (
            <Card title="Invitación">
              <p className="text-sm text-slate-500">Nota de conexión (máx. 200 caracteres).</p>
              <InviteEditor id={lead.id} note={lead.connection_note} />
            </Card>
          ) : null}

          <Card title="Conversación">
            {thread.length === 0 && <p className="text-sm text-slate-500">Todavía no hay mensajes.</p>}
            <ul className="space-y-3">
              {thread.map((m) =>
                m.status === "draft" || m.status === "failed" ? (
                  <li key={m.id} className="rounded-lg border border-amber-200 bg-amber-50/50 p-3">
                    <div className="mb-2 text-xs font-medium text-amber-800">
                      {KIND[m.kind]} · {MESSAGE_STATUS[m.status]} {m.error && `· ${m.error}`}
                    </div>
                    <DraftEditor id={m.id} body={m.body} approveLabel={m.status === "failed" ? "Reintentar" : "Aprobar"} />
                  </li>
                ) : (
                  <li key={m.id} className={`flex ${m.direction === "out" ? "justify-end" : "justify-start"}`}>
                    <div
                      className={`max-w-[85%] rounded-2xl px-4 py-2 text-sm ${
                        m.direction === "out" ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-900"
                      } ${["rejected", "cancelled"].includes(m.status) ? "opacity-40 line-through" : ""}`}
                    >
                      <p className="whitespace-pre-wrap">{m.body}</p>
                      <p className={`mt-1 text-[11px] ${m.direction === "out" ? "text-slate-300" : "text-slate-500"}`}>
                        {KIND[m.kind]} · {MESSAGE_STATUS[m.status]} · {fmtDate(m.sent_at ?? m.created_at)}
                        {m.intent && ` · ${INTENT[m.intent] ?? m.intent}`}
                      </p>
                    </div>
                  </li>
                ),
              )}
            </ul>

            {canMessage && (
              <ActionForm action={composeMessage} className="mt-4 space-y-2 border-t border-slate-100 pt-4">
                <input type="hidden" name="lead_id" value={lead.id} />
                <textarea name="body" rows={3} placeholder={`Escribe a ${lead.first_name || lead.full_name}…`} className={input} />
                <div className="flex flex-wrap gap-2">
                  <Submit className={btnPrimary} name="mode" value="now" pendingText="Enviando…">
                    Enviar ahora
                  </Submit>
                  <Submit className={btnSecondary} name="mode" value="queue">
                    Poner en cola
                  </Submit>
                </div>
              </ActionForm>
            )}
            {["connected", "messaged"].includes(lead.status) && (
              <form action={regenerateMessage} className="mt-3">
                <input type="hidden" name="id" value={lead.id} />
                <Submit className={btnSecondary}>Pedir a la IA el siguiente mensaje ahora</Submit>
                <p className="mt-1 text-xs text-slate-500">n8n lo redactará en su próxima ejecución.</p>
              </form>
            )}
          </Card>

          <Card title="Análisis de la IA">
            <dl className="space-y-3 text-sm">
              <div>
                <dt className="text-xs font-medium uppercase text-slate-500">Encaje</dt>
                <dd>
                  <span className="font-semibold">{lead.score ?? "—"}/100</span> {lead.fit_reason}
                </dd>
              </div>
              <div>
                <dt className="text-xs font-medium uppercase text-slate-500">Resumen</dt>
                <dd className="whitespace-pre-wrap text-slate-700">{lead.ai_summary || "—"}</dd>
              </div>
              {lead.connection_note && lead.status !== "invite_review" && lead.status !== "to_invite" && (
                <div>
                  <dt className="text-xs font-medium uppercase text-slate-500">Nota de conexión</dt>
                  <dd className="text-slate-700">{lead.connection_note}</dd>
                </div>
              )}
              <div>
                <dt className="text-xs font-medium uppercase text-slate-500">Perfil usado por la IA</dt>
                <dd>
                  <details>
                    <summary className="cursor-pointer text-slate-500">Ver texto</summary>
                    <pre className="mt-2 whitespace-pre-wrap rounded bg-slate-50 p-3 text-xs text-slate-700">{lead.profile_text}</pre>
                  </details>
                </dd>
              </div>
            </dl>
          </Card>
        </div>

        <div className="space-y-6">
          <Card title="Estado">
            <div className="mb-3">
              <StatusBadge status={lead.status} />
              {lead.error && <p className="mt-2 text-xs text-rose-700">{lead.error}</p>}
            </div>
            <form action={setLeadStatus} className="flex gap-2">
              <input type="hidden" name="id" value={lead.id} />
              <select name="status" defaultValue={lead.status} className={input}>
                {STATUS_ORDER.map((s) => (
                  <option key={s} value={s}>
                    {STATUS[s].label}
                  </option>
                ))}
              </select>
              <Submit className={btnSecondary}>Cambiar</Submit>
            </form>
            <dl className="mt-4 grid grid-cols-2 gap-x-3 gap-y-2 text-xs">
              <dt className="text-slate-500">Campaña</dt>
              <dd>{camp ? <Link href={`/campanas/${camp.id}`} className="hover:underline">{camp.name}</Link> : "—"}</dd>
              <dt className="text-slate-500">Empresa</dt>
              <dd>{lead.company || "—"}</dd>
              <dt className="text-slate-500">Invitado</dt>
              <dd>{fmtDate(lead.invited_at)}</dd>
              <dt className="text-slate-500">Conectado</dt>
              <dd>{fmtDate(lead.connected_at)}</dd>
              <dt className="text-slate-500">Seguimientos</dt>
              <dd>{lead.followups_sent}</dd>
              <dt className="text-slate-500">Próxima acción</dt>
              <dd>{fmtDate(lead.next_action_at)}</dd>
              <dt className="text-slate-500">Intención</dt>
              <dd>{lead.intent ? INTENT[lead.intent] ?? lead.intent : "—"}</dd>
            </dl>
          </Card>

          <Card title="Notas">
            <form action={saveLeadNotes} className="space-y-2">
              <input type="hidden" name="id" value={lead.id} />
              <textarea name="notes" defaultValue={lead.notes} rows={4} className={input} />
              <Submit className={btnSecondary}>Guardar notas</Submit>
            </form>
          </Card>

          <Card title="Historial">
            <ul className="space-y-2 text-xs">
              {log.map((e) => (
                <li key={e.id}>
                  <span className="text-slate-400">{fmtDate(e.created_at)}</span>{" "}
                  <span className="font-medium text-slate-700">{EVENT[e.type] ?? e.type}</span>
                  {e.detail && <p className="text-slate-500">{e.detail}</p>}
                </li>
              ))}
              {log.length === 0 && <li className="text-slate-500">Sin eventos.</li>}
            </ul>
          </Card>
        </div>
      </div>
    </>
  );
}
