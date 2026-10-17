"use client";

import { useEffect, useState } from "react";
import { extensionToken, refreshPanel } from "@/app/actions";
import { btnPrimary, btnSecondary } from "./ui";

// ID fijo de la extensión (sale de la clave pública de extension/manifest.json).
export const EXTENSION_ID = "bpljabfhjpbkncjipleeakknpaccfiff";

type Reply = { ok: boolean; error?: string; version?: string; paired?: boolean; status?: string; profile?: string } | null;
type Runtime = { sendMessage: (id: string, msg: unknown, cb: (r: Reply) => void) => void; lastError?: { message?: string } };

// Igual que WaLead: la web habla con la extensión por chrome.runtime (externally_connectable).
function ask(msg: unknown): Promise<Reply> {
  const rt = (window as unknown as { chrome?: { runtime?: Runtime } }).chrome?.runtime;
  if (!rt?.sendMessage) return Promise.resolve(null);
  return new Promise((resolve) => {
    try {
      rt.sendMessage(EXTENSION_ID, msg, (r) => resolve(rt.lastError ? null : r ?? null));
    } catch {
      resolve(null);
    }
  });
}

const STATUS: Record<string, string> = {
  ok: "conectada y sincronizando",
  logged_out: "instalada, pero no hay sesión de LinkedIn abierta en este navegador",
  invalid: "instalada, pero LinkedIn rechaza la sesión",
  error: "instalada, con error al contactar con el SDR",
  unpaired: "instalada, falta conectarla",
};

export function ExtensionConnect() {
  const [ext, setExt] = useState<Reply | "checking">("checking");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null);
  const [token, setToken] = useState<string | null>(null);

  useEffect(() => {
    ask({ action: "get_version" }).then(setExt);
  }, []);

  async function connect() {
    setBusy(true);
    setResult(null);
    try {
      const t = await extensionToken();
      if (!t.ok || !t.token) return setResult({ ok: false, message: t.message ?? "No se pudo crear la clave" });
      const r = await ask({ action: "pair", token: t.token });
      if (!r) return setResult({ ok: false, message: "No se encuentra la extensión. Recarga la página tras instalarla." });
      setResult(
        r.ok
          ? { ok: true, message: `Conectada${r.profile ? ` como ${r.profile}` : ""}. La sesión se mantendrá sola mientras Chrome tenga LinkedIn abierto.` }
          : { ok: false, message: r.error ?? "Error" },
      );
      setExt(await ask({ action: "get_version" }));
      await refreshPanel();
    } finally {
      setBusy(false);
    }
  }

  async function showToken() {
    const t = await extensionToken();
    setToken(t.token ?? t.message ?? "");
  }

  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm">
      <p className="font-medium text-slate-900">Conexión automática con la extensión de Chrome (como WaLead)</p>
      <p className="mt-1 text-slate-600">
        La extensión lee la sesión de LinkedIn de tu navegador (todas las cookies y el navegador exacto) y se la pasa al SDR cada vez que cambia.
        Ya no hay que copiar cookies: si LinkedIn te pide entrar de nuevo, entras en Chrome como siempre y el SDR la recibe en segundos.
      </p>
      <p className="mt-2">
        Estado:{" "}
        <strong>
          {ext === "checking" ? "buscando la extensión…" : ext ? `v${ext.version}, ${STATUS[ext.status ?? ""] ?? ext.status}` : "no instalada en este navegador"}
        </strong>
      </p>
      {ext === null && (
        <ol className="mt-2 list-decimal space-y-1 pl-5 text-slate-600">
          <li>
            Descarga <a className="font-medium text-sky-700 underline" href="/coto-sdr-extension.zip">coto-sdr-extension.zip</a> y descomprímelo.
          </li>
          <li>
            En Chrome abre <code>chrome://extensions</code>, activa «Modo desarrollador» y pulsa «Cargar descomprimida» eligiendo la carpeta.
          </li>
          <li>Recarga esta página y pulsa «Conectar con la extensión».</li>
        </ol>
      )}
      <div className="mt-3 flex flex-wrap gap-2">
        <button type="button" onClick={connect} disabled={busy || !ext || ext === "checking"} className={btnPrimary}>
          {busy ? "Conectando… (completa el login si se abre LinkedIn)" : "Conectar con la extensión"}
        </button>
        <button type="button" onClick={showToken} className={btnSecondary}>
          Ver clave para conectar a mano
        </button>
      </div>
      {token && (
        <p className="mt-2 break-all text-xs text-slate-600">
          Pégala en el popup de la extensión → «Conectar a mano»: <code>{token}</code>
        </p>
      )}
      {result && <p className={`mt-2 text-sm ${result.ok ? "text-emerald-700" : "text-rose-700"}`}>{result.message}</p>}
    </div>
  );
}
