import Link from "next/link";
import { toggleSetting } from "@/app/actions";
import { JobButton, Submit } from "@/components/forms";
import { Card, PageHeader, Stat, StatusBadge, btnPrimary, btnSecondary, btnSuccess } from "@/components/ui";
import { countEvents, getCampaigns, getSettings, localDayStart, statusCounts } from "@/lib/data";
import { EVENT, STATUS_ORDER, fmtDate } from "@/lib/labels";
import { db } from "@/lib/supabase";
import type { SdrEvent } from "@/lib/types";

async function countWhere(column: string) {
  const { count } = await db().from("sdr_leads").select("id", { count: "exact", head: true }).not(column, "is", null);
  return count ?? 0;
}

function pct(a: number, b: number) {
  return b ? `${Math.round((a / b) * 100)}%` : "—";
}

export default async function Dashboard() {
  const settings = await getSettings();
  const today = localDayStart(settings.timezone);
  const [counts, campaigns, invitesToday, messagesToday, invited, connected, contacted, replied, events, drafts] = await Promise.all([
    statusCounts(),
    getCampaigns(),
    countEvents("invite_sent", today),
    countEvents("message_sent", today),
    countWhere("invited_at"),
    countWhere("connected_at"),
    countWhere("last_outbound_at"),
    countWhere("last_inbound_at"),
    db().from("sdr_events").select("*").order("created_at", { ascending: false }).limit(12),
    db().from("sdr_messages").select("id", { count: "exact", head: true }).eq("status", "draft"),
  ]);
  const total = Object.values(counts).reduce((a, b) => a + (b ?? 0), 0);
  const activeCampaigns = campaigns.filter((c) => c.status === "active").length;
  const pendingApprovals = (counts.invite_review ?? 0) + (drafts.count ?? 0);

  const checklist = [
    { done: settings.company_pitch.trim().length > 20, label: "Describe qué hace The Coto Company", href: "/ajustes" },
    { done: settings.icp.trim().length > 10, label: "Define el cliente ideal (ICP)", href: "/ajustes" },
    { done: settings.li_session_status === "ok", label: "Conecta la sesión de LinkedIn de Enrique", href: "/ajustes#linkedin" },
    { done: activeCampaigns > 0, label: "Activa al menos una campaña", href: "/campanas" },
    { done: settings.engine_enabled, label: "Enciende el motor", href: "/" },
  ];
  const ready = checklist.every((c) => c.done);

  return (
    <>
      <PageHeader
        title="Resumen"
        subtitle={
          settings.li_profile?.name
            ? `Prospectando como ${settings.li_profile.name}${settings.li_profile.headline ? ` · ${settings.li_profile.headline}` : ""}`
            : "Sesión de LinkedIn sin comprobar"
        }
        actions={
          <>
            <form action={toggleSetting}>
              <input type="hidden" name="field" value="engine_enabled" />
              <input type="hidden" name="value" value={String(!settings.engine_enabled)} />
              <Submit className={settings.engine_enabled ? btnSecondary : btnSuccess}>
                {settings.engine_enabled ? "⏸ Pausar motor" : "▶ Encender motor"}
              </Submit>
            </form>
            <form action={toggleSetting}>
              <input type="hidden" name="field" value="autopilot" />
              <input type="hidden" name="value" value={String(!settings.autopilot)} />
              <Submit className={btnSecondary}>{settings.autopilot ? "Piloto automático: ON" : "Modo aprobación: ON"}</Submit>
            </form>
          </>
        }
      />

      {!ready && (
        <Card title="Puesta en marcha" className="mb-6 border-amber-200 bg-amber-50/40">
          <ul className="space-y-2 text-sm">
            {checklist.map((c) => (
              <li key={c.label} className="flex items-center gap-2">
                <span className={c.done ? "text-emerald-600" : "text-slate-400"}>{c.done ? "✔" : "○"}</span>
                <Link href={c.href} className={c.done ? "text-slate-500 line-through" : "font-medium text-slate-900 underline-offset-2 hover:underline"}>
                  {c.label}
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {settings.li_session_status === "invalid" && (
        <div className="mb-6 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">
          La sesión de LinkedIn ya no es válida y el motor no hará nada en LinkedIn. Entra en LinkedIn en Chrome (la extensión la
          sincroniza sola) o conéctala desde <Link href="/ajustes#linkedin" className="font-semibold underline">Ajustes</Link>.
        </div>
      )}

      <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Invitaciones hoy" value={`${invitesToday} / ${settings.daily_invite_limit}`} hint={`Semana máx. ${settings.weekly_invite_limit}`} />
        <Stat label="Mensajes hoy" value={`${messagesToday} / ${settings.daily_message_limit}`} />
        <Stat label="Aceptación" value={pct(connected, invited)} hint={`${connected} de ${invited} invitaciones`} />
        <Stat label="Respuesta" value={pct(replied, contacted)} hint={`${replied} de ${contacted} contactados`} />
        <Stat label="Pendiente de aprobar" value={pendingApprovals} href="/aprobaciones" hint="Invitaciones y mensajes" />
        <Stat label="Interesados" value={counts.interested ?? 0} href="/leads?status=interested" />
        <Stat label="Reuniones" value={counts.meeting ?? 0} href="/leads?status=meeting" />
        <Stat label="Leads totales" value={total} href="/leads" hint={`${activeCampaigns} campañas activas`} />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card title="Embudo" className="lg:col-span-1">
          <ul className="space-y-1.5">
            {STATUS_ORDER.filter((s) => counts[s]).map((s) => (
              <li key={s} className="flex items-center justify-between text-sm">
                <Link href={`/leads?status=${s}`}>
                  <StatusBadge status={s} />
                </Link>
                <span className="tabular-nums text-slate-700">{counts[s]}</span>
              </li>
            ))}
            {total === 0 && <li className="text-sm text-slate-500">Aún no hay leads. Crea una campaña y lanza la prospección.</li>}
          </ul>
        </Card>

        <Card title="Actividad reciente" className="lg:col-span-2" actions={<Link href="/actividad" className="text-xs text-slate-500 hover:text-slate-900">Ver todo →</Link>}>
          <ul className="divide-y divide-slate-100">
            {((events.data ?? []) as SdrEvent[]).map((e) => (
              <li key={e.id} className="flex gap-3 py-2 text-sm">
                <span className="w-24 shrink-0 text-xs text-slate-400">{fmtDate(e.created_at)}</span>
                <span className="shrink-0 font-medium text-slate-700">{EVENT[e.type] ?? e.type}</span>
                <span className="min-w-0 truncate text-slate-500">
                  {e.lead_id ? <Link href={`/leads/${e.lead_id}`} className="hover:underline">{e.detail}</Link> : e.detail}
                </span>
              </li>
            ))}
            {!events.data?.length && <li className="py-2 text-sm text-slate-500">Sin actividad todavía.</li>}
          </ul>
        </Card>
      </div>

      <Card title="Ejecutar ahora" className="mt-6">
        <p className="mb-4 text-sm text-slate-500">
          n8n lanza estos pasos solo según su horario. Aquí puedes forzarlos (ignoran el horario y la pausa aleatoria, pero
          respetan los límites diarios). La cualificación y la redacción con DeepSeek se ejecutan desde n8n.
        </p>
        <div className="flex flex-wrap gap-2">
          <JobButton job="prospect" label="Buscar leads" className={btnPrimary} />
          <JobButton job="invite" label="Enviar 1 invitación" className={btnSecondary} />
          <JobButton job="check-connections" label="Comprobar aceptaciones" className={btnSecondary} />
          <JobButton job="send-outbox" label="Enviar cola de mensajes" className={btnSecondary} />
          <JobButton job="sync-inbox" label="Leer bandeja de LinkedIn" className={btnSecondary} />
        </div>
      </Card>
    </>
  );
}
