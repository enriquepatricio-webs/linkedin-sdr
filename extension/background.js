// Coto SDR · Conector de LinkedIn
//
// Hace lo mismo que la extensión de WaLead: lee las cookies de LinkedIn del navegador de Enrique
// (todas, no sólo li_at) y su user agent, y se las manda al SDR. Así el servidor trabaja con la
// misma sesión que el navegador y, cuando LinkedIn la renueva o Enrique vuelve a entrar, el SDR
// la recibe sola en segundos. No hace scraping ni llama a LinkedIn: sólo lee cookies.

const DEFAULT_API = "https://linkedin-sdr.vercel.app"
const ALLOWED_APIS = [DEFAULT_API, "http://localhost:3000"]
const HEARTBEAT_HOURS = 2 // aunque no cambie nada, avisa cada 2 h de que sigue viva
const LOGIN_TIMEOUT_MS = 5 * 60 * 1000
const KEY_COOKIES = ["li_at", "JSESSIONID"]

// ---------- estado ----------

async function getState() {
	const s = await chrome.storage.local.get(null)
	return { apiBase: DEFAULT_API, status: "unpaired", ...s }
}

async function setState(values) {
	await chrome.storage.local.set(values)
	const { status } = await getState()
	const badge = {
		ok: ["ON", "#059669"],
		logged_out: ["OFF", "#64748b"],
		invalid: ["!", "#dc2626"],
		error: ["!", "#dc2626"],
		unpaired: ["?", "#d97706"],
		needs_proxy: ["PRX", "#d97706"],
	}[status] || ["", "#64748b"]
	await chrome.action.setBadgeText({ text: badge[0] })
	await chrome.action.setBadgeBackgroundColor({ color: badge[1] })
}

// ---------- cookies ----------

async function linkedinCookies() {
	const all = await chrome.cookies.getAll({ domain: "linkedin.com" })
	const host = (c) => c.domain.replace(/^\./, "")
	// Las de www.linkedin.com mandan sobre las de linkedin.com si se llaman igual.
	const relevant = all
		.filter((c) => ["linkedin.com", "www.linkedin.com"].includes(host(c)))
		.sort((a, b) => host(a).length - host(b).length)
	const out = {}
	for (const c of relevant) out[c.name] = c.value
	return out
}

async function fingerprint(cookies) {
	const data = new TextEncoder().encode(KEY_COOKIES.map((k) => cookies[k] || "").join("|"))
	const hash = await crypto.subtle.digest("SHA-256", data)
	return [...new Uint8Array(hash)].map((b) => b.toString(16).padStart(2, "0")).join("")
}

// ---------- sincronización ----------

let running = null

function sync(reason, force = false) {
	// Una sola sincronización a la vez: los cambios de cookies llegan en ráfagas.
	if (!running) running = doSync(reason, force).finally(() => (running = null))
	return running
}

async function doSync(reason, force) {
	const state = await getState()
	if (!state.token) {
		await setState({ status: "unpaired", error: "Conecta la extensión desde Ajustes del panel del SDR" })
		return { ok: false, error: "Extensión sin conectar al panel" }
	}

	const cookies = await linkedinCookies()
	if (!cookies.li_at || !cookies.JSESSIONID) {
		await setState({ status: "logged_out", error: "No hay sesión de LinkedIn abierta en este navegador" })
		return { ok: false, error: "Entra en LinkedIn en este navegador" }
	}

	const hash = await fingerprint(cookies)
	const recent = state.lastSyncAt && Date.now() - state.lastSyncAt < HEARTBEAT_HOURS * 3600 * 1000
	// Misma sesión ya enviada: no se repite (tampoco si LinkedIn la rechazó, para no insistir).
	if (!force && hash === state.lastHash && recent && ["ok", "invalid", "needs_proxy"].includes(state.status)) {
		return { ok: true, skipped: true }
	}

	let res, data
	try {
		res = await fetch(`${state.apiBase}/api/py/linkedin/session`, {
			method: "POST",
			headers: { "Content-Type": "application/json", "x-extension-token": state.token },
			body: JSON.stringify({
				cookies,
				user_agent: navigator.userAgent,
				accept_language: navigator.languages.join(","),
				source: `extension:${reason}`,
			}),
		})
		data = await res.json().catch(() => ({}))
	} catch (e) {
		await setState({ status: "error", error: `No se pudo contactar con el SDR: ${e.message}` })
		return { ok: false, error: e.message }
	}

	if (res.status === 401) {
		await setState({ status: "unpaired", token: null, error: data.detail || "Clave inválida: vuelve a conectar desde el panel" })
		return { ok: false, error: data.detail }
	}
	if (!res.ok || !data.ok) {
		const error = data.error || data.detail || `Error ${res.status}`
		const status = data.proxy_required ? "needs_proxy" : res.ok ? "invalid" : "error"
		await setState({ status, lastHash: hash, lastSyncAt: Date.now(), error })
		return { ok: false, error }
	}
	await setState({
		status: "ok",
		error: null,
		lastHash: hash,
		lastSyncAt: Date.now(),
		profile: data.profile?.name || null,
	})
	return { ok: true, changed: data.changed, profile: data.profile?.name }
}

