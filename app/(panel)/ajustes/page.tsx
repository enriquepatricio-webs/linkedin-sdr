import { saveLinkedInSession, saveSettings, toggleSetting } from "@/app/actions";
import { ActionForm, JobButton, Submit } from "@/components/forms";
import { ExtensionConnect } from "@/components/extension-connect";
import { Card, Field, PageHeader, btnPrimary, btnSecondary, input } from "@/components/ui";
import { getSettings } from "@/lib/data";
import { fmtDate } from "@/lib/labels";

const DAYS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];

function mask(v: string | null) {
  if (!v) return "no configurada";
  return `…${v.slice(-6)}`;
}

export default async function SettingsPage() {
  const s = await getSettings();
  const toggles = [
    { field: "engine_enabled", on: s.engine_enabled, label: "Motor", desc: "Si está apagado, los flujos de n8n no hacen nada." },
    { field: "autopilot", on: s.autopilot, label: "Piloto automático", desc: "Invitaciones y mensajes de secuencia salen sin aprobación." },
    { field: "auto_reply", on: s.auto_reply, label: "Respuestas automáticas", desc: "Las respuestas a quien contesta salen sin aprobación (nunca a quien dice que no)." },
  ];
  return (
    <>
      <PageHeader title="Ajustes" subtitle={`Última modificación: ${fmtDate(s.updated_at)}`} />

      <Card title="Modo de funcionamiento" className="mb-6">
        <div className="grid gap-4 md:grid-cols-3">
          {toggles.map((t) => (
            <form key={t.field} action={toggleSetting} className="rounded-lg border border-slate-200 p-4">
              <input type="hidden" name="field" value={t.field} />
              <input type="hidden" name="value" value={String(!t.on)} />
              <div className="flex items-center justify-between">
                <span className="font-medium">{t.label}</span>
                <Submit className={`rounded-full px-3 py-1 text-xs font-semibold ${t.on ? "bg-emerald-600 text-white" : "bg-slate-200 text-slate-600"}`}>
                  {t.on ? "ACTIVADO" : "DESACTIVADO"}
                </Submit>
              </div>
              <p className="mt-2 text-xs text-slate-500">{t.desc}</p>
            </form>
          ))}
        </div>
      </Card>

      <Card title="Sesión de LinkedIn de Enrique" className="mb-6">
        <div id="linkedin" className="mb-4 flex flex-wrap items-center gap-3 text-sm">
          <span
            className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
              s.li_session_status === "ok" ? "bg-emerald-100 text-emerald-800" : s.li_session_status === "invalid" ? "bg-rose-100 text-rose-800" : "bg-slate-100 text-slate-600"
            }`}
          >
            {s.li_session_status === "ok" ? "Conectada" : s.li_session_status === "invalid" ? "Caducada" : "Sin comprobar"}
          </span>
          {s.li_profile?.name && <span>{s.li_profile.name}</span>}
          <span className="text-xs text-slate-500">Comprobada: {fmtDate(s.li_session_checked_at)}</span>
          <JobButton job="check" label="Comprobar ahora" className={btnSecondary} />
        </div>
        <ExtensionConnect />
        <p className="mt-3 text-xs text-slate-500">
          Última sincronización: {fmtDate(s.li_session_synced_at)}
          {s.li_session_source ? ` (${s.li_session_source.startsWith("extension") ? "extensión" : s.li_session_source})` : ""}
          {" · "}Última renovación de cookies en el servidor: {fmtDate(s.li_cookies_refreshed_at)}
        </p>
        <ActionForm action={saveLinkedInSession} className="mt-4 grid gap-4 md:grid-cols-2">
          <Field
            label="Proxy residencial en España (muy recomendado)"
            hint="Lo que hace WaLead: cada cuenta sale por un proxy residencial de su país, así LinkedIn ve una conexión desde España y no desde un centro de datos de EE. UU. Formato http://usuario:clave@host:puerto"
          >
            <input name="li_proxy" defaultValue={s.li_proxy ?? ""} className={input} />
          </Field>
          <div className="flex items-end">
            <Submit className={btnPrimary} pendingText="Comprobando…">
              Guardar y comprobar
            </Submit>
          </div>
          <details className="text-sm text-slate-600 md:col-span-2">
            <summary className="cursor-pointer font-medium text-slate-800">Plan B: pegar las cookies a mano</summary>
            <ol className="mt-2 list-decimal space-y-1 pl-5">
              <li>Entra en linkedin.com con la cuenta de Enrique en Chrome.</li>
              <li>Abre las herramientas de desarrollador (F12) → Aplicación → Cookies → https://www.linkedin.com.</li>
              <li>Copia el valor de <code>li_at</code> y el de <code>JSESSIONID</code> (empieza por <code>ajax:</code>).</li>
            </ol>
            <div className="mt-3 grid gap-4 md:grid-cols-2">
              <Field label="li_at" hint={`Actual: ${mask(s.li_at)}. Déjalo vacío para no cambiarla.`}>
                <input name="li_at" type="password" autoComplete="off" className={input} />
              </Field>
              <Field label="JSESSIONID" hint={`Actual: ${mask(s.jsessionid)}`}>
                <input name="jsessionid" type="password" autoComplete="off" className={input} placeholder="ajax:123456789…" />
              </Field>
            </div>
          </details>
        </ActionForm>
      </Card>

      <ActionForm action={saveSettings} className="space-y-6">
        <Card title="Empresa y propuesta (lo que la IA sabe de The Coto Company)">
          <div className="grid gap-4 md:grid-cols-2">
            <Field label="Nombre de la empresa">
              <input name="company_name" defaultValue={s.company_name} className={input} />
            </Field>
            <Field label="Web">
              <input name="company_website" defaultValue={s.company_website} className={input} />
            </Field>
            <div className="md:col-span-2">
              <Field label="Qué hacéis" hint="Servicios, a quién ayudáis y qué resultado conseguís. Cuanto más concreto, mejores mensajes.">
                <textarea name="company_pitch" defaultValue={s.company_pitch} rows={4} className={input} />
              </Field>
            </div>
            <Field label="Propuesta de valor / diferenciales">
              <textarea name="value_props" defaultValue={s.value_props} rows={4} className={input} />
            </Field>
            <Field label="Casos y resultados reales" hint="La IA sólo usará estos datos, no inventará otros.">
              <textarea name="case_studies" defaultValue={s.case_studies} rows={4} className={input} />
            </Field>
            <Field label="Llamada a la acción" hint="P. ej. una llamada de 15 minutos, o un enlace de Calendly">
              <input name="cta" defaultValue={s.cta} className={input} />
            </Field>
          </div>
        </Card>

        <Card title="Remitente, cliente ideal y estilo">
          <div className="grid gap-4 md:grid-cols-2">
            <Field label="Nombre del remitente">
              <input name="sender_name" defaultValue={s.sender_name} className={input} />
            </Field>
            <Field label="Cargo de Enrique">
              <input name="sender_role" defaultValue={s.sender_role} className={input} placeholder="Fundador de The Coto Company" />
            </Field>
            <div className="md:col-span-2">
              <Field label="Cliente ideal (ICP)" hint="Sector, tamaño, cargo, geografía, señales de que necesitan lo vuestro y quién NO encaja.">
                <textarea name="icp" defaultValue={s.icp} rows={4} className={input} />
              </Field>
            </div>
            <Field label="Tono">
              <textarea name="tone" defaultValue={s.tone} rows={3} className={input} />
            </Field>
            <Field label="Otras instrucciones para la IA">
              <textarea name="extra_instructions" defaultValue={s.extra_instructions} rows={3} className={input} />
            </Field>
            <Field label="Idioma de los mensajes">
              <select name="language" defaultValue={s.language} className={input}>
                <option value="es">Español</option>
                <option value="en">Inglés</option>
              </select>
            </Field>
            <Field label="Puntuación mínima para invitar" hint="0-100. Por debajo, el lead se descarta.">
              <input name="min_score" type="number" min={0} max={100} defaultValue={s.min_score} className={input} />
            </Field>
          </div>
        </Card>

        <Card title="Límites y horario (protegen la cuenta)">
          <div className="grid gap-4 md:grid-cols-3">
            <Field label="Invitaciones al día" hint="Recomendado 10-20">
              <input name="daily_invite_limit" type="number" min={0} max={40} defaultValue={s.daily_invite_limit} className={input} />
            </Field>
            <Field label="Invitaciones a la semana" hint="LinkedIn corta en torno a 100">
              <input name="weekly_invite_limit" type="number" min={0} max={150} defaultValue={s.weekly_invite_limit} className={input} />
            </Field>
            <Field label="Mensajes al día">
              <input name="daily_message_limit" type="number" min={0} max={100} defaultValue={s.daily_message_limit} className={input} />
            </Field>
            <Field label="Hora de inicio">
              <input name="work_start_hour" type="number" min={0} max={23} defaultValue={s.work_start_hour} className={input} />
            </Field>
            <Field label="Hora de fin">
              <input name="work_end_hour" type="number" min={1} max={24} defaultValue={s.work_end_hour} className={input} />
            </Field>
            <Field label="Zona horaria">
              <input name="timezone" defaultValue={s.timezone} className={input} />
            </Field>
            <div className="md:col-span-3">
              <Field label="Días de envío">
                <div className="flex flex-wrap gap-3 pt-1 text-sm">
                  {DAYS.map((d, i) => (
                    <label key={d} className="flex items-center gap-1.5">
                      <input type="checkbox" name="working_days" value={i + 1} defaultChecked={s.working_days.includes(i + 1)} /> {d}
                    </label>
                  ))}
                </div>
              </Field>
            </div>
          </div>
        </Card>

        <div className="sticky bottom-0 -mx-4 border-t border-slate-200 bg-slate-50/95 px-4 py-3 backdrop-blur md:-mx-8 md:px-8">
          <Submit className={btnPrimary}>Guardar ajustes</Submit>
        </div>
      </ActionForm>
    </>
  );
}
