const $ = (sel, el = document) => el.querySelector(sel);
const app = $("#app");
const modal = $("#modal");
let toastEl;

function toast(msg, isError = false) {
  if (!toastEl) { toastEl = document.createElement("div"); document.body.appendChild(toastEl); }
  toastEl.className = `toast show${isError ? " error" : ""}`;
  toastEl.textContent = msg;
  setTimeout(() => toastEl.classList.remove("show"), 3500);
}

async function api(path, opts = {}) {
  const res = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" }, ...opts,
  });
  if (!res.ok) {
    let detail; try { detail = (await res.json()).detail; } catch { detail = res.statusText; }
    throw new Error(detail);
  }
  const ct = res.headers.get("content-type") || "";
  return ct.includes("json") ? res.json() : res.text();
}

const esc = (s) => String(s ?? "").replace(/[&<>"']/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const money = (n) => `$${Number(n).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;

function openModal(html) { $("#modal-body").innerHTML = html; modal.showModal(); }
modal.addEventListener("click", (e) => { if (e.target === modal) modal.close(); });

/* ---------------- accounts list ---------------- */

async function viewAccounts() {
  const accounts = await api("/accounts");
  app.innerHTML = `
    <div class="row spread" style="margin-bottom:14px">
      <h2 style="margin:0">Client accounts</h2>
      <button class="btn" id="add-account">+ Add account</button>
    </div>
    ${accounts.length ? "" : `<div class="card muted">No accounts yet. Add your first client account, then hit Sync to pull data and generate the first review queue.</div>`}
    ${accounts.map((a) => `
      <div class="card row spread">
        <div>
          <a class="btn-link" data-acct="${a.id}" style="font-size:15px">${esc(a.name)}</a>
          <div class="muted">${esc(a.vertical || "—")} · ${esc(a.service_area || "no service area")} · CID ${esc(a.customer_id)}</div>
        </div>
        <div class="row">
          <span class="badge ${a.mode}">${a.mode}</span>
          <span class="muted">${a.campaigns} campaigns</span>
          <span class="muted">${money(a.total_cost)} · ${a.total_conversions} conv</span>
          ${a.pending_proposals ? `<span class="badge warn">${a.pending_proposals} pending</span>` : ""}
        </div>
      </div>`).join("")}`;
  $("#add-account").onclick = showAddAccount;
  app.querySelectorAll("[data-acct]").forEach((el) =>
    el.onclick = () => viewAccount(+el.dataset.acct));
}

function showAddAccount() {
  openModal(`
    <h2>Add client account</h2>
    <label>Business name</label><input id="f-name" placeholder="Reyes Plumbing">
    <label>Google Ads customer ID</label><input id="f-cid" placeholder="111-222-3333">
    <label>Vertical</label><input id="f-vert" placeholder="plumbing, dental, HVAC…">
    <label>Service area</label><input id="f-area" placeholder="Springfield + 25mi">
    <label>Target CPA ($, optional — used by bid rules)</label><input id="f-cpa" type="number">
    <div class="row" style="margin-top:16px; justify-content:flex-end">
      <button class="btn ghost" onclick="modal.close()">Cancel</button>
      <button class="btn" id="f-save">Add account</button>
    </div>`);
  $("#f-save").onclick = async () => {
    try {
      await api("/accounts", { method: "POST", body: JSON.stringify({
        name: $("#f-name").value, customer_id: $("#f-cid").value,
        vertical: $("#f-vert").value, service_area: $("#f-area").value,
        target_cpa: $("#f-cpa").value ? +$("#f-cpa").value : null,
      })});
      modal.close(); toast("Account added — now Sync it."); viewAccounts();
    } catch (e) { toast(e.message, true); }
  };
}

/* ---------------- account detail ---------------- */

async function viewAccount(id) {
  const [accounts, campaigns, proposals] = await Promise.all([
    api("/accounts"), api(`/accounts/${id}/campaigns`),
    api(`/accounts/${id}/proposals?status=pending`),
  ]);
  const acct = accounts.find((a) => a.id === id);

  app.innerHTML = `
    <div class="row spread" style="margin-bottom:14px">
      <div>
        <a class="btn-link" id="back">← Accounts</a>
        <h2 style="margin:6px 0 0">${esc(acct.name)} <span class="badge ${acct.mode}">${acct.mode}</span></h2>
      </div>
      <div class="row">
        <button class="btn ghost" id="toggle-mode">Switch to ${acct.mode === "review" ? "automatic" : "review"} mode</button>
        <button class="btn ghost" id="dl-report">Report CSV</button>
        <button class="btn ghost" id="dl-audit">Audit</button>
        <button class="btn" id="new-campaign">+ New campaign</button>
        <button class="btn green" id="sync">Sync &amp; analyze</button>
      </div>
    </div>

    <div class="card">
      <h2>Review queue ${proposals.length ? `<span class="badge warn">${proposals.length}</span>` : ""}</h2>
      <div id="queue">${proposals.length ? "" : `<div class="muted">Queue is empty. Sync to re-analyze, or everything already conforms to the playbook.</div>`}</div>
    </div>

    ${campaigns.map((c) => `
      <div class="card">
        <div class="row spread">
          <h2 style="margin:0">${esc(c.name)}
            <span class="badge ${c.status === "ENABLED" ? "automatic" : "review"}">${c.status}</span></h2>
          <div class="row muted">
            <span>Budget ${money(c.daily_budget)}/day <span title="Budgets are immutable in this tool">🔒</span></span>
            <span>${esc(c.bidding_strategy)}</span>
            <span>geo: ${esc(c.geo_target_type)}</span>
            <button class="btn sm ghost toggle-camp" data-camp="${c.id}"
              data-status="${c.status === "ENABLED" ? "PAUSED" : "ENABLED"}">
              ${c.status === "ENABLED" ? "Pause" : "Enable"}</button>
          </div>
        </div>
        <h3>Keywords</h3>
        <table><tr><th>Ad group</th><th>Keyword</th><th>Match</th><th>Status</th>
          <th class="num">Bid</th><th class="num">Clicks</th><th class="num">Cost</th>
          <th class="num">Conv</th><th class="num">CPA</th><th></th></tr>
          ${c.keywords.map((k) => `<tr>
            <td>${esc(k.ad_group)}</td><td>${esc(k.text)}</td>
            <td><code>${esc(k.match_type)}</code></td><td>${esc(k.status)}</td>
            <td class="num">$${k.cpc_bid.toFixed(2)}</td>
            <td class="num">${k.clicks}</td><td class="num">${money(k.cost)}</td>
            <td class="num">${k.conversions}</td>
            <td class="num">${k.conversions ? money(k.cost / k.conversions) : "—"}</td>
            <td><button class="btn sm ghost kw-toggle" data-kw="${k.id}"
              data-status="${k.status === "ENABLED" ? "PAUSED" : "ENABLED"}">
              ${k.status === "ENABLED" ? "Pause" : "Enable"}</button></td>
          </tr>`).join("")}</table>
        ${c.search_terms.length ? `<h3>Search terms</h3>
        <table><tr><th>Term</th><th class="num">Clicks</th><th class="num">Cost</th><th class="num">Conv</th></tr>
        ${c.search_terms.map((t) => `<tr><td>${esc(t.term)}</td>
          <td class="num">${t.clicks}</td><td class="num">${money(t.cost)}</td>
          <td class="num">${t.conversions}</td></tr>`).join("")}</table>` : ""}
      </div>`).join("")}`;

  $("#back").onclick = viewAccounts;
  $("#sync").onclick = async () => {
    try {
      const r = await api(`/accounts/${id}/sync`, { method: "POST" });
      toast(`Synced. ${r.queued} proposal(s) queued, ${r.auto_applied} auto-applied.`);
      viewAccount(id);
    } catch (e) { toast(e.message, true); }
  };
  $("#toggle-mode").onclick = async () => {
    const mode = acct.mode === "review" ? "automatic" : "review";
    if (mode === "automatic" && !confirm(
      "Automatic mode applies non-budget changes without per-change approval. " +
      "Budgets stay locked either way. Enable for this account?")) return;
    await api(`/accounts/${id}`, { method: "PATCH", body: JSON.stringify({ mode }) });
    toast(`Mode set to ${mode}.`); viewAccount(id);
  };
  $("#dl-report").onclick = () => window.open(`/api/accounts/${id}/report.csv`);
  $("#dl-audit").onclick = () => window.open(`/api/accounts/${id}/audit.md`);
  $("#new-campaign").onclick = () => showCampaignBuilder(id);

  app.querySelectorAll(".kw-toggle").forEach((b) => b.onclick = async () => {
    try {
      await api(`/accounts/${id}/changes`, { method: "POST", body: JSON.stringify({
        change_type: "keyword_status", entity_ref: `keyword:${b.dataset.kw}`,
        payload: { status: b.dataset.status } })});
      viewAccount(id);
    } catch (e) { toast(e.message, true); }
  });
  app.querySelectorAll(".toggle-camp").forEach((b) => b.onclick = async () => {
    try {
      await api(`/accounts/${id}/changes`, { method: "POST", body: JSON.stringify({
        change_type: "campaign_status", entity_ref: `campaign:${b.dataset.camp}`,
        payload: { status: b.dataset.status } })});
      viewAccount(id);
    } catch (e) { toast(e.message, true); }
  });

  const queue = $("#queue");
  proposals.forEach((p) => {
    const el = document.createElement("div");
    el.className = "proposal";
    el.innerHTML = `
      <div class="row spread">
        <strong>${esc(p.rule)}</strong>
        <span class="muted">${esc(p.change_type)} · ${esc(p.entity_ref)}</span>
      </div>
      <div class="reason">${esc(p.reasoning)}</div>
      <div class="row">
        <code>${esc(JSON.stringify(p.payload))}</code>
        <button class="btn sm green">Approve</button>
        <button class="btn sm ghost">Edit &amp; approve</button>
        <button class="btn sm red">Reject</button>
      </div>`;
    const [ok, edit, no] = el.querySelectorAll("button");
    ok.onclick = async () => {
      try { await api(`/proposals/${p.id}/approve`, { method: "POST", body: "{}" });
            toast("Applied."); viewAccount(id); }
      catch (e) { toast(e.message, true); }
    };
    edit.onclick = async () => {
      const edited = prompt("Edit the change payload (JSON):", JSON.stringify(p.payload));
      if (edited === null) return;
      try { await api(`/proposals/${p.id}/approve`, { method: "POST",
            body: JSON.stringify({ payload: JSON.parse(edited) }) });
            toast("Applied with your edits."); viewAccount(id); }
      catch (e) { toast(e.message, true); }
    };
    no.onclick = async () => {
      await api(`/proposals/${p.id}/reject`, { method: "POST" });
      toast("Rejected."); viewAccount(id);
    };
    queue.appendChild(el);
  });
}

/* ---------------- campaign builder ---------------- */

function showCampaignBuilder(accountId) {
  openModal(`
    <h2>New search campaign</h2>
    <p class="muted" style="margin-top:-6px">Playbook enforced: phrase/exact only,
    presence-based geo, partners &amp; display off, starts paused, baseline negatives added.</p>
    <label>Campaign name</label><input id="c-name" placeholder="Plumbing - Drains - Springfield">
    <label>Daily budget ($ — set once, cannot be changed by this tool later)</label>
    <input id="c-budget" type="number" min="1">
    <div id="groups"></div>
    <a class="btn-link" id="add-group">+ Add ad group</a>
    <div class="row" style="margin-top:16px; justify-content:flex-end">
      <button class="btn ghost" onclick="modal.close()">Cancel</button>
      <button class="btn" id="c-save">Create (paused)</button>
    </div>`);
  const groups = $("#groups");
  const addGroup = () => {
    const g = document.createElement("div");
    g.className = "kwgroup";
    g.innerHTML = `
      <label>Ad group name</label><input class="g-name" placeholder="Drain Cleaning">
      <label>Keywords — one per line as <code>match:keyword</code> (match = phrase|exact)</label>
      <textarea class="g-kws" rows="3" placeholder="phrase:drain cleaning&#10;exact:drain cleaning springfield"></textarea>`;
    groups.appendChild(g);
  };
  addGroup();
  $("#add-group").onclick = addGroup;
  $("#c-save").onclick = async () => {
    const ad_groups = [...groups.querySelectorAll(".kwgroup")].map((g) => ({
      name: $(".g-name", g).value,
      keywords: $(".g-kws", g).value.split("\n").filter((l) => l.trim()).map((l) => {
        const [mt, ...rest] = l.split(":");
        return { match_type: mt.trim().toUpperCase(), text: rest.join(":").trim() };
      }),
    })).filter((g) => g.name && g.keywords.length);
    try {
      await api(`/accounts/${accountId}/campaigns`, { method: "POST",
        body: JSON.stringify({ name: $("#c-name").value,
          daily_budget: +$("#c-budget").value, ad_groups }) });
      modal.close(); toast("Campaign created (paused) — review, then enable.");
      viewAccount(accountId);
    } catch (e) { toast(e.message, true); }
  };
}

/* ---------------- audit log ---------------- */

async function viewAuditLog() {
  const entries = await api("/audit-log");
  app.innerHTML = `<div class="card"><h2>Audit log</h2>
    ${entries.length ? `<table><tr><th>When (UTC)</th><th>Actor</th><th>Change</th><th>Entity</th><th>Detail</th></tr>
    ${entries.map((e) => `<tr>
      <td>${e.created_at.replace("T", " ").slice(0, 16)}</td>
      <td>${esc(e.actor)}</td><td><code>${esc(e.change_type)}</code></td>
      <td>${esc(e.entity_ref)}</td>
      <td class="muted">${esc(JSON.stringify(e.detail.payload ?? e.detail))}</td>
    </tr>`).join("")}</table>` : `<div class="muted">No changes recorded yet.</div>`}</div>`;
}

/* ---------------- agent chat ---------------- */

const chatHistory = [];

async function viewAgent() {
  app.innerHTML = `<div class="card">
    <h2>Agent</h2>
    <p class="muted" style="margin-top:-8px">Ask in plain language — “audit Reyes Plumbing”,
    “draft a campaign for the dental client”, “what's pending review?”.
    The agent uses the same guarded tools as the dashboard: it can never touch budgets,
    and in review mode its changes also land in the queue.</p>
    <div id="chat">
      <div id="chat-log">${chatHistory.map((m) =>
        `<div class="msg ${m.role}">${esc(m.content)}</div>`).join("")}</div>
      <div class="row">
        <input id="chat-in" placeholder="Message the agent…" style="flex:1">
        <button class="btn" id="chat-send">Send</button>
      </div>
    </div></div>`;
  const log = $("#chat-log");
  log.scrollTop = log.scrollHeight;
  const send = async () => {
    const text = $("#chat-in").value.trim();
    if (!text) return;
    $("#chat-in").value = "";
    chatHistory.push({ role: "user", content: text });
    log.innerHTML += `<div class="msg user">${esc(text)}</div>`;
    log.scrollTop = log.scrollHeight;
    try {
      const r = await api("/agent/chat", { method: "POST",
        body: JSON.stringify({ messages: chatHistory }) });
      chatHistory.push({ role: "assistant", content: r.reply });
      log.innerHTML += `<div class="msg assistant">${esc(r.reply)}</div>`;
    } catch (e) {
      log.innerHTML += `<div class="msg assistant">⚠ ${esc(e.message)}</div>`;
    }
    log.scrollTop = log.scrollHeight;
  };
  $("#chat-send").onclick = send;
  $("#chat-in").onkeydown = (e) => { if (e.key === "Enter") send(); };
}

/* ---------------- nav ---------------- */

const views = { accounts: viewAccounts, auditlog: viewAuditLog, agent: viewAgent };
document.querySelectorAll("nav button").forEach((b) => b.onclick = () => {
  document.querySelectorAll("nav button").forEach((x) => x.classList.remove("active"));
  b.classList.add("active");
  views[b.dataset.view]();
});
viewAccounts();
