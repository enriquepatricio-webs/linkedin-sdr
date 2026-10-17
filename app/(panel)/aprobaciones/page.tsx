import Link from "next/link";
import { approveAllInvites } from "@/app/actions";
import { DraftEditor, InviteEditor } from "@/components/editors";
import { Submit } from "@/components/forms";
import { Card, PageHeader, btnSecondary } from "@/components/ui";
import { INTENT, KIND, fmtDate } from "@/lib/labels";
import { db, must } from "@/lib/supabase";
import type { Lead, Message } from "@/lib/types";

type DraftRow = Message & { lead: Pick<Lead, "id" | "full_name" | "headline" | "status" | "intent"> | null };

export default async function Approvals() {
  const [invites, drafts, failed] = await Promise.all([
    db().from("sdr_leads").select("*").eq("status", "invite_review").order("score", { ascending: false }).limit(50),
    db()
      .from("sdr_messages")
      .select("*, lead:sdr_leads(id,full_name,headline,status,intent)")
      .eq("status", "draft")
      .order("created_at", { ascending: true })
      .limit(50),
    db()
      .from("sdr_messages")
      .select("*, lead:sdr_leads(id,full_name,headline,status,intent)")
      .eq("status", "failed")
      .order("created_at", { ascending: false })
      .limit(20),
  ]);
  const inviteRows = must(invites) as Lead[];
  const draftRows = must(drafts) as DraftRow[];
  const failedRows = must(failed) as DraftRow[];

  // Último mensaje recibido de cada lead con borrador de respuesta, para dar contexto.
  const replyLeadIds = draftRows.filter((d) => d.kind === "reply").map((d) => d.lead_id);
  const lastInbound: Record<string, Message> = {};
  if (replyLeadIds.length) {
    const rows = must(
      await db().from("sdr_messages").select("*").in("lead_id", replyLeadIds).eq("direction", "in").order("created_at", { ascending: true }),
    ) as Message[];
    for (const m of rows) lastInbound[m.lead_id] = m;
  }

  return (
    <>
      <PageHeader
        title="Aprobaciones"
        subtitle="Nada sale a LinkedIn sin pasar por aquí mientras el modo aprobación esté activo."
      />

      <Card
        title={`Invitaciones por revisar (${inviteRows.length})`}
        className="mb-6"
        actions={
          inviteRows.length > 0 && (
            <form action={approveAllInvites}>
              <Submit className={btnSecondary}>Aprobar todas</Submit>
            </form>
          )
        }
      >
        {inviteRows.length === 0 && <p className="text-sm text-slate-500">No hay invitaciones pendientes.</p>}
        <ul className="space-y-4">
          {inviteRows.map((l) => (
            <li key={l.id} className="rounded-lg border border-slate-200 p-4">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <Link href={`/leads/${l.id}`} className="font-medium text-slate-900 hover:underline">
                    {l.full_name}
                  </Link>
                  <a href={l.profile_url} target="_blank" rel="noreferrer" className="ml-2 text-xs text-sky-700 hover:underline">
                    LinkedIn ↗
                  </a>
                  <p className="text-sm text-slate-600">{l.headline}</p>
                  <p className="text-xs text-slate-500">{l.location}</p>
                </div>
                <span className="rounded-full bg-slate-900 px-2 py-0.5 text-xs font-semibold text-white">{l.score ?? "—"}/100</span>
              </div>
              {l.fit_reason && <p className="mt-2 text-sm text-slate-600">💡 {l.fit_reason}</p>}
              <InviteEditor id={l.id} note={l.connection_note} />
            </li>
          ))}
        </ul>
      </Card>

      <Card title={`Mensajes por aprobar (${draftRows.length})`} className="mb-6">
        {draftRows.length === 0 && <p className="text-sm text-slate-500">No hay mensajes pendientes.</p>}
        <ul className="space-y-4">
          {draftRows.map((m) => (
            <MessageReview key={m.id} m={m} inbound={lastInbound[m.lead_id]} />
          ))}
        </ul>
      </Card>

      {failedRows.length > 0 && (
        <Card title={`Mensajes que fallaron (${failedRows.length})`}>
          <ul className="space-y-4">
            {failedRows.map((m) => (
              <MessageReview key={m.id} m={m} />
            ))}
          </ul>
        </Card>
      )}
    </>
  );
}

function MessageReview({ m, inbound }: { m: DraftRow; inbound?: Message }) {
  return (
    <li className="rounded-lg border border-slate-200 p-4">
      <div className="mb-2 flex flex-wrap items-center gap-2 text-sm">
        <Link href={`/leads/${m.lead_id}`} className="font-medium text-slate-900 hover:underline">
          {m.lead?.full_name ?? "Lead"}
        </Link>
        <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-600">{KIND[m.kind]}</span>
        {m.lead?.intent && <span className="rounded bg-emerald-50 px-1.5 py-0.5 text-xs text-emerald-700">{INTENT[m.lead.intent] ?? m.lead.intent}</span>}
        <span className="text-xs text-slate-400">{fmtDate(m.created_at)}</span>
      </div>
      {m.lead?.headline && <p className="mb-2 text-xs text-slate-500">{m.lead.headline}</p>}
      {inbound && (
        <blockquote className="mb-3 rounded-lg bg-slate-50 p-3 text-sm text-slate-700">
          <span className="text-xs font-medium text-slate-500">Su último mensaje:</span>
          <br />
          {inbound.body}
        </blockquote>
      )}
      {m.error && <p className="mb-2 text-xs text-rose-700">Error: {m.error}</p>}
      <DraftEditor id={m.id} body={m.body} approveLabel={m.status === "failed" ? "Reintentar en la próxima ronda" : "Aprobar"} />
    </li>
  );
}
