// Sesión del panel: cookie con un HMAC de la contraseña. Funciona en el middleware (Edge) y en Node.

export const SESSION_COOKIE = "sdr_session";

export async function sessionToken(): Promise<string> {
  const password = process.env.PANEL_PASSWORD ?? "";
  const secret = `${password}:${process.env.SDR_API_KEY ?? ""}`;
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode("linkedin-sdr-panel-v1"));
  return Array.from(new Uint8Array(sig), (b) => b.toString(16).padStart(2, "0")).join("");
}

export function safeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}
