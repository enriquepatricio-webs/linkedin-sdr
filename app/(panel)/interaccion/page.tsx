import { saveEngagementSettings, toggleSetting } from "@/app/actions";
import { CommentEditor } from "@/components/editors";
import { ActionForm, JobButton, Submit } from "@/components/forms";
import { Card, Field, PageHeader, Stat, btnPrimary, btnSecondary, input } from "@/components/ui";
import { countEvents, getSettings, localDayStart } from "@/lib/data";
import { fmtDate } from "@/lib/labels";
import { db, must } from "@/lib/supabase";
import type { Engagement } from "@/lib/types";

function PostHeader({ e }: { e: Engagement }) {
  return (
    <div className="mb-2 flex flex-wrap items-center gap-2 text-sm">
      <a href={e.post_url} target="_blank" rel="noreferrer" className="font-medium text-slate-900 hover:underline">
        {e.author_name || "Publicación"} ↗
      </a>
      <span className={`rounded px-1.5 py-0.5 text-xs ${e.source === "lead" ? "bg-sky-50 text-sky-700" : "bg-slate-100 text-slate-600"}`}>
        {e.source === "lead" ? "Lead" : "Feed"}
      </span>
      {e.relevance != null && <span className="text-xs text-slate-500">Interés {e.relevance}/100</span>}
      <span className="text-xs text-slate-400">{e.post_age}</span>
    </div>
  );
}

export default async function Interaction() {
  const settings = await getSettings();
  const today = localDayStart(settings.timezone);
  const [drafts, recent, likesToday, commentsToday] = await Promise.all([
    db().from("sdr_engagements").select("*").eq("comment_status", "draft").order("relevance", { ascending: false }).limit(30),
    db()
      .from("sdr_engagements")
      .select("*")
      .or("liked_at.not.is.null,commented_at.not.is.null")
      .order("updated_at", { ascending: false })
      .limit(30),
    countEvents("post_liked", today),
    countEvents("post_commented", today),
  ]);
  const draftRows = must(drafts) as Engagement[];
  const recentRows = must(recent) as Engagement[];

  const toggles = [
    { field: "engagement_enabled", on: settings.engagement_enabled, label: "Interacción activa", desc: "Busca publicaciones de tus leads y de tu feed y da me gusta a las relevantes." },
    { field: "auto_comment", on: settings.auto_comment, label: "Comentarios automáticos", desc: "Si está apagado, cada comentario espera tu aprobación aquí." },
  ];

  return (
    <>
      <PageHeader
        title="Interacción"
        subtitle="Me gusta y comentarios en publicaciones de tus leads (antes y después de invitarles) y de tu feed."
        actions={<JobButton job="engage-run" label="Ejecutar ronda ahora" className={btnSecondary} />}
      />

      <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Me gusta hoy" value={`${likesToday} / ${settings.daily_like_limit}`} />
        <Stat label="Comentarios hoy" value={`${commentsToday} / ${settings.daily_comment_limit}`} />
        <Stat label="Comentarios por aprobar" value={draftRows.length} />
        <Stat label="Interacciones recientes" value={recentRows.length} />
      </div>

      <div className="mb-6 grid gap-4 md:grid-cols-2">
        {toggles.map((t) => (
          <form key={t.field} action={toggleSetting} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
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

      <Card title={`Comentarios por aprobar (${draftRows.length})`} className="mb-6">
        {draftRows.length === 0 && <p className="text-sm text-slate-500">No hay comentarios pendientes.</p>}
        <ul className="space-y-4">
          {draftRows.map((e) => (
            <li key={e.id} className="rounded-lg border border-slate-200 p-4">
              <PostHeader e={e} />
              <blockquote className="mb-3 line-clamp-6 whitespace-pre-wrap rounded-lg bg-slate-50 p-3 text-sm text-slate-700">{e.post_text}</blockquote>
              {e.reason && <p className="mb-2 text-xs text-slate-500">💡 {e.reason}</p>}
              <CommentEditor id={e.id} comment={e.comment} />
            </li>
          ))}
        </ul>
      </Card>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card title="Últimas interacciones" className="lg:col-span-2">
          <ul className="divide-y divide-slate-100">
            {recentRows.map((e) => (
              <li key={e.id} className="py-3 text-sm">
                <PostHeader e={e} />
                <p className="line-clamp-2 text-slate-600">{e.post_text}</p>
                <p className="mt-1 text-xs text-slate-500">
                  {e.liked_at && `👍 ${fmtDate(e.liked_at)}`}
                  {e.commented_at && ` · 💬 ${fmtDate(e.commented_at)}: «${e.comment}»`}
                </p>
              </li>
            ))}
            {recentRows.length === 0 && <li className="py-2 text-sm text-slate-500">Todavía no hay interacciones.</li>}
          </ul>
        </Card>
        <Card title="Ajustes">
          <ActionForm action={saveEngagementSettings} className="space-y-4">
            <Field label="Me gusta al día" hint="Recomendado 15-30">
              <input name="daily_like_limit" type="number" min={0} max={60} defaultValue={settings.daily_like_limit} className={input} />
            </Field>
            <Field label="Comentarios al día" hint="Recomendado 5-10">
              <input name="daily_comment_limit" type="number" min={0} max={20} defaultValue={settings.daily_comment_limit} className={input} />
            </Field>
            <Field label="Temas de interés" hint="La IA usa esto para decidir qué publicaciones del feed merecen interacción">
              <textarea name="engagement_topics" defaultValue={settings.engagement_topics} rows={4} className={input} />
            </Field>
            <Submit className={btnPrimary}>Guardar</Submit>
          </ActionForm>
        </Card>
      </div>
    </>
  );
}
