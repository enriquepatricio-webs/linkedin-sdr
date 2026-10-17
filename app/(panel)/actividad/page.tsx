import Link from "next/link";
import { Card, PageHeader, btnPrimary, input } from "@/components/ui";
import { EVENT, fmtDate } from "@/lib/labels";
import { db, must } from "@/lib/supabase";
import type { SdrEvent } from "@/lib/types";

export default async function Activity({ searchParams }: { searchParams: Promise<{ type?: string }> }) {
  const { type } = await searchParams;
  let q = db().from("sdr_events").select("*, lead:sdr_leads(full_name)").order("created_at", { ascending: false }).limit(300);
  if (type) q = q.eq("type", type);
  const events = must(await q) as (SdrEvent & { lead: { full_name: string } | null })[];
  return (
    <>
      <PageHeader title="Actividad" subtitle="Todo lo que ha hecho el SDR, incluidos errores de LinkedIn." />
      <form className="mb-4 flex gap-2">
        <select name="type" defaultValue={type ?? ""} className={`${input} w-auto`}>
          <option value="">Todos los tipos</option>
          {Object.entries(EVENT).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
        <button className={btnPrimary}>Filtrar</button>
      </form>
      <Card>
        <ul className="divide-y divide-slate-100">
          {events.map((e) => (
            <li key={e.id} className="grid gap-1 py-2.5 text-sm md:grid-cols-[8rem_12rem_1fr]">
              <span className="text-xs text-slate-400">{fmtDate(e.created_at)}</span>
              <span className={`font-medium ${/failed|invalid/.test(e.type) ? "text-rose-700" : "text-slate-700"}`}>{EVENT[e.type] ?? e.type}</span>
              <span className="min-w-0 break-words text-slate-600">
                {e.lead_id && (
                  <Link href={`/leads/${e.lead_id}`} className="mr-1 font-medium text-slate-900 hover:underline">
                    {e.lead?.full_name ?? "Lead"}:
                  </Link>
                )}
                {e.detail}
              </span>
            </li>
          ))}
          {events.length === 0 && <li className="py-4 text-sm text-slate-500">Sin actividad.</li>}
        </ul>
      </Card>
    </>
  );
}
