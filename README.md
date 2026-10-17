# LinkedIn SDR · The Coto Company

SDR automático que prospecta en LinkedIn **desde el perfil de Enrique**: busca leads, los cualifica con DeepSeek,
envía invitaciones con nota personalizada, detecta quién acepta, escribe el primer mensaje y los seguimientos,
lee las respuestas y prepara la contestación. Todo se controla desde un panel.

```
 n8n (ritmo + DeepSeek vía OpenRouter)
   │  x-api-key
   ▼
 Vercel ── /api/py/*  FastAPI + open-linkedin-api  ──►  LinkedIn (cookies de Enrique)
   │     └─ /         Panel Next.js (contraseña)
   ▼
 Supabase (tablas sdr_*)
```

- **LinkedIn**: [`open-linkedin-api`](https://github.com/EseToni/open-linkedin-api) con las cookies `li_at` + `JSESSIONID`
  (`api/_sdr/li.py`).
- **Lógica**: límites diarios/semanales, horario laboral, estados y bloqueos viven en `api/_sdr/jobs.py`. n8n sólo
  dispara los pasos y hace de puente con la IA, así que si el motor está apagado nada sale a LinkedIn.
- **IA**: la API devuelve los prompts ya montados (`api/_sdr/prompts.py`) con el contexto de Ajustes y de la campaña;
  n8n los pasa a DeepSeek y devuelve el JSON resultante.
- **Panel**: resumen y embudo, aprobaciones, leads con su conversación, campañas, actividad y ajustes.

## Flujo de un lead

| Paso | Quién | Estado |
|---|---|---|
| Búsqueda de la campaña | n8n → `/jobs/prospect` | `new` |
| Perfil + puntuación + nota de invitación (DeepSeek) | n8n → `/jobs/qualify-batch` → IA → `/jobs/qualification` | `invite_review` (o `to_invite` en piloto automático) / `disqualified` |
| Aprobación de la invitación | Panel → Aprobaciones | `to_invite` |
| Invitación (1 por ronda, límites y pausas aleatorias) | n8n → `/jobs/invite` | `invited` |
| Aceptación | n8n → `/jobs/check-connections` | `connected` |
| Primer mensaje y seguimientos (DeepSeek) | n8n → `/jobs/due-messages` → IA → `/jobs/draft` | borrador → aprobado → `messaged` |
| Envío | n8n → `/jobs/send-outbox` | |
| Respuesta: se para la secuencia, DeepSeek clasifica y propone respuesta | n8n → `/jobs/sync-inbox` → IA → `/jobs/reply-analysis` | `replied` / `interested` / `meeting` / `not_interested` |

Por defecto todo pasa por **Aprobaciones**. En Ajustes puedes activar el piloto automático (invitaciones y secuencia)
y las respuestas automáticas por separado. Una respuesta a quien dice que no nunca sale sola.

## Puesta en marcha

### 1. Supabase

Las tablas ya están creadas en el proyecto `xuujbcszciiyebcmagla` (migración en `supabase/migrations/001_sdr.sql`).
Todas llevan el prefijo `sdr_`, tienen RLS activado y ninguna política: sólo la service role puede leerlas.

### 2. Vercel

El proyecto `linkedin-sdr` ya está enlazado a este repositorio. En **Settings → Environment Variables** añade
(Production y Preview):

| Variable | Valor |
|---|---|
| `SUPABASE_URL` | `https://xuujbcszciiyebcmagla.supabase.co` |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase → Project Settings → API Keys → `service_role` / secret |
| `SDR_API_KEY` | Una cadena larga aleatoria (`openssl rand -hex 32`). La misma irá en n8n |
| `PANEL_PASSWORD` | La contraseña para entrar al panel |

**Protección de despliegues**: ahora mismo el proyecto tiene *Vercel Authentication* en todos los despliegues, lo que
bloquea a n8n. Opciones: en **Settings → Deployment Protection** cámbiala a *Only Preview Deployments* (el panel ya
tiene contraseña y la API su clave), o crea un *Protection Bypass for Automation* y añade la cabecera
`x-vercel-protection-bypass` en la credencial de n8n (el panel la usa sola si existe).

Tras añadir las variables, vuelve a desplegar (Deployments → Redeploy) y entra en https://linkedin-sdr.vercel.app con
`PANEL_PASSWORD`.

### 3. Panel

1. **Ajustes → Empresa y propuesta**: describe qué hace The Coto Company, diferenciales, casos reales y la llamada a
   la acción. La IA no cualifica nada mientras esté vacío.
2. **Ajustes → Cliente ideal**.
3. **Ajustes → Sesión de LinkedIn**: pega `li_at` y `JSESSIONID` del navegador de Enrique y pulsa *Guardar y comprobar*.
   Recomendado: un proxy residencial en España (Vercel sale por IPs de EE. UU.).
4. **Campañas → Nueva campaña**: filtros de búsqueda (usa *Probar búsqueda*), instrucciones y secuencia. Actívala.
5. **Resumen → Encender motor**.

### 4. n8n

El workflow ya está creado en https://n8n.thecotocompany.com/workflow/bHhfhvrgePh3kppl (zona horaria Europe/Madrid).
Usa las credenciales existentes `SDR API (x-api-key)` (Header Auth: nombre `x-api-key`, valor = `SDR_API_KEY`) y
`OpenRouter account`, con el modelo `deepseek/deepseek-chat`. `n8n/linkedin-sdr.workflow.json` es una copia para
importarlo en otra instancia.

| Disparador | Frecuencia |
|---|---|
| Buscar leads | 8:20 y 13:20, L-V |
| Cualificar (DeepSeek) | cada 30 min |
| Invitar | cada 15 min, 8-20 h L-V (el horario real lo fija Ajustes) |
| Comprobar aceptaciones | cada 2 h |
| Redactar mensajes (DeepSeek) | cada 30 min L-V |
| Enviar cola | cada 12 min L-V |
| Leer bandeja (DeepSeek) | cada 15 min |

## Seguridad de la cuenta

- Límites por defecto: 15 invitaciones/día, 80/semana, 30 mensajes/día, L-V de 9 a 19 h (Europe/Madrid).
- Una invitación por ronda y pausas aleatorias; la librería además espera 2-5 s entre peticiones.
- Si LinkedIn rechaza la sesión, se marca como caducada, el panel avisa y el motor deja de tocar LinkedIn.
- Las cuentas gratuitas tienen un cupo mensual de notas de invitación de 200 caracteres: si se agota, la invitación se
  envía sin nota y queda registrado.
- `open-linkedin-api` usa la API interna de LinkedIn. No es oficial y usarla puede ir contra sus condiciones; algunos
  endpoints (perfil completo, bandeja antigua) pueden dejar de funcionar. Los fallos quedan en **Actividad** y el lead
  sigue adelante con los datos de la búsqueda cuando el perfil completo no está disponible.

## Desarrollo local

```bash
cp .env.example .env.local        # rellena las variables
npm install
python -m venv .venv && .venv/bin/pip install -r requirements.txt uvicorn
.venv/bin/uvicorn api.index:app --reload --port 8000   # API Python
npm run dev                                            # panel en http://localhost:3000
.venv/bin/pip install pytest httpx && .venv/bin/pytest tests   # recorrido completo con LinkedIn y Supabase simulados
```

La API está documentada en `/api/py/docs`.
