-- Interacción con publicaciones: "me gusta" y comentarios en posts de leads y del feed.
-- status: new (espera a la IA) -> ready (decidido) -> done | skipped | failed
-- comment_status: none | draft (espera aprobación) | approved (en cola) | posted | rejected | failed

create table if not exists public.sdr_engagements (
  id uuid primary key default gen_random_uuid(),
  lead_id uuid references public.sdr_leads(id) on delete cascade,
  source text not null default 'feed' check (source in ('lead', 'feed')),
  post_urn text not null unique,
  post_url text not null default '',
  author_name text not null default '',
  author_headline text not null default '',
  post_text text not null default '',
  post_age text not null default '',
  status text not null default 'new' check (status in ('new', 'ready', 'done', 'skipped', 'failed')),
  relevance int,
  reason text not null default '',
  want_like boolean not null default false,
  liked_at timestamptz,
  comment text not null default '',
  comment_status text not null default 'none' check (comment_status in ('none', 'draft', 'approved', 'posted', 'rejected', 'failed')),
  commented_at timestamptz,
  error text,
  locked_until timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists sdr_engagements_status_idx on public.sdr_engagements (status, created_at);
create index if not exists sdr_engagements_comment_idx on public.sdr_engagements (comment_status, created_at);
alter table public.sdr_engagements enable row level security;

alter table public.sdr_leads add column if not exists last_engaged_at timestamptz;

alter table public.sdr_settings add column if not exists engagement_enabled boolean not null default true;
alter table public.sdr_settings add column if not exists auto_comment boolean not null default false;
alter table public.sdr_settings add column if not exists daily_like_limit int not null default 25;
alter table public.sdr_settings add column if not exists daily_comment_limit int not null default 8;
alter table public.sdr_settings add column if not exists engagement_topics text not null default
  'captación de clientes, ventas, marketing para pymes, emprendimiento, gestión de negocios de servicios, y cualquier publicación de dueños de negocios de los sectores de nuestras campañas';
