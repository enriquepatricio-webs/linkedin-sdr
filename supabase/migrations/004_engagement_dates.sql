-- Fecha real de cada publicación (sale de su identificador de actividad). No se interactúa con
-- publicaciones de más de 7 días. El primer mensaje sale 1 hora después de aceptar, no 24.

alter table public.sdr_engagements add column if not exists post_created_at timestamptz;
alter table public.sdr_campaigns alter column first_message_delay_hours set default 1;
update public.sdr_campaigns set first_message_delay_hours = 1 where first_message_delay_hours = 24;
