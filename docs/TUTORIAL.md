# Cómo construí un SDR de LinkedIn con IA (n8n + Supabase + Vercel + DeepSeek)

> Tutorial completo de cómo se montó el SDR de **The Coto Company**: un sistema que busca clientes potenciales en
> LinkedIn desde el perfil personal de Enrique, los cualifica con IA, les invita a conectar con una nota
> personalizada, les escribe cuando aceptan, hace seguimientos, lee las respuestas y además da "me gusta" y comenta
> publicaciones relevantes. Todo se gestiona desde un panel web.
>
> Incluye el repositorio base, la arquitectura, el orden en que se construyó, **todos los fallos que aparecieron**
> (con su causa real y cómo se arreglaron) y lo aprendido por el camino.

---

## Índice

1. [Resultado](#1-resultado)
2. [El stack y por qué](#2-el-stack-y-por-qué)
3. [Arquitectura](#3-arquitectura)
4. [El recorrido de un lead](#4-el-recorrido-de-un-lead)
5. [Construcción paso a paso](#5-construcción-paso-a-paso)
   - [Fase 1 · Esqueleto: base de datos, API, panel y n8n](#fase-1--esqueleto-base-de-datos-api-panel-y-n8n)
   - [Fase 2 · Puesta en marcha en Vercel y n8n](#fase-2--puesta-en-marcha-en-vercel-y-n8n)
   - [Fase 3 · La sesión de LinkedIn (el gran problema)](#fase-3--la-sesión-de-linkedin-el-gran-problema)
   - [Fase 4 · Estudio de mercado y búsquedas](#fase-4--estudio-de-mercado-y-búsquedas)
   - [Fase 5 · Interacción con publicaciones](#fase-5--interacción-con-publicaciones)
   - [Fase 6 · Aceptaciones y mensajería](#fase-6--aceptaciones-y-mensajería)
   - [Fase 7 · Nicho: consultores de OVB](#fase-7--nicho-consultores-de-ovb)
6. [Tabla de fallos: síntoma → causa → solución](#6-tabla-de-fallos-síntoma--causa--solución)
7. [Aprendizajes](#7-aprendizajes)
8. [Cómo replicarlo desde cero](#8-cómo-replicarlo-desde-cero)
9. [Operación diaria](#9-operación-diaria)
10. [Mantenimiento: lo que se va a romper](#10-mantenimiento-lo-que-se-va-a-romper)
11. [Riesgos y avisos](#11-riesgos-y-avisos)
12. [Próximos pasos](#12-próximos-pasos)

---

## 1. Resultado

Datos reales del sistema a 26 de octubre de 2026 (una semana en marcha):

| Métrica | Total | Campaña OVB |
| --- | ---: | ---: |
| Perfiles cualificados por la IA | 232 | — |
| Perfiles descartados por la IA | 90 | — |
| Invitaciones enviadas | 89 | 60 |
| Invitaciones aceptadas | 38 | 25 (**42 %**) |
| Mensajes enviados | 54 | — |
| Personas que han respondido | 16 | 12 (**48 % de los que aceptan**) |
| Leads interesados o con reunión | 9 | **7** |
| Me gusta / comentarios en publicaciones | 14 / 12 | — |

La lección más importante del proyecto sale de esta tabla: **las campañas genéricas (clínicas, catering, coaches,
reformas) funcionaron discretamente; la campaña de nicho (consultores financieros de una sola empresa, OVB, con
prueba social real) multiplicó todo.** Ver [Fase 7](#fase-7--nicho-consultores-de-ovb).

---

## 2. El stack y por qué

| Pieza | Qué hace | Por qué |
| --- | --- | --- |
| **[open-linkedin-api](https://github.com/EseToni/open-linkedin-api)** (Python) | Habla con la API interna de LinkedIn (Voyager) usando las cookies de la sesión | Es el repositorio base del proyecto. Da búsqueda, perfiles, invitaciones y publicaciones sin navegador |
| **Vercel** | Aloja la API (FastAPI, Python 3.12) y el panel (Next.js 15) en el mismo proyecto | Un solo despliegue por `git push`, sin servidores |
| **Supabase** (Postgres) | Guarda ajustes, campañas, leads, mensajes, eventos e interacciones | Base de datos gestionada con API REST (PostgREST) |
| **n8n** | Orquesta: dispara cada paso por horario y hace de puente con la IA | Programar y ver ejecuciones es trivial; las credenciales de OpenRouter ya estaban allí |
| **DeepSeek vía OpenRouter** | Cualifica perfiles, escribe notas, mensajes, respuestas y comentarios | Muy barato y bueno en español; se usa en modo `json_object` |
| **Extensión de Chrome propia** | Pasa la sesión de LinkedIn del navegador al servidor | Para no copiar cookies a mano (idea sacada de WaLead) |
| **Proxy residencial en España** | El servidor sale a internet por una IP española | Sin él LinkedIn cerraba la sesión a los pocos minutos |

Principio de diseño clave: **la lógica vive en Python, n8n sólo dispara**. Límites, horarios, estados y bloqueos
están en `api/_sdr/jobs.py`. Si el motor está apagado, n8n puede ejecutarse cuantas veces quiera: no sale nada a
LinkedIn.

---

## 3. Arquitectura

```
                 ┌──────────────────────────────┐
                 │  n8n (n8n.thecotocompany.com) │
                 │  Schedule → HTTP → DeepSeek   │
                 └──────────────┬───────────────┘
                                │ x-api-key
                                ▼
  Chrome de Enrique      ┌───────────────────────────────┐        ┌──────────────┐
  ┌───────────────┐      │  Vercel                        │        │  Supabase    │
  │ Extensión     │─────▶│  /api/py/*  FastAPI (Python)   │◀──────▶│  sdr_*       │
  │ (cookies +    │      │    api/_sdr/jobs.py  lógica    │        │  tablas      │
  │  navegador)   │      │    api/_sdr/li.py    LinkedIn  │        └──────────────┘
  └───────────────┘      │    api/_sdr/prompts.py  IA     │               ▲
                         │  /  panel Next.js (Ajustes,    │───────────────┘
                         │     Aprobaciones, Leads...)    │
                         └──────────────┬────────────────┘
                                        │ proxy residencial ES
                                        ▼
                                   LinkedIn (Voyager)
```

### Repositorio

```
api/
  index.py            FastAPI: rutas /api/py/* y autenticación por x-api-key
  _sdr/db.py          cliente PostgREST mínimo (con reintentos)
  _sdr/li.py          todo lo que habla con LinkedIn
  _sdr/jobs.py        la lógica del SDR (clase SDR)
  _sdr/prompts.py     prompts de DeepSeek (cualificar, mensaje, respuesta, comentario)
app/(panel)/          páginas del panel: resumen, aprobaciones, leads, campañas, interacción, actividad, ajustes
app/actions.ts        server actions del panel
components/           formularios, editores, botón "Conectar con la extensión"
extension/            extensión de Chrome (Manifest V3)
n8n/                  copia exportable del workflow
supabase/migrations/  esquema de base de datos (001 a 004)
tests/test_jobs.py    recorrido completo con LinkedIn y Supabase simulados
docs/                 estudio de mercado y este tutorial
```

### Tablas (Supabase)

| Tabla | Contenido |
| --- | --- |
| `sdr_settings` | Una fila: empresa, propuesta, cliente ideal, tono, límites, horario, interruptores y sesión de LinkedIn |
| `sdr_campaigns` | Filtros de búsqueda, matices de cliente ideal, instrucciones para la IA y secuencia |
| `sdr_leads` | Cada persona encontrada y su estado (`new → invite_review/to_invite → invited → connected → messaged → replied → interested/meeting`) |
| `sdr_messages` | Borradores, mensajes enviados y recibidos |
| `sdr_events` | Registro de todo lo que pasa (y base de los límites diarios) |
| `sdr_engagements` | Publicaciones candidatas a me gusta / comentario |

Todas con RLS activado y sin políticas: sólo la service role (servidor) puede leerlas.

---

## 4. El recorrido de un lead

| Paso | Quién | Cuándo (Europe/Madrid) |
| --- | --- | --- |
| 1. **Buscar** 25 perfiles por campaña activa hasta tener 40 en cola | API → LinkedIn | 8:20 y 13:20, L-V |
| 2. **Cualificar**: la API manda el perfil y el prompt; DeepSeek devuelve puntuación, motivo, resumen y nota | n8n → DeepSeek → API | cada 30 min |
| 3. **Revisar** (si el piloto automático está apagado) en *Aprobaciones* | Enrique | — |
| 4. **Invitar** con nota (máx. 200 caracteres), 1 por ronda, cupo repartido entre campañas | API → LinkedIn | cada 15 min, 9-19 h L-V |
| 5. **Detectar aceptación** con la lista de contactos recientes | API → LinkedIn | cada 30 min |
| 6. **Redactar** primer mensaje (1 h después de aceptar) y seguimientos (a los 4 y 7 días) | n8n → DeepSeek → API | :10 y :40, L-V |
| 7. **Enviar** la cola de mensajes aprobados | API → LinkedIn | cada 12 min, L-V |
| 8. **Leer la bandeja**: si responde, se cancela la secuencia y la IA clasifica la intención y propone respuesta | API → LinkedIn → DeepSeek | cada 15 min |

Límites por defecto: 15 invitaciones/día, 80/semana, 30 mensajes/día, 25 me gusta y 8 comentarios al día,
horario L-V 9-19 h. Hay pausas aleatorias (25 % de las rondas de invitación, 20 % de las de interacción) para no
tener un ritmo de máquina.

---

## 5. Construcción paso a paso

### Fase 1 · Esqueleto: base de datos, API, panel y n8n

**Petición inicial:** "un SDR en LinkedIn para thecotocompany.com desde mi perfil, con n8n, Supabase y Vercel,
DeepSeek por OpenRouter, usando open-linkedin-api, y con un panel para manejarlo todo".

Decisiones:

1. **Una sola app en Vercel con dos runtimes.** FastAPI en `api/index.py` (Python) y Next.js en la raíz. Un
   rewrite en `vercel.json` manda `/api/py/:path*` a la función Python.
2. **La IA no vive en la API.** La API prepara el prompt y n8n llama a DeepSeek con sus credenciales de
   OpenRouter. Así la API no necesita la clave de OpenRouter y en n8n se ve cada respuesta de la IA.
3. **Estados explícitos y bloqueos** (`locked_until`) para que dos ejecuciones de n8n no cojan el mismo lead.
4. **Eventos como fuente de verdad de los límites:** "¿cuántas invitaciones hoy?" es un `count` de `sdr_events`.
5. **Tests con LinkedIn y Supabase falsos** (`FakeDB` y `FakeLinkedIn` en `tests/test_jobs.py`) que recorren la
   secuencia completa. Fueron clave para cambiar cosas con confianza más adelante.

Problemas de esta fase:

- **`apply_migration` de Supabase se quedaba colgado** con funciones `$$ ... $$` (triggers de `updated_at`).
  → Se quitaron triggers y funciones; `updated_at` se pone desde el código.
- **El MCP de Supabase se cuelga con `;` dentro de literales SQL** y los `DELETE` piden aprobación y caducan.
  → Evitar `;` en textos; neutralizar con `UPDATE` en vez de borrar.

### Fase 2 · Puesta en marcha en Vercel y n8n

Variables de entorno en Vercel (Production): `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`,
`NEXT_PUBLIC_SUPABASE_URL`, `SDR_API_KEY`, `PANEL_PASSWORD` y opcionalmente `LINKEDIN_PROXY`.

Fallos encontrados, en orden:

1. **n8n recibía la página de login de Vercel.** La protección SSO de Vercel bloqueaba las llamadas.
   → Desactivar *Deployment Protection* (la API ya tiene su propia clave).
2. **Los cambios no llegaban a producción.** El primer despliegue fue producción, los siguientes eran *previews*
   (sin variables de entorno). → Crear la rama `main` como rama de producción. Y ojo: Vercel no vuelve a
   desplegar un commit que ya desplegó, así que se empuja primero a `main` y después a la rama de trabajo.
3. **Python equivocado en Vercel.** → `.python-version` con `3.12`.
4. **"401 API key inválida" desde n8n aunque la clave estaba bien.** Había **dos credenciales con el mismo
   nombre** ("SDR API (x-api-key)"), una *Header Auth* con una clave antigua y otra *Query Auth* actualizada. Los
   nodos usaban la vieja. → Pasar todos los nodos a *Query Auth* y que la API acepte también `?x-api-key=`.
   Además el error ahora dice cuántos caracteres recibió frente a los que espera (detecta espacios y claves viejas
   sin revelar la clave).
5. **La IA respondía pero no se guardaba nada.** El nodo *Basic LLM Chain* con salida `json_object` devuelve los
   campos ya parseados, no un `.text`. El código de parseo buscaba `.text`, no encontraba nada y descartaba todo:
   los leads se habrían quedado atascados para siempre. → El parseo acepta las dos formas (campos directos o texto
   con JSON dentro). Verificado con un lead de prueba: puntuación 90, invitación lista y borrador del primer mensaje.
6. **Plantillas de LangChain:** las llaves `{ }` del prompt se interpretaban como variables. → `prompts._safe()`
   cambia llaves por paréntesis.
7. **La IA mezclaba casos reales** ("13 eventos fuera de temporada"). → Regla en el prompt: "si citas un caso
   real, usa sus datos exactos sin cambiarlos", e instrucciones de campaña con ideas separadas.

### Fase 3 · La sesión de LinkedIn (el gran problema)

`open-linkedin-api` funciona con las cookies `li_at` y `JSESSIONID` de un navegador con la sesión iniciada. Al
principio se pegaban a mano en Ajustes. Y la sesión **moría a los pocos minutos**:

| Hora | Qué pasó |
| --- | --- |
| 16:23 | La sesión funciona desde Vercel (Washington, `iad1`) |
| 16:26 | Se mueve la función a Dublín (`dub1`) para estar "en Europa" |
| 16:28 | 401: LinkedIn rechaza la sesión |
| 21:10 | Vuelta a `iad1`; la sesión sigue muerta |

Pregunta de Enrique: *"¿no hay una manera de que nunca se vaya la autenticación, metiendo la contraseña?"*. El
login con contraseña desde un servidor dispara verificaciones (checkpoint) y es peor. Había que entender cómo lo
hacen los SaaS del sector.

**Análisis de WaLead con [REA](https://github.com/morluto/rea).** Se descargó el código de la app web de WaLead y
el de su extensión de Chrome y se analizaron con `rea-agents analyze-javascript-application`. Lo que hacen:

1. Su extensión abre `linkedin.com/login`, espera a que exista la cookie `li_at` y lee **todas** las cookies de
   LinkedIn más el `navigator.userAgent`.
2. Las sube a su API y desde ahí **envían desde sus servidores** (el ordenador del usuario puede estar apagado).
3. Cada cuenta sale por un **proxy residencial dedicado de su país**.
4. Encima: límites diarios, horario, calentamiento de cuentas nuevas, retirada de invitaciones pendientes y un
   "health score" por cuenta.

**Lo que se aplicó aquí:**

1. **Extensión de Chrome propia** (`extension/`, ID fijo gracias a la clave pública del `manifest.json`). Lee las
   cookies de `linkedin.com` y el navegador y las manda a `POST /api/py/linkedin/session` con su propia clave
   (nunca la `SDR_API_KEY`). Lo hace al conectar, cuando cambian `li_at`/`JSESSIONID` y como latido cada 2 h.
   El panel habla con ella por `externally_connectable`, con un botón *Conectar con la extensión* en Ajustes.
2. **El servidor se presenta como ese navegador**: todas las cookies (`bcookie`, `bscookie`, `lidc`...), el mismo
   user agent y el mismo idioma. Un `li_at` suelto desde otra máquina es lo que más se parece a una sesión robada.
3. **La sesión vive en el servidor**: cada respuesta de LinkedIn que renueva cookies se guarda (como haría un
   navegador) y el token CSRF sigue al `JSESSIONID` nuevo. No se guardan cookies de respuestas 401/403.
4. **Proxy en España obligatorio.** Se comprobó dos veces el patrón "funciona → muere a los 4-5 minutos" sin
   proxy. Desde entonces, sin proxy el SDR no toca LinkedIn (la extensión guarda la sesión sin probarla).
   *Guardar y comprobar* muestra la IP, ciudad y proveedor por los que sale.

Fallos de esta fase:

- **"¿Y con una lista de proxies gratis?"** No: son de terceros desconocidos (la cookie `li_at` da acceso total a
  la cuenta), cambian cada pocas horas (justo lo contrario de lo que hace falta: una IP fija) y LinkedIn los tiene
  fichados.
- **Error 500 al guardar el proxy.** IPRoyal lo da como `host:puerto:usuario:clave` y el servidor sólo entendía
  `http://usuario:clave@host:puerto`; en vez de avisar, se caía. → `normalize_proxy()` acepta los dos formatos y
  cualquier error de red se devuelve como 502 con mensaje claro.
- **El último cambio no llegó a producción** (sólo a la preview de la rama) y durante horas producción siguió
  probando una sesión muerta. → Comprobar siempre el despliegue de `main` después de un push.

Resultado: con un proxy residencial de Madrid la sesión se mantiene, aunque el ordenador esté apagado.

### Fase 4 · Estudio de mercado y búsquedas

Para elegir campañas se midió el volumen real en LinkedIn de cada sector del cliente ideal (endpoint
`GET /api/py/research/search`). Y ahí apareció un fallo que llevaba ahí desde el principio:

1. **Todas las búsquedas devolvían 0 resultados.** Para diagnosticarlo se añadió un modo que devuelve la respuesta
   en bruto de LinkedIn: `"totalResultCount": 0, "filterAppliedCount": 0`. Probando filtro a filtro: sólo palabra
   clave → 1,9 millones; + España → 45.812; + grado de contacto → 0.
   **Causa:** los filtros con varios valores se separaban con `" | "` (formato antiguo) y LinkedIn ahora exige
   comas: `(key:network,value:List(S,O))`. No daba error, sólo 0 resultados. **Las campañas nunca habían
   encontrado a nadie.**
2. **Error 413 ("Internal error fetching data from downstream")** con el filtro de cargo de 10 términos.
   → El filtro de cargo admite unos 5 términos con OR; las palabras clave, 3-4.
3. **Sin filtro de cargo salen empleados**, no dueños (727.941 resultados en catering/eventos/bodas, casi todos
   coordinadores y comerciales). El filtro de cargo es imprescindible.
4. **Una campaña podía llevarse todo el cupo diario** (las invitaciones salían por orden de llegada). → La
   siguiente invitación sale de la campaña que menos lleva hoy.

Estudio completo en [`docs/estudio-mercado-2026-10.md`](estudio-mercado-2026-10.md).

### Fase 5 · Interacción con publicaciones

Me gusta y comentarios en publicaciones de los leads (antes y después de invitarles) y del feed. DeepSeek decide si
la publicación es relevante, si merece me gusta y si hay algo valioso que comentar.

Fallos y su causa real:

1. **Me gusta en publicaciones de hace 7 meses y 6 años.** Al pedir LinkedIn en español, la antigüedad llega como
   "7 meses", "6 años"... El filtro sólo entendía `3d`, `2w`, `1mo`; lo que no entendía contaba como **0 días**.
   → Se parsea español e inglés y, sobre todo, se usa la **fecha que lleva el propio identificador**: en
   `urn:li:activity:<id>` los 41 bits altos son el timestamp en milisegundos (`id >> 22`).
   Regla de Enrique: **nada con publicaciones de más de 7 días**. Se comprueba al recogerlas, en la cola y justo
   antes de actuar.
2. **Me gusta que fallaban con 400 "No se puede reaccionar a esta publicación".** Primera hipótesis (incompleta):
   compartidos. La causa real salió al mirar el feed en bruto: cada elemento tiene dos identificadores, el del
   **evento del feed** ("X ha comentado esto", `updateMetadata.urn`) y el de **la publicación**
   (`*socialDetail`). LinkedIn sólo acepta reacciones y comentarios sobre el segundo. → El feed se lee
   directamente (`/feed/updatesV2`) y se usa el hilo del `socialDetail`, que además trae la fecha real.
3. **Comentarios que empezaban por "Totalmente de acuerdo" o "Muy cierto"** aunque el prompt lo prohibía, y alguno
   vendía ("justo ayudamos a empresas..."). → Se limpian esos arranques en el código (no basta con pedirlo en el
   prompt) y los que venden quedan para aprobación aunque los comentarios automáticos estén activos.

### Fase 6 · Aceptaciones y mensajería

Enrique vio en LinkedIn que gente había aceptado y nadie les había escrito.

1. **Aceptaciones detectadas tarde.** Cada lead se revisaba cada 6 h con `networkinfo` y el primer mensaje
   esperaba **24 h** desde la detección. → Una sola petición a la lista de contactos recién añadidos
   (`/relationships/dash/connections?sortType=RECENTLY_ADDED`) cada 30 min y primer mensaje a la hora. En la
   primera prueba detectó 5 aceptaciones de 15 invitaciones de ese día.
2. **Mensajes que fallaban con 500.** La librería usa la mensajería antigua (`/messaging/conversations`). Con los
   que ya tenían conversación abierta (por la nota de invitación) daba 500. → Mensajería actual:
   `voyagerMessagingDashMessengerMessages?action=createMessage` con `mailboxUrn` y `hostRecipientUrns` o
   `conversationUrn`.
3. **La bandeja tampoco funcionaba (el fallo más grave).** La lectura antigua también devolvía 500 cada 15 minutos
   desde el primer día: si alguien respondía, el SDR no se enteraba y seguía mandando seguimientos. La bandeja nueva
   va por GraphQL con identificadores de consulta (`queryId`) que cambian con cada versión de la web. Se
   **descubrieron leyendo el código JavaScript de `linkedin.com/messaging`** y se probaron en vivo:
   `messengerConversations.<hash>` (con `query:(predicateUnions:List((conversationCategoryPredicate:(category:PRIMARY_INBOX))))`)
   y `messengerMessages.<hash>`. Los mensajes anteriores a la invitación quedan como historial pero no cuentan como
   respuesta.
4. **Cualificaciones que fallaban de vez en cuando por "Read timed out" de Supabase.** Los logs de Supabase
   mostraban que la petición nunca llegaba: la conexión reutilizada se quedaba muerta mientras se esperaba a
   LinkedIn por el proxy. → Reintentos con conexión nueva (`urllib3.Retry`) y esperas de 5 s / 15 s.

### Fase 7 · Nicho: consultores de OVB

Enrique vio a otra persona contactando así a consultores financieros de OVB, y The Coto Company ya trabaja con
varios. Se creó una campaña sólo para ellos y se pausaron las demás.

- Búsqueda: empresa actual "OVB", en España, 2.º y 3.er grado → **2.685 personas**, casi todas consultores
  financieros, gestores de equipo y coordinadores de zona de OVB Allfinanz. Los 14 contactos directos de OVB se
  dejaron fuera (probablemente clientes).
- **El cliente ideal general excluía "grandes corporaciones" y "empleados"**: la IA podía descartar a los
  consultores de OVB. → El cliente ideal y las instrucciones de cada campaña mandan sobre los generales.
- **Pausar no paraba**: una campaña en pausa seguía invitando a los leads que tenía en cola. → Sólo se cualifica e
  invita de campañas activas (los ya conectados siguen con su secuencia).
- Mensaje: vía de captación que no depende de su red de contactos, solicitudes ya filtradas de particulares que
  quieren ahorrar o invertir, aviso al momento, sin publicidad ni usar la marca OVB, y **prueba social real**
  ("ya trabajamos con varios consultores de OVB") sin inventar cifras.

Resultado en una semana: **60 invitaciones → 25 aceptadas (42 %) → 12 respuestas → 7 interesados o con reunión**.

---

## 6. Tabla de fallos: síntoma → causa → solución

| # | Síntoma | Causa real | Solución |
| --- | --- | --- | --- |
| 1 | `apply_migration` colgado | Funciones con `$$` en el MCP de Supabase | Sin triggers; `updated_at` desde el código |
| 2 | n8n recibe HTML de Vercel | Protección SSO de despliegues | Desactivarla; la API tiene su clave |
| 3 | Cambios que no llegan a producción | Rama de producción mal fijada; previews sin variables | Rama `main` de producción; push a `main` primero |
| 4 | 401 desde n8n con la clave correcta | Dos credenciales con el mismo nombre en n8n | Una sola (Query Auth); error con longitudes |
| 5 | La IA responde y no se guarda nada | `json_object` devuelve campos, no `.text` | Parseo que acepta ambas formas |
| 6 | Prompts rotos en n8n | Llaves `{}` = variables de LangChain | Sustituir llaves por paréntesis |
| 7 | La IA mezcla datos de casos reales | Instrucciones ambiguas | Regla de "datos exactos" e ideas separadas |
| 8 | Sesión muere a los 4-5 min | IP de centro de datos de EE. UU. con cookies de España | Extensión + todas las cookies + proxy residencial ES |
| 9 | 500 al guardar el proxy | Formato `host:puerto:usuario:clave` | `normalize_proxy()` y errores de red como 502 |
| 10 | Producción con código viejo | El push sólo desplegó la preview | Comprobar el despliegue de `main` |
| 11 | Búsquedas con 0 resultados | Separador `" \| "` en filtros con varios valores | Comas |
| 12 | 413 en la búsqueda | Filtro de cargo con 10 términos | ≤ 5 términos |
| 13 | Una campaña acapara invitaciones | Orden de llegada global | Reparto por campaña |
| 14 | Me gusta en posts de años | "7 meses" en español no se entendía (= 0 días) | Fecha del identificador + regla de 7 días |
| 15 | Me gusta con 400 | Identificador del evento del feed, no del post | Hilo del `socialDetail` |
| 16 | Comentarios vacíos o vendedores | La IA ignora prohibiciones | Limpieza en código + aprobación si vende |
| 17 | Nadie recibe mensaje tras aceptar | Revisión cada 6 h + espera de 24 h | Lista de contactos recientes + 1 h |
| 18 | Mensajes con 500 | Mensajería antigua retirada | `MessengerMessages?action=createMessage` |
| 19 | Respuestas nunca detectadas | Bandeja antigua retirada | GraphQL `messengerConversations`/`messengerMessages` |
| 20 | "Read timed out" de Supabase | Conexión reutilizada muerta tras esperar al proxy | Reintentos con conexión nueva |
| 21 | Campañas pausadas siguen invitando | Sólo se filtraba al buscar | Filtrar también al cualificar e invitar |
| 22 | Nicho descartado por la IA | El cliente ideal general lo excluía | Lo de la campaña manda sobre lo general |

---

## 7. Aprendizajes

**Sobre LinkedIn**

1. **La API interna cambia sin avisar y falla en silencio.** Búsquedas con 0 resultados, mensajería que devuelve
   500, identificadores que ya no valen. Una librería de hace un año ya tiene media API rota.
2. **Cuando algo no cuadra, mira la respuesta en bruto.** Casi todos los fallos se resolvieron añadiendo un modo
   diagnóstico que devolvía lo que LinkedIn contestaba de verdad (`filterAppliedCount: 0`, los dos identificadores
   del feed, el error de validación GraphQL).
3. **La web de LinkedIn es la documentación.** Los `queryId` actuales están en su JavaScript; lo que hace su web
   es lo que funciona.
4. **La sesión es una huella, no una cookie.** Navegador, idioma, todas las cookies e IP tienen que ser
   coherentes. Por eso los SaaS del sector dan a cada cuenta un proxy de su país.
5. **Los identificadores llevan información.** `urn:li:activity:<id>` lleva la fecha de creación: más fiable que
   "hace 3 días" en el idioma que toque.

**Sobre IA en producción**

6. **Lo que el prompt prohíbe, el código lo vigila.** "No empieces con 'Totalmente de acuerdo'" no basta.
7. **Separar la lógica de la IA.** La IA redacta y clasifica; los límites, estados y reglas duras están en código
   y en tests.
8. **Contexto específico por campaña.** Un cliente ideal general puede hacer que la IA descarte justo el nicho que
   quieres.

**Sobre el negocio**

9. **El nicho gana.** Una empresa concreta, un dolor concreto y prueba social real: 42 % de aceptación y la mitad
   responde.
10. **El mercado no es el límite; la calidad sí.** Con 15 invitaciones al día hay volumen para años en casi
    cualquier sector.

**Sobre el proceso**

11. **Tests con dobles de LinkedIn y Supabase** permitieron rehacer la mensajería, el feed y la detección de
    aceptaciones sin miedo (26 tests al final).
12. **Verificar en producción, no sólo en local.** Varios fallos sólo se vieron mirando las ejecuciones de n8n, los
    logs de Supabase y la base de datos tras cada ronda.
13. **Desplegar no es hacer push.** Comprobar que el commit está en el despliegue de producción.

---

## 8. Cómo replicarlo desde cero

1. **Supabase**: crea un proyecto en la UE y aplica `supabase/migrations/001` a `004` en orden.
2. **Vercel**: importa el repo, rama de producción `main`, región `iad1`, y añade en *Production*:
   `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `NEXT_PUBLIC_SUPABASE_URL`, `SDR_API_KEY` (cadena larga
   aleatoria) y `PANEL_PASSWORD`. Desactiva *Deployment Protection*.
3. **n8n**: importa `n8n/linkedin-sdr.workflow.json`, crea una credencial *Query Auth* con nombre `x-api-key` y
   valor `SDR_API_KEY`, conecta OpenRouter (modelo `deepseek/deepseek-chat`) y actívalo. La copia del repo no
   trae los nodos de interacción: el workflow vivo es la referencia.
4. **Panel → Ajustes**: describe la empresa, la propuesta, los casos reales (sin nombres de clientes), el cliente
   ideal, el tono y la llamada a la acción. La IA no cualifica nada mientras esté vacío.
5. **Proxy**: contrata un proxy ISP o residencial **estático** en tu país (mejor de tu ciudad) y pégalo en Ajustes.
   *Guardar y comprobar* debe mostrar tu país.
6. **Extensión**: descarga el zip desde Ajustes, cárgala en `chrome://extensions` (modo desarrollador → *Cargar
   descomprimida*) y pulsa *Conectar con la extensión*.
7. **Estudio de mercado**: mide volúmenes con `/api/py/research/search` (palabras clave + cargo ≤ 5 términos +
   región) antes de crear campañas.
8. **Campañas**: empieza con una de nicho. Prueba la búsqueda en el panel antes de activarla.
9. **Primer día con el piloto automático apagado**: revisa notas y mensajes en *Aprobaciones* y actívalo cuando el
   tono sea el correcto.

Desarrollo local:

```bash
cp .env.example .env.local
npm install
python -m venv .venv && .venv/bin/pip install -r requirements.txt uvicorn pytest httpx
.venv/bin/uvicorn api.index:app --reload --port 8000   # API
npm run dev                                            # panel en http://localhost:3000
.venv/bin/pytest tests                                 # 26 tests
scripts/pack-extension.sh                              # tras tocar extension/
```

---

## 9. Operación diaria

| Página | Para qué |
| --- | --- |
| **Resumen** | Motor, piloto automático, respuestas automáticas, contadores del día, avisos (sesión, proxy) y botones para lanzar cada paso a mano |
| **Aprobaciones** | Invitaciones, mensajes y respuestas pendientes; mensajes fallidos con *Reintentar* |
| **Leads** | Cada persona, su estado, conversación y notas |
| **Campañas** | Filtros, instrucciones para la IA, secuencia, *Probar búsqueda* y *Buscar leads ahora* |
| **Interacción** | Me gusta y comentarios: límites, temas y comentarios por aprobar |
| **Actividad** | Registro de todo lo que ha pasado (incluidos errores) |
| **Ajustes** | Empresa, cliente ideal, tono, límites, horario, sesión, extensión y proxy |

Rutina recomendada: mirar *Aprobaciones* y las respuestas una vez al día, y *Ajustes* si aparece el aviso de
sesión caducada (se reconecta entrando en LinkedIn en Chrome).

---

## 10. Mantenimiento: lo que se va a romper

- **Los `queryId` de GraphQL** (`_CONVERSATIONS_QUERY`, `_MESSAGES_QUERY` en `api/_sdr/li.py`). Si la bandeja falla
  con un error de validación, buscar los actuales en el código de `https://www.linkedin.com/messaging/` y
  sustituirlos.
- **El de búsqueda** (`voyagerSearchDashClusters.<hash>`): si las búsquedas empiezan a fallar, mismo método.
- **Formatos de filtros y respuestas**: usar el modo diagnóstico (`/api/py/research/search?...&debug=true`) para
  ver la respuesta en bruto antes de tocar nada.
- **Sesión**: si LinkedIn la cierra, entrar en LinkedIn en Chrome; la extensión la sincroniza sola.
- **n8n**: revisar de vez en cuando las ejecuciones con error. Un paso que falla siempre a la misma hora es casi
  siempre un endpoint de LinkedIn que ha cambiado.

---

## 11. Riesgos y avisos

- **Automatizar LinkedIn va contra sus condiciones de uso.** Usar su API interna, aunque sea con tu propia cuenta,
  puede acabar en cierre de sesión o restricción de la cuenta. Los límites, el horario, las pausas aleatorias y el
  proxy reducen el riesgo, pero no lo eliminan. Servicios como WaLead asumen ese mismo riesgo.
- **La cookie `li_at` da acceso completo a la cuenta.** Nunca por proxies de terceros desconocidos; la extensión
  usa su propia clave y la `SDR_API_KEY` nunca sale del servidor.
- **Secretos fuera del repositorio**: claves, proxy y tokens van en variables de entorno o en `sdr_settings`
  (protegida por RLS).
- **Pendiente de seguridad en Supabase:** en el mismo proyecto hay una tabla `accounts` (de otra aplicación) con
  RLS desactivado y tokens sensibles. Conviene activar RLS en ella.
- **Datos personales**: los leads son personas; guarda sólo lo necesario y respeta a quien pide no ser contactado
  (estado `do_not_contact`).

---

## 12. Próximos pasos

- Retirar automáticamente invitaciones pendientes antiguas (como hace WaLead) para cuidar la cuenta.
- Calentamiento progresivo de límites para cuentas nuevas.
- Aviso por Telegram o email cuando la sesión caduca o alguien responde con interés.
- Descubrimiento automático de los `queryId` de GraphQL cuando LinkedIn los cambie.
- Más campañas de nicho con el mismo patrón de OVB: empresa concreta + dolor concreto + prueba social real.
