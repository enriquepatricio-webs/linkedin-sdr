-- Sesión de LinkedIn sincronizada desde el navegador de Enrique con la extensión (como WaLead).
-- La extensión manda todas las cookies de linkedin.com y el user agent del navegador, de modo
-- que el servidor se presenta como ese mismo navegador (bcookie, bscookie, lidc...) y no sólo
-- con li_at, que es lo que LinkedIn detecta como sesión robada.

alter table public.sdr_settings
  add column if not exists li_cookies jsonb,
  add column if not exists li_user_agent text,
  add column if not exists li_accept_language text,
  add column if not exists li_session_source text,
  add column if not exists li_session_synced_at timestamptz,
  add column if not exists extension_token text,
  -- cookies que LinkedIn ha renovado en respuestas al servidor (la sesión vive sin el ordenador de Enrique)
  add column if not exists li_cookies_refreshed_at timestamptz;
