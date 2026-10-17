import Link from "next/link";
import { notFound } from "next/navigation";
import { resetCampaignOffset, setCampaignStatus } from "@/app/actions";
import { CampaignForm } from "@/components/campaign-form";
import { JobButton, Submit } from "@/components/forms";
import { Card, PageHeader, StatusBadge, btnDanger, btnPrimary, btnSecondary, btnSuccess } from "@/components/ui";
import { statusCounts } from "@/lib/data";
import { STATUS_ORDER, fmtDate } from "@/lib/labels";
import { db } from "@/lib/supabase";
import type { Campaign } from "@/lib/types";

export default async function CampaignPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (id === "nueva") {
    return (
      <>
        <PageHeader title="Nueva campaña" actions={<Link href="/campanas" className={btnSecondary}>← Campañas</Link>} />
        <Card>
          <CampaignForm campaign={{}} />
        </Card>
      </>
    );
  }
  const campaign = (await db().from("sdr_campaigns").select("*").eq("id", id).maybeSingle()).data as Campaign | null;
  if (!campaign) notFound();
  const counts = await statusCounts(id);

  const statusButton = (status: Campaign["status"], label: string, className: string) => (
    <form action={setCampaignStatus}>
      <input type="hidden" name="id" value={id} />
      <input type="hidden" name="status" value={status} />
      <Submit className={className}>{label}</Submit>
    </form>
  );

  return (
    <>
      <PageHeader
        title={campaign.name}
        subtitle={`Desplazamiento de búsqueda: ${campaign.search_offset} · Última búsqueda: ${fmtDate(campaign.last_prospected_at)}`}
        actions={
          <>
            {campaign.status !== "active" && statusButton("active", "Activar", btnSuccess)}
            {campaign.status === "active" && statusButton("paused", "Pausar", btnSecondary)}
            {campaign.status !== "archived" && statusButton("archived", "Archivar", btnDanger)}
            <Link href="/campanas" className={btnSecondary}>
              ← Campañas
            </Link>
          </>
        }
      />
      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CampaignForm campaign={campaign} />
        </Card>
        <div className="space-y-6">
          <Card title="Leads de la campaña">
            <ul className="space-y-1.5">
              {STATUS_ORDER.filter((s) => counts[s]).map((s) => (
                <li key={s} className="flex items-center justify-between text-sm">
                  <Link href={`/leads?campaign=${id}&status=${s}`}>
                    <StatusBadge status={s} />
                  </Link>
                  <span className="tabular-nums">{counts[s]}</span>
                </li>
              ))}
              {Object.keys(counts).length === 0 && <li className="text-sm text-slate-500">Sin leads todavía.</li>}
            </ul>
          </Card>
          <Card title="Acciones">
            <div className="space-y-3">
              <JobButton job="prospect" campaignId={id} label="Buscar leads ahora" className={btnPrimary} />
              <form action={resetCampaignOffset}>
                <input type="hidden" name="id" value={id} />
                <Submit className={btnSecondary}>Reiniciar búsqueda desde el principio</Submit>
              </form>
              <p className="text-xs text-slate-500">Los perfiles que ya están en la base de datos nunca se duplican.</p>
            </div>
          </Card>
        </div>
      </div>
    </>
  );
}
