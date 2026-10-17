"use client";

import { useActionState } from "react";
import { previewSearch, saveCampaign } from "@/app/actions";
import type { Campaign } from "@/lib/types";
import { Feedback, Submit } from "./forms";
import { Field, btnPrimary, btnSecondary, input } from "./ui";

export function CampaignForm({ campaign }: { campaign: Partial<Campaign> }) {
  const [saved, saveAction] = useActionState(saveCampaign, null);
  const [preview, previewAction] = useActionState(previewSearch, null);
  const depths = campaign.network_depths ?? ["S", "O"];

  return (
    <form action={saveAction} className="space-y-8">
      {campaign.id && <input type="hidden" name="id" value={campaign.id} />}

      <section className="space-y-4">
        <h3 className="text-sm font-semibold text-slate-900">General</h3>
        <Field label="Nombre">
          <input name="name" defaultValue={campaign.name} required className={input} placeholder="CEOs de pymes en Madrid" />
        </Field>
      </section>

      <section className="space-y-4">
        <h3 className="text-sm font-semibold text-slate-900">Búsqueda en LinkedIn</h3>
        <div className="grid gap-4 md:grid-cols-2">
          <Field label="Palabras clave" hint="Igual que el buscador de LinkedIn">
            <input name="search_keywords" defaultValue={campaign.search_keywords} className={input} placeholder="marketing inmobiliaria" />
          </Field>
          <Field label="Cargo">
            <input name="search_title" defaultValue={campaign.search_title} className={input} placeholder="CEO OR fundador OR director general" />
          </Field>
          <Field label="Empresa (texto)">
            <input name="search_company" defaultValue={campaign.search_company} className={input} />
          </Field>
          <Field
            label="Ubicaciones (geoUrn)"
            hint={
              <>
                IDs separados por comas. Haz la búsqueda en LinkedIn con el filtro de ubicación y copia los números de{" "}
                <code>geoUrn=</code> en la URL. España = 105646813.
              </>
            }
          >
            <input name="search_regions" defaultValue={campaign.search_regions?.join(", ")} className={input} placeholder="105646813" />
          </Field>
          <Field label="Sectores (industry)" hint={<>IDs de <code>industry=</code> en la URL de una búsqueda de LinkedIn.</>}>
            <input name="search_industries" defaultValue={campaign.search_industries?.join(", ")} className={input} />
          </Field>
          <Field label="Grado de conexión">
            <div className="flex gap-4 pt-2 text-sm">
              {[
                ["S", "2º grado"],
                ["O", "3º y más"],
                ["F", "1º (ya conectados)"],
              ].map(([v, l]) => (
                <label key={v} className="flex items-center gap-1.5">
                  <input type="checkbox" name="network_depths" value={v} defaultChecked={depths.includes(v)} /> {l}
                </label>
              ))}
            </div>
          </Field>
          <Field label="Perfiles por búsqueda" hint="Máximo 49 por ejecución">
            <input name="search_batch" type="number" min={5} max={49} defaultValue={campaign.search_batch ?? 25} className={input} />
          </Field>
          <Field label="Colchón de leads" hint="No busca más si ya hay tantos leads esperando cualificación o invitación">
            <input name="pipeline_buffer" type="number" min={5} defaultValue={campaign.pipeline_buffer ?? 40} className={input} />
          </Field>
        </div>
        <div>
          <button formAction={previewAction} className={btnSecondary}>
            Probar búsqueda (no guarda nada)
          </button>
          {preview?.error && <p className="mt-2 text-sm text-rose-700">{preview.error}</p>}
          {preview?.people && (
            <ul className="mt-3 divide-y divide-slate-100 rounded-lg border border-slate-200 text-sm">
              {preview.people.length === 0 && <li className="p-3 text-slate-500">Sin resultados.</li>}
              {preview.people.map((p) => (
                <li key={p.profile_url} className="p-3">
                  <a href={p.profile_url} target="_blank" rel="noreferrer" className="font-medium hover:underline">
                    {p.full_name}
                  </a>
                  <div className="text-xs text-slate-500">
                    {p.headline} · {p.location}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      <section className="space-y-4">
        <h3 className="text-sm font-semibold text-slate-900">Criterio e instrucciones para la IA</h3>
        <Field label="Cliente ideal en esta campaña" hint="Se suma al ICP general de Ajustes">
          <textarea name="icp_notes" defaultValue={campaign.icp_notes} rows={3} className={input} />
        </Field>
        <Field label="Instrucciones de mensajes" hint="Ángulo, caso de éxito a mencionar, qué evitar…">
          <textarea name="ai_instructions" defaultValue={campaign.ai_instructions} rows={3} className={input} />
        </Field>
      </section>

      <section className="space-y-4">
        <h3 className="text-sm font-semibold text-slate-900">Secuencia</h3>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" name="send_connection_note" defaultChecked={campaign.send_connection_note ?? true} />
          Enviar la invitación con nota personalizada (las cuentas gratuitas tienen pocas notas al mes; si se agotan se envía sin nota)
        </label>
        <div className="grid gap-4 md:grid-cols-2">
          <Field label="Primer mensaje tras aceptar (horas)">
            <input name="first_message_delay_hours" type="number" min={0} defaultValue={campaign.first_message_delay_hours ?? 24} className={input} />
          </Field>
          <Field label="Seguimientos (días entre mensajes)" hint="Ej.: 4, 7 = seguimiento a los 4 días y otro 7 días después. Vacío = sin seguimientos">
            <input name="followup_delays_days" defaultValue={(campaign.followup_delays_days ?? [4, 7]).join(", ")} className={input} />
          </Field>
        </div>
      </section>

      <div className="flex items-center gap-3 border-t border-slate-200 pt-4">
        <Submit className={btnPrimary}>{campaign.id ? "Guardar campaña" : "Crear campaña"}</Submit>
        <Feedback state={saved} />
      </div>
    </form>
  );
}
