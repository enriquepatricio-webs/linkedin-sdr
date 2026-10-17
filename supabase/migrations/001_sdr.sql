-- SDR de LinkedIn para The Coto Company.
-- Todas las tablas llevan el prefijo sdr_ para convivir con el resto del proyecto.
-- RLS activado y sin políticas: sólo la service role (panel y API en Vercel) puede leer o escribir.

create extension if not exists pgcrypto;

-- Ajustes globales: una sola fila (id = 1).
create table if not exists public.sdr_settings (
  id int primary key default 1 check (id = 1),
  engine_enabled boolean not null default false,
  autopilot boolean not null default false,
  auto_reply boolean not null default false,

  company_name text not null default 'The Coto Company',
  company_website text not null default 'https://thecotocompany.com',
  company_pitch text not null default '',
  value_props text not null default '',
  case_studies text not null default '',
  cta text not null default 'Una llamada de 15 minutos para ver si encaja',

  sender_name text not null default 'Enrique',
  sender_role text not null default '',
  icp text not null default '',
  tone text not null default 'Cercano, directo y profesional. Frases cortas. Nada de lenguaje de vendedor ni emojis.',
  language text not null default 'es',
  extra_instructions text not null default '',
  min_score int not null default 60,

  daily_invite_limit int not null default 15,
  weekly_invite_limit int not null default 80,
  daily_message_limit int not null default 30,
  working_days int[] not null default '{1,2,3,4,5}',
  work_start_hour int not null default 9,
  work_end_hour int not null default 19,
  timezone text not null default 'Europe/Madrid',

  li_at text,
  jsessionid text,
  li_proxy text,
  li_session_status text not null default 'unknown',
  li_session_checked_at timestamptz,
  li_profile jsonb,

  updated_at timestamptz not null default now()
);

insert into public.sdr_settings (id) values (1) on conflict (id) do nothing;

create table if not exists public.sdr_campaigns (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  status text not null default 'draft' check (status in ('draft', 'active', 'paused', 'archived')),

  search_keywords text not null default '',
  search_title text not null default '',
  search_company text not null default '',
  search_regions text[] not null default '{}',
  search_industries text[] not null default '{}',
  network_depths text[] not null default '{S,O}',
  search_batch int not null default 25,
  search_offset int not null default 0,
  pipeline_buffer int not null default 40,

  icp_notes text not null default '',
  ai_instructions text not null default '',
  send_connection_note boolean not null default true,
  first_message_delay_hours int not null default 24,
  followup_delays_days int[] not null default '{4,7}',

  last_prospected_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- Estados del lead:
--   new -> invite_review (pendiente de aprobar) | to_invite | disqualified
--   to_invite -> invited -> connected -> messaged -> replied -> interested | meeting | not_interested
--   messaged sin respuesta tras los seguimientos -> no_response
--   do_not_contact, error
create table if not exists public.sdr_leads (
  id uuid primary key default gen_random_uuid(),
  campaign_id uuid references public.sdr_campaigns(id) on delete set null,
  urn_id text not null unique,
  public_id text,
  full_name text not null default '',
  first_name text not null default '',
  headline text not null default '',
  location text not null default '',
  company text not null default '',
  profile_url text not null default '',
  distance text,
  profile jsonb,
  profile_text text not null default '',

  status text not null default 'new' check (status in (
    'new', 'invite_review', 'to_invite', 'disqualified', 'invited', 'connected',
    'messaged', 'replied', 'interested', 'meeting', 'not_interested',
    'no_response', 'do_not_contact', 'error'
  )),
  score int,
  fit_reason text not null default '',
  ai_summary text not null default '',
  connection_note text not null default '',
  intent text,

  invited_at timestamptz,
  connected_at timestamptz,
  last_checked_at timestamptz,
  inbox_synced_at timestamptz,
  last_outbound_at timestamptz,
  last_inbound_at timestamptz,
  followups_sent int not null default 0,
  next_action_at timestamptz,
  locked_until timestamptz,
  conversation_urn_id text,
  notes text not null default '',
  error text,

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists sdr_leads_status_idx on public.sdr_leads (status, created_at);
create index if not exists sdr_leads_campaign_idx on public.sdr_leads (campaign_id, status);
create index if not exists sdr_leads_next_action_idx on public.sdr_leads (next_action_at) where next_action_at is not null;

-- Mensajes del hilo. direction: out (de Enrique) | in (del lead).
-- status de los salientes: draft (espera aprobación) -> approved (en cola) -> sent | failed; rejected; cancelled.
create table if not exists public.sdr_messages (
  id uuid primary key default gen_random_uuid(),
  lead_id uuid not null references public.sdr_leads(id) on delete cascade,
  direction text not null check (direction in ('out', 'in')),
  kind text not null default 'manual' check (kind in ('first_message', 'followup', 'reply', 'manual', 'inbound')),
  body text not null,
  status text not null default 'draft' check (status in ('draft', 'approved', 'sent', 'failed', 'rejected', 'cancelled', 'received')),
  ai_generated boolean not null default false,
  intent text,
  linkedin_event_urn text unique,
  error text,
  sent_at timestamptz,
  created_at timestamptz not null default now()
);

create index if not exists sdr_messages_lead_idx on public.sdr_messages (lead_id, created_at);
create index if not exists sdr_messages_status_idx on public.sdr_messages (status, created_at);

-- Registro de actividad. Los contadores diarios (invitaciones, mensajes) se calculan desde aquí.
-- updated_at lo fija el código que escribe (API y panel).
create table if not exists public.sdr_events (
  id bigint generated always as identity primary key,
  type text not null,
  lead_id uuid references public.sdr_leads(id) on delete cascade,
  campaign_id uuid references public.sdr_campaigns(id) on delete set null,
  detail text not null default '',
  data jsonb,
  created_at timestamptz not null default now()
);

create index if not exists sdr_events_type_idx on public.sdr_events (type, created_at desc);
create index if not exists sdr_events_created_idx on public.sdr_events (created_at desc);

alter table public.sdr_settings enable row level security;
alter table public.sdr_campaigns enable row level security;
alter table public.sdr_leads enable row level security;
alter table public.sdr_messages enable row level security;
alter table public.sdr_events enable row level security;
