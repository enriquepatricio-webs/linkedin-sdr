import Link from "next/link";
import { Card, PageHeader, btnPrimary } from "@/components/ui";
import { REACHED_CONNECTED, REACHED_INVITED, REACHED_REPLIED, campaignCounts, getCampaigns, sum } from "@/lib/data";
import { fmtDate } from "@/lib/labels";

const STATE: Record<string, string> = {
  draft: "bg-slate-100 text-slate-600",
  active: "bg-emerald-100 text-emerald-800",
  paused: "bg-amber-100 text-amber-800",
  archived: "bg-slate-100 text-slate-400",
};
const STATE_LABEL: Record<string, string> = { draft: "Borrador", active: "Activa", paused: "Pausada", archived: "Archivada" };

export default async function Campaigns() {
  const [campaigns, counts] = await Promise.all([getCampaigns(), campaignCounts()]);
  return (
    <>
      <PageHeader
        title="Campañas"
        subtitle="Cada campaña es una búsqueda de LinkedIn más las instrucciones para la IA."
        actions={
          <Link href="/campanas/nueva" className={btnPrimary}>
            Nueva campaña
          </Link>
        }
      />
      {campaigns.length === 0 && (
        <Card>
          <p className="text-sm text-slate-500">Todavía no hay campañas. Crea la primera para empezar a prospectar.</p>
        </Card>
      )}
      <div className="grid gap-4 md:grid-cols-2">
        {campaigns.map((c) => {
          const k = counts[c.id] ?? {};
          const total = Object.values(k).reduce((a, b) => a + (b ?? 0), 0);
          return (
            <Link key={c.id} href={`/campanas/${c.id}`} className="block rounded-xl border border-slate-200 bg-white p-5 shadow-sm hover:border-slate-300">
              <div className="flex items-start justify-between gap-2">
                <h2 className="font-medium text-slate-900">{c.name}</h2>
                <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATE[c.status]}`}>{STATE_LABEL[c.status]}</span>
              </div>
              <p className="mt-1 truncate text-xs text-slate-500">
                {[c.search_title, c.search_keywords].filter(Boolean).join(" · ") || "Sin filtros"}
              </p>
              <div className="mt-4 grid grid-cols-4 gap-2 text-center">
                {[
                  ["Leads", total],
                  ["Invitados", sum(k, REACHED_INVITED)],
                  ["Conectados", sum(k, REACHED_CONNECTED)],
                  ["Respuestas", sum(k, REACHED_REPLIED)],
                ].map(([label, value]) => (
                  <div key={label as string}>
                    <div className="text-lg font-semibold tabular-nums">{value}</div>
                    <div className="text-[11px] text-slate-500">{label}</div>
                  </div>
                ))}
              </div>
              <p className="mt-3 text-[11px] text-slate-400">Última búsqueda: {fmtDate(c.last_prospected_at)}</p>
            </Link>
          );
        })}
      </div>
    </>
  );
}