// Si no hay sesión abre LinkedIn (como WaLead) y espera a que Enrique entre.
async function connect() {
	let cookies = await linkedinCookies()
	if (!cookies.li_at) {
		await chrome.tabs.create({ url: "https://www.linkedin.com/login", active: true })
		const start = Date.now()
		while (!cookies.li_at || !cookies.JSESSIONID) {
			if (Date.now() - start > LOGIN_TIMEOUT_MS) return { ok: false, error: "No se completó el login en LinkedIn en 5 minutos" }
			await new Promise((r) => setTimeout(r, 2000))
			cookies = await linkedinCookies()
		}
	}
	return sync("connect", true)
}

// ---------- eventos ----------

let debounce = null

chrome.cookies.onChanged.addListener(({ cookie }) => {
	if (!cookie.domain.endsWith("linkedin.com") || !KEY_COOKIES.includes(cookie.name)) return
	clearTimeout(debounce)
	debounce = setTimeout(() => sync("cookie_change"), 8000)
})

chrome.alarms.onAlarm.addListener((alarm) => {
	if (alarm.name === "sync") sync("alarm")
})

async function boot() {
	await chrome.alarms.create("sync", { periodInMinutes: 30 })
	await sync("startup")
}

chrome.runtime.onInstalled.addListener(boot)
chrome.runtime.onStartup.addListener(boot)

// Desde el panel (Ajustes): sólo las webs de externally_connectable llegan aquí.
chrome.runtime.onMessageExternal.addListener((msg, sender, reply) => {
	const origin = sender.origin || new URL(sender.url).origin
	if (!ALLOWED_APIS.includes(origin)) return false
	;(async () => {
		if (msg?.action === "get_version") {
			const s = await getState()
			return { ok: true, version: chrome.runtime.getManifest().version, paired: Boolean(s.token), status: s.status }
		}
		if (msg?.action === "pair" && typeof msg.token === "string" && msg.token.length >= 32) {
			// La URL del SDR es la de la web que empareja, no la que diga el mensaje.
			await setState({ apiBase: origin, token: msg.token, lastHash: null })
			return connect()
		}
		if (msg?.action === "sync") return sync("panel", true)
		return { ok: false, error: "Acción desconocida" }
	})().then(reply, (e) => reply({ ok: false, error: e.message }))
	return true
})

// Desde el popup.
chrome.runtime.onMessage.addListener((msg, sender, reply) => {
	if (sender.id !== chrome.runtime.id) return false
	;(async () => {
		if (msg?.action === "state") return getState()
		if (msg?.action === "sync") return sync("popup", true)
		if (msg?.action === "connect") return connect()
		if (msg?.action === "save") {
			if (!ALLOWED_APIS.includes(msg.apiBase)) return { ok: false, error: "URL del SDR no permitida" }
			await setState({ apiBase: msg.apiBase, token: msg.token, lastHash: null })
			return connect()
		}
		return { ok: false, error: "Acción desconocida" }
	})().then(reply, (e) => reply({ ok: false, error: e.message }))
	return true
})
