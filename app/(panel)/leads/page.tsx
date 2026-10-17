import Link from "next/link";
import { Card, PageHeader, StatusBadge, btnPrimary, btnSecondary, input } from "@/components/ui";
import { getCampaigns } from "@/lib/data";
import { STATUS, STATUS_ORDER, fmtDate } from "@/lib/labels";
import { db, must } from "@/lib/supabase";
import type { Lead } from "@/lib/types";

const PAGE = 50;

export default async function Leads({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const sp = await searchParams;
  const page = Math.max(1, parseInt(sp.page ?? "1", 10) || 1);
  const campaigns = await getCampaigns();
  const campaignName = Object.fromEntries(campaigns.map((c) => [c.id, c.name]));

  let q = db()
    .from("sdr_leads")
    .select("id,full_name,headline,company,location,status,score,campaign_id,updated_at,profile_url", { count: "exact" })
    .order("updated_at", { ascending: false })
    .range((page - 1) * PAGE, page * PAGE - 1);
  if (sp.status) q = q.eq("status", sp.status);
  if (sp.campaign) q = q.eq("campaign_id", sp.campaign);
  if (sp.q) {
    const term = sp.q.replace(/[%,()]/g, " ");
    q = q.or(`full_name.ilike.%${term}%,headline.ilike.%${term}%,company.ilike.%${term}%`);
  }
  const res = await q;
  const leads = must(res) as Lead[];
  const total = res.count ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE));
  const link = (p: number) => `/leads?${new URLSearchParams({ ...(sp as Record<string, string>), page: String(p) })}`;

  return (
    <>
      <PageHeader title="Leads" subtitle={`${total} leads`} />
      <form className="mb-4 flex flex-wrap gap-2">
        <input name="q" defaultValue={sp.q} placeholder="Buscar nombre, cargo o empresa" className={`${input} max-w-xs`} />
        <select name="status" defaultValue={sp.status ?? ""} className={`${input} w-auto`}>
          <option value="">Todos los estados</option>
          {STATUS_ORDER.map((s) => (
            <option key={s} value={s}>
              {STATUS[s].label}
            </option>
          ))}
        </select>
        <select name="campaign" defaultValue={sp.campaign ?? ""} className={`${input} w-auto`}>
          <option value="">Todas las campañas</option>
          {campaigns.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <button className={btnPrimary}>Filtrar</button>
        <Link href="/leads" className={btnSecondary}>
          Limpiar
        </Link>
      </form>

      <Card>
        <div className="-mx-5 overflow-x-auto">
          <table className="w-full min-w-[720px] text-left text-sm">
            <thead className="border-b border-slate-200 text-xs uppercase text-slate-500">
              <tr>
                <th className="px-5 py-2 font-medium">Persona</th>
                <th className="px-3 py-2 font-medium">Campaña</th>
                <th className="px-3 py-2 font-medium">Estado</th>
                <th className="px-3 py-2 text-right font-medium">Encaje</th>
                <th className="px-5 py-2 text-right font-medium">Actualizado</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {leads.map((l) => (
                <tr key={l.id} className="hover:bg-slate-50">
                  <td className="max-w-md px-5 py-2.5">
                    <Link href={`/leads/${l.id}`} className="font-medium text-slate-900 hover:underline">
                      {l.full_name || "(sin nombre)"}
                    </Link>
                    <div className="truncate text-xs text-slate-500">{[l.headline, l.company].filter(Boolean).join(" · ")}</div>
                  </td>
                  <td className="px-3 py-2.5 text-xs text-slate-600">{l.campaign_id ? campaignName[l.campaign_id] ?? "—" : "—"}</td>
                  <td className="px-3 py-2.5">
                    <StatusBadge status={l.status} />
                  </td>
                  <td className="px-3 py-2.5 text-right tabular-nums text-slate-700">{l.score ?? "—"}</td>
                  <td className="px-5 py-2.5 text-right text-xs text-slate-500">{fmtDate(l.updated_at)}</td>
                </tr>
              ))}
              {leads.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-5 py-6 text-center text-slate-500">
                    No hay leads con estos filtros.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        {pages > 1 && (
          <div className="mt-4 flex items-center justify-between text-sm">
            {page > 1 ? <Link href={link(page - 1)} className={btnSecondary}>← Anterior</Link> : <span />}
            <span className="text-slate-500">
              Página {page} de {pages}
            </span>
            {page < pages ? <Link href={link(page + 1)} className={btnSecondary}>Siguiente →</Link> : <span />}
          </div>
        )}
      </Card>
    </>
  );
}
