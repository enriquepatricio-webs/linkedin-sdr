import { Nav } from "@/components/nav";
import { db } from "@/lib/supabase";
import { logout } from "@/app/actions";

export const dynamic = "force-dynamic";

async function pendingApprovals(): Promise<number> {
  const [invites, drafts, comments] = await Promise.all([
    db().from("sdr_leads").select("id", { count: "exact", head: true }).eq("status", "invite_review"),
    db().from("sdr_messages").select("id", { count: "exact", head: true }).eq("status", "draft"),
    db().from("sdr_engagements").select("id", { count: "exact", head: true }).eq("comment_status", "draft"),
  ]);
  return (invites.count ?? 0) + (drafts.count ?? 0) + (comments.count ?? 0);
}

export default async function PanelLayout({ children }: { children: React.ReactNode }) {
  const pending = await pendingApprovals().catch(() => 0);
  return (
    <div className="mx-auto flex min-h-screen max-w-7xl flex-col md:flex-row">
      <aside className="border-b border-slate-200 p-4 md:sticky md:top-0 md:h-screen md:w-56 md:shrink-0 md:border-b-0 md:border-r">
        <div className="mb-4 px-3">
          <div className="text-sm font-semibold text-slate-900">LinkedIn SDR</div>
          <div className="text-xs text-slate-500">The Coto Company · Enrique</div>
        </div>
        <Nav pending={pending} />
        <form action={logout} className="mt-4 hidden px-3 md:block">
          <button className="text-xs text-slate-500 hover:text-slate-900">Cerrar sesión</button>
        </form>
      </aside>
      <main className="min-w-0 flex-1 p-4 md:p-8">{children}</main>
    </div>
  );
}
