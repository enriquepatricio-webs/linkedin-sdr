import "server-only";

// Llama a la API Python (LinkedIn) desde el servidor del panel.
function baseUrl(): string {
  if (process.env.SDR_BASE_URL) return process.env.SDR_BASE_URL.replace(/\/$/, "");
  if (process.env.NODE_ENV === "development") return "http://127.0.0.1:8000";
  if (process.env.VERCEL_URL) return `https://${process.env.VERCEL_URL}`;
  throw new Error("Define SDR_BASE_URL");
}

export type PyResult = { ok?: boolean; error?: string; skipped?: string; [key: string]: unknown };

export async function py(path: string, body: Record<string, unknown> = {}): Promise<PyResult> {
  const headers: Record<string, string> = {
    "content-type": "application/json",
    "x-api-key": process.env.SDR_API_KEY ?? "",
  };
  if (process.env.VERCEL_AUTOMATION_BYPASS_SECRET) {
    headers["x-vercel-protection-bypass"] = process.env.VERCEL_AUTOMATION_BYPASS_SECRET;
  }
  try {
    const res = await fetch(`${baseUrl()}/api/py${path}`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
      cache: "no-store",
    });
    const text = await res.text();
    try {
      const data = JSON.parse(text) as PyResult;
      if (!res.ok && !data.error) data.error = `HTTP ${res.status}: ${JSON.stringify(data.detail ?? data)}`;
      return data;
    } catch {
      return { ok: false, error: `HTTP ${res.status}: ${text.slice(0, 200)}` };
    }
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : String(e) };
  }
}

export function describe(r: PyResult): string {
  if (r.error) return `Error: ${r.error}`;
  if (r.skipped) return `Sin acción: ${r.skipped}`;
  const { ok: _ok, ...rest } = r;
  return JSON.stringify(rest);
}
