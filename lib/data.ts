import "server-only";
import { db, must } from "./supabase";
import type { Campaign, LeadStatus, Settings } from "./types";

export async function getSettings(): Promise<Settings> {
  return must(await db().from("sdr_settings").select("*").eq("id", 1).single()) as Settings;
}

export async function getCampaigns(): Promise<Campaign[]> {
  return must(await db().from("sdr_campaigns").select("*").order("created_at", { ascending: false })) as Campaign[];
}

export async function statusCounts(campaignId?: string): Promise<Partial<Record<LeadStatus, number>>> {
  const counts: Partial<Record<LeadStatus, number>> = {};
  const page = 1000;
  for (let from = 0; from < 50000; from += page) {
    let q = db().from("sdr_leads").select("status").range(from, from + page - 1);
    if (campaignId) q = q.eq("campaign_id", campaignId);
    const rows = must(await q) as { status: LeadStatus }[];
    for (const r of rows) counts[r.status] = (counts[r.status] ?? 0) + 1;
    if (rows.length < page) break;
  }
  return counts;
}

export async function campaignCounts(): Promise<Record<string, Partial<Record<LeadStatus, number>>>> {
  const out: Record<string, Partial<Record<LeadStatus, number>>> = {};
  const page = 1000;
  for (let from = 0; from < 50000; from += page) {
    const rows = must(await db().from("sdr_leads").select("campaign_id,status").range(from, from + page - 1)) as {
      campaign_id: string | null;
      status: LeadStatus;
    }[];
    for (const r of rows) {
      const key = r.campaign_id ?? "none";
      out[key] ??= {};
      out[key][r.status] = (out[key][r.status] ?? 0) + 1;
    }
    if (rows.length < page) break;
  }
  return out;
}

// Medianoche de hoy en la zona horaria configurada, en UTC.
export function localDayStart(timeZone: string, daysBack = 0): string {
  const now = new Date();
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-US", { timeZone, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" })
      .formatToParts(now)
      .map((p) => [p.type, p.value]),
  );
  const asUtc = Date.UTC(+parts.year, +parts.month - 1, +parts.day, +parts.hour, +parts.minute);
  const offset = asUtc - Math.floor(now.getTime() / 60000) * 60000;
  const midnight = Date.UTC(+parts.year, +parts.month - 1, +parts.day - daysBack) - offset;
  return new Date(midnight).toISOString();
}

export async function countEvents(type: string, since: string): Promise<number> {
  const { count } = await db().from("sdr_events").select("id", { count: "exact", head: true }).eq("type", type).gte("created_at", since);
  return count ?? 0;
}

export function sum(counts: Partial<Record<LeadStatus, number>>, statuses: LeadStatus[]): number {
  return statuses.reduce((acc, s) => acc + (counts[s] ?? 0), 0);
}

// Leads que han llegado al menos a cada etapa.
export const REACHED_INVITED: LeadStatus[] = ["invited", "connected", "messaged", "replied", "interested", "meeting", "not_interested", "no_response"];
export const REACHED_CONNECTED: LeadStatus[] = ["connected", "messaged", "replied", "interested", "meeting", "not_interested"];
export const REACHED_REPLIED: LeadStatus[] = ["replied", "interested", "meeting", "not_interested"];
