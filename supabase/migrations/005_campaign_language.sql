-- Idioma por campaña (null = el de Ajustes). Para campañas en otros mercados, p. ej. inglés.
alter table public.sdr_campaigns add column if not exists language text;
