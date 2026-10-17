const LABELS = {
	ok: ["Conectada", "ok"],
	logged_out: ["Sin sesión en LinkedIn", "mid"],
	invalid: ["LinkedIn la rechaza", "bad"],
	error: ["Error", "bad"],
	unpaired: ["Sin conectar al panel", "mid"],
}

const $ = (id) => document.getElementById(id)
const send = (msg) => chrome.runtime.sendMessage(msg)

async function render(result) {
	const s = await send({ action: "state" })
	const [label, cls] = LABELS[s.status] || ["…", "mid"]
	$("status").textContent = label
	$("status").className = `pill ${cls}`
	$("profile").textContent = s.profile || ""
	$("last").textContent = s.lastSyncAt ? `Última sincronización: ${new Date(s.lastSyncAt).toLocaleString("es-ES")}` : ""
	$("error").textContent = result?.error || (s.status === "ok" ? "" : s.error || "")
	$("api").value = s.apiBase
}

async function run(button, msg) {
	button.disabled = true
	try {
		await render(await send(msg))
	} finally {
		button.disabled = false
	}
}

$("sync").onclick = () => run($("sync"), { action: "sync" })
$("connect").onclick = () => run($("connect"), { action: "connect" })
$("save").onclick = () => run($("save"), { action: "save", apiBase: $("api").value, token: $("token").value.trim() })
render()
