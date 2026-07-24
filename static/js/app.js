/* ═══════════════════════════════════════════
   WoL Dashboard — Frontend SPA v2
═══════════════════════════════════════════ */

// ── State ──
let devices      = [];
let scanResults  = [];
let selectedIds  = new Set();
let scanSelected = new Set();
let currentPage  = "dashboard";
let editDeviceId = null;
let statusFilter = "all";
let pollTimer    = null;
let scanSortCol  = "ip";
let scanSortAsc  = true;

// ── Service map (port → display info) ──
const SERVICE_MAP = {
  22:   { label: "SSH",      color: "#6b7280", url: null },
  80:   { label: "HTTP",     color: "#3b82f6", url: "http://{ip}" },
  443:  { label: "HTTPS",    color: "#10b981", url: "https://{ip}" },
  3389: { label: "RDP",      color: "#8b5cf6", url: null },
  5900: { label: "VNC",      color: "#f59e0b", url: null },
  8006: { label: "Proxmox",  color: "#e57000", url: "https://{ip}:8006" },
  8080: { label: "HTTP-Alt", color: "#3b82f6", url: "http://{ip}:8080" },
  8443: { label: "HTTPS-Alt",color: "#10b981", url: "https://{ip}:8443" },
  9090: { label: "Cockpit",  color: "#06b6d4", url: "https://{ip}:9090" },
};

function servicePills(openPortsJson, ip) {
  let ports;
  try { ports = JSON.parse(openPortsJson || "[]"); } catch { ports = []; }
  if (!ports.length) return "";
  return ports.map(p => {
    const svc   = SERVICE_MAP[p];
    const label = svc ? svc.label : `Port ${p}`;
    const color = svc ? svc.color : "var(--text-3)";
    const url   = svc?.url ? svc.url.replace("{ip}", encodeURIComponent(ip)) : null;
    return url
      ? `<a class="service-pill" href="${esc(url)}" target="_blank" rel="noopener" style="--svc-color:${color}" title="Öffne ${label}" onclick="event.stopPropagation()">${esc(label)}</a>`
      : `<span class="service-pill" style="--svc-color:${color}" title="Port ${p}">${esc(label)}</span>`;
  }).join("");
}

// ── API ──
async function api(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(err.error || res.statusText);
  }
  return res.json();
}

// ── Toast ──
function toast(msg, type = "info") {
  const c = document.getElementById("toast-container");
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.innerHTML = `<span class="toast-icon"></span><span>${esc(msg)}</span>`;
  c.appendChild(el);
  setTimeout(() => el.remove(), 3800);
}

function fmt_dt(iso) {
  if (!iso) return "—";
  return new Date(iso + (iso.endsWith("Z") ? "" : "Z")).toLocaleString("de-DE");
}

function esc(s) {
  return String(s ?? "")
    .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")
    .replace(/"/g,"&quot;").replace(/'/g,"&#39;");
}

function dlBlob(content, mime, filename) {
  const url = URL.createObjectURL(new Blob([content], { type: mime }));
  Object.assign(document.createElement("a"), { href: url, download: filename }).click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// ── Clock ──
function tickClock() {
  const el = document.getElementById("topbar-clock");
  if (el) el.textContent = new Date().toLocaleTimeString("de-DE");
}
setInterval(tickClock, 1000);
tickClock();

// ── Theme ──
function toggleTheme() {
  const html = document.documentElement;
  const next = html.getAttribute("data-theme") === "dark" ? "light" : "dark";
  html.setAttribute("data-theme", next);
  localStorage.setItem("wol-theme", next);
  updateThemeIcon(next);
}
function updateThemeIcon(t) {
  const icon = document.getElementById("theme-icon");
  if (!icon) return;
  icon.innerHTML = t === "dark"
    ? `<circle cx="12" cy="12" r="4"/>
       <path d="M12 2v2m0 16v2M4.22 4.22l1.42 1.42m12.72 12.72 1.42 1.42M2 12h2m16 0h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/>`
    : `<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>`;
}
(function initTheme() {
  const t = localStorage.getItem("wol-theme") || "dark";
  document.documentElement.setAttribute("data-theme", t);
  updateThemeIcon(t);
})();

// ── Navigation ──
const PAGE_TITLES = {
  dashboard: "Dashboard",
  scan:      "Netz-Scan",
  history:   "Verlauf",
  settings:  "Einstellungen",
};

function showPage(name, navEl) {
  document.querySelectorAll(".page").forEach(p => p.classList.remove("active"));
  document.querySelectorAll(".nav-item").forEach(n => n.classList.remove("active"));
  document.getElementById("page-" + name).classList.add("active");
  if (navEl) navEl.classList.add("active");
  else document.querySelector(`[data-page="${name}"]`)?.classList.add("active");
  document.getElementById("page-title").textContent = PAGE_TITLES[name] || name;
  currentPage = name;
  if (name === "history")  loadHistory();
  if (name === "settings") loadSettings();
  if (name === "scan")     loadScanResults();
}

function refreshCurrent() {
  if (currentPage === "dashboard") loadDevices();
  if (currentPage === "scan")      loadScanResults();
  if (currentPage === "history")   loadHistory();
  if (currentPage === "settings")  loadSettings();
}

// ── Dashboard ──
async function loadDevices() {
  try {
    devices = await api("GET", "/api/devices");
    renderDeviceGrid();
    updateStats();
    updateGroupFilter();
  } catch (e) {
    toast("Geräte konnten nicht geladen werden: " + e.message, "error");
  }
}

function updateStats() {
  const online     = devices.filter(d => d.is_online).length;
  const offline    = devices.length - online;
  const scheduled  = devices.filter(d => d.has_schedule).length;
  const pct        = devices.length ? Math.round(online / devices.length * 100) : 0;

  document.getElementById("stat-total").textContent     = devices.length;
  document.getElementById("stat-online").textContent    = online;
  document.getElementById("stat-offline").textContent   = offline;
  document.getElementById("stat-scheduled").textContent = scheduled || "—";
  const bar = document.getElementById("online-bar");
  if (bar) bar.style.width = pct + "%";
}

function updateGroupFilter() {
  const sel = document.getElementById("group-filter");
  const dl  = document.getElementById("group-list");
  const cur = sel.value;
  const groups = [...new Set(devices.map(d => d.group_name).filter(Boolean))].sort();
  sel.innerHTML = '<option value="">Alle Gruppen</option>' +
    groups.map(g => `<option value="${esc(g)}">${esc(g)}</option>`).join("");
  if (groups.includes(cur)) sel.value = cur;
  if (dl) dl.innerHTML = groups.map(g => `<option value="${esc(g)}">`).join("");
}

function setFilter(f, el) {
  statusFilter = f;
  document.querySelectorAll(".filter-tabs .tab").forEach(c => c.classList.remove("active"));
  el.classList.add("active");
  filterDevices();
}

function filterDevices() {
  renderDeviceGrid();
}

function filteredDevices() {
  const q     = (document.getElementById("search-input")?.value || "").toLowerCase();
  const group = document.getElementById("group-filter")?.value || "";
  return devices.filter(d => {
    if (q && !d.name.toLowerCase().includes(q) &&
        !String(d.ip || "").includes(q) &&
        !String(d.mac || "").toLowerCase().includes(q)) return false;
    if (group && d.group_name !== group) return false;
    if (statusFilter === "online"  && !d.is_online)  return false;
    if (statusFilter === "offline" &&  d.is_online)  return false;
    return true;
  });
}

function renderDeviceGrid() {
  const grid = document.getElementById("device-grid");
  const list = filteredDevices();

  if (!list.length) {
    const isEmpty = !devices.length;
    grid.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round">
            <rect x="2" y="3" width="20" height="14" rx="2"/><polyline points="8 21 12 17 16 21"/>
          </svg>
        </div>
        <div class="empty-title">${isEmpty ? "Noch keine Geräte" : "Keine Ergebnisse"}</div>
        <div class="empty-text">${isEmpty
          ? "Füge Geräte über den Netz-Scan hinzu oder klicke auf das + unten rechts."
          : "Versuche andere Suchbegriffe oder Filter."}</div>
        ${isEmpty ? `<button class="btn btn-primary" onclick="showPage('scan',document.querySelector('[data-page=scan]'))">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>Netz scannen</button>` : ""}
      </div>`;
    return;
  }

  // Group by group_name
  const grouped = {};
  list.forEach(d => (grouped[d.group_name || "Standard"] = grouped[d.group_name || "Standard"] || []).push(d));

  let html = "";
  for (const [grp, items] of Object.entries(grouped)) {
    html += `<div class="group-label">
      <span class="group-label-text">${esc(grp)}</span>
      <span class="group-label-line"></span>
    </div>`;
    html += items.map(d => deviceCard(d)).join("");
  }
  grid.innerHTML = html;

  // Attach click listeners
  grid.querySelectorAll(".device-card").forEach(card => {
    const id = +card.dataset.id;
    card.addEventListener("click", e => {
      if (e.target.closest(".card-actions")) return;
      toggleSelect(id);
    });
  });

  // Re-apply selection state
  selectedIds.forEach(id => {
    const c = grid.querySelector(`[data-id="${id}"]`);
    if (c) {
      c.classList.add("selected");
      const ind = c.querySelector(".card-select-indicator");
      if (ind) ind.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" style="width:10px;height:10px"><polyline points="20 6 9 17 4 12"/></svg>`;
    }
  });
}

function deviceCard(d) {
  const onCls  = d.is_online ? "online" : "offline";
  const portChecks = JSON.parse(d.port_checks || "[]");
  const portPills  = portChecks.map(p =>
    `<span class="port-pill">${esc(String(p))}</span>`).join("");

  return `
<div class="device-card ${onCls}" data-id="${d.id}">
  <div class="card-stripe"></div>
  <div class="card-select-indicator"></div>
  <div class="card-body">
    <div class="card-top">
      <div class="device-icon-wrap">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round">
          <rect x="2" y="3" width="20" height="14" rx="2"/><polyline points="8 21 12 17 16 21"/>
        </svg>
      </div>
      <div class="card-title-area">
        <div class="device-name">${esc(d.name)}</div>
        ${d.group_name ? `<span class="device-group-tag">${esc(d.group_name)}</span>` : ""}
      </div>
      <span class="status-pill ${onCls}">
        <span class="status-dot ${onCls}"></span>
        ${d.is_online ? "Online" : "Offline"}
      </span>
    </div>
    <div class="device-meta">
      <div class="meta-row">
        <span class="meta-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/>
            <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
          </svg>
        </span>
        <span class="meta-val">${esc(d.ip || "—")}</span>
      </div>
      <div class="meta-row">
        <span class="meta-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round">
            <rect x="5" y="2" width="14" height="20" rx="2"/><line x1="12" y1="18" x2="12.01" y2="18"/>
          </svg>
        </span>
        <span class="meta-val">${esc(d.mac || "—")}</span>
      </div>
      ${d.last_seen ? `<div class="meta-row">
        <span class="meta-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
          </svg>
        </span>
        <span style="font-size:.72rem;color:var(--text-3)">${fmt_dt(d.last_seen)}</span>
      </div>` : ""}
    </div>
    ${portPills ? `<div class="port-pills">${portPills}</div>` : ""}
    ${servicePills(d.open_ports, d.ip || "") ? `<div class="service-pills">${servicePills(d.open_ports, d.ip || "")}</div>` : ""}
    ${d.notes ? `<div class="device-notes">${esc(d.notes)}</div>` : ""}
  </div>
  <div class="card-actions">
    <button class="btn-wake-card" onclick="wakeDevice(${d.id});event.stopPropagation()">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round">
        <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
      </svg>
      Wecken
    </button>
    <button class="card-icon-btn" title="Bearbeiten" onclick="openEditModal(${d.id});event.stopPropagation()">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round">
        <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
        <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
      </svg>
    </button>
    <button class="card-icon-btn danger" title="Entfernen" onclick="deleteDevice(${d.id});event.stopPropagation()">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/>
        <path d="M10 11v6m4-6v6"/><path d="M9 6V4h6v2"/>
      </svg>
    </button>
  </div>
</div>`;
}

function toggleSelect(id) {
  const card = document.querySelector(`[data-id="${id}"]`);
  if (selectedIds.has(id)) {
    selectedIds.delete(id);
    card?.classList.remove("selected");
    if (card) card.querySelector(".card-select-indicator").innerHTML = "";
  } else {
    selectedIds.add(id);
    card?.classList.add("selected");
    if (card) card.querySelector(".card-select-indicator").innerHTML =
      `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" style="width:10px;height:10px"><polyline points="20 6 9 17 4 12"/></svg>`;
  }
  updateBulkBar();
}

function updateBulkBar() {
  const bar = document.getElementById("bulk-bar");
  if (selectedIds.size > 0) {
    bar.classList.remove("hidden");
    document.getElementById("bulk-count").textContent = selectedIds.size;
  } else {
    bar.classList.add("hidden");
  }
}

function clearSelection() {
  selectedIds.clear();
  updateBulkBar();
  renderDeviceGrid();
}

async function bulkWake() {
  if (!selectedIds.size) return;
  try {
    await api("POST", "/api/wake/bulk", { ids: [...selectedIds] });
    toast(`Magische Pakete gesendet an ${selectedIds.size} Gerät(e)`, "success");
    selectedIds.clear();
    updateBulkBar();
    renderDeviceGrid();
  } catch (e) {
    toast("Fehler: " + e.message, "error");
  }
}

async function wakeDevice(id) {
  const dev = devices.find(d => d.id === id);
  try {
    await api("POST", `/api/devices/${id}/wake`);
    toast(`Magisches Paket gesendet an ${dev?.name || id}`, "success");
    if (dev && !dev.is_online) watchForOnline(id, dev.name);
  } catch (e) {
    toast("Wake fehlgeschlagen: " + e.message, "error");
  }
}

function watchForOnline(id, name) {
  let attempts = 0;
  const t = setInterval(async () => {
    if (++attempts > 30) { clearInterval(t); return; }
    const fresh = await api("GET", "/api/devices").catch(() => []);
    const dev = fresh.find(d => d.id === id);
    if (dev?.is_online) {
      clearInterval(t);
      toast(`${name} ist jetzt online!`, "success");
      if (Notification.permission === "granted") new Notification(`${name} ist jetzt online!`);
      devices = fresh;
      renderDeviceGrid();
      updateStats();
    }
  }, 10000);
}

async function deleteDevice(id) {
  const dev = devices.find(d => d.id === id);
  if (!confirm(`Gerät "${dev?.name}" wirklich entfernen?`)) return;
  try {
    await api("DELETE", `/api/devices/${id}`);
    toast("Gerät entfernt", "info");
    selectedIds.delete(id);
    updateBulkBar();
    loadDevices();
  } catch (e) {
    toast("Fehler: " + e.message, "error");
  }
}

// ── Modal ──
function openEditModal(id) {
  editDeviceId = id;
  document.getElementById("modal-title").textContent = id ? "Gerät bearbeiten" : "Gerät hinzufügen";
  document.getElementById("modal-name").value      = "";
  document.getElementById("modal-mac").value       = "";
  document.getElementById("modal-ip").value        = "";
  document.getElementById("modal-broadcast").value = "";
  document.getElementById("modal-group").value     = "";
  document.getElementById("modal-notes").value     = "";
  document.getElementById("modal-schedule-list").innerHTML =
    `<div style="padding:10px 12px;font-size:.78rem;color:var(--text-3)">Erst nach dem Speichern verfügbar</div>`;
  document.getElementById("schedule-add-area").style.display = "none";

  if (id) {
    const dev = devices.find(d => d.id === id);
    if (dev) {
      document.getElementById("modal-name").value      = dev.name;
      document.getElementById("modal-mac").value       = dev.mac;
      document.getElementById("modal-ip").value        = dev.ip || "";
      document.getElementById("modal-broadcast").value = dev.broadcast || "";
      document.getElementById("modal-group").value     = dev.group_name || "";
      document.getElementById("modal-notes").value     = dev.notes || "";
      document.getElementById("schedule-add-area").style.display = "";
      loadSchedulesInModal(id);
    }
  }
  document.getElementById("device-modal").classList.remove("hidden");
}

function closeModal() {
  document.getElementById("device-modal").classList.add("hidden");
  editDeviceId = null;
}

document.getElementById("device-modal").addEventListener("click", e => {
  if (e.target === e.currentTarget) closeModal();
});

async function saveDevice() {
  const name      = document.getElementById("modal-name").value.trim();
  const mac       = document.getElementById("modal-mac").value.trim();
  const ip        = document.getElementById("modal-ip").value.trim();
  const broadcast = document.getElementById("modal-broadcast").value.trim();
  const group     = document.getElementById("modal-group").value.trim() || "Standard";
  const notes     = document.getElementById("modal-notes").value.trim();
  if (!name || !mac) { toast("Name und MAC sind Pflichtfelder", "error"); return; }
  try {
    if (editDeviceId) {
      await api("PUT", `/api/devices/${editDeviceId}`, { name, ip, broadcast, group_name: group, notes });
    } else {
      await api("POST", "/api/devices", { name, mac, ip, broadcast, group_name: group, notes });
    }
    toast("Gespeichert", "success");
    closeModal();
    loadDevices();
  } catch (e) {
    toast("Fehler: " + e.message, "error");
  }
}

async function loadSchedulesInModal(deviceId) {
  const list = document.getElementById("modal-schedule-list");
  try {
    const schedules = await api("GET", `/api/devices/${deviceId}/schedules`);
    if (!schedules.length) {
      list.innerHTML = `<div style="padding:10px 12px;font-size:.78rem;color:var(--text-3)">Noch keine Zeitpläne</div>`;
      return;
    }
    list.innerHTML = schedules.map(s => `
      <div class="schedule-row" data-sid="${s.id}">
        <span class="schedule-cron">${esc(s.cron_expr)}</span>
        <span style="flex:1;color:var(--text-2);font-size:.8rem">${esc(s.label || "")}</span>
        <button class="card-icon-btn danger btn-sm" style="width:26px;height:26px" onclick="deleteSchedule(${s.id},${deviceId})">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" style="width:12px;height:12px">
            <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
      </div>`).join("");
  } catch {
    list.innerHTML = `<div style="padding:10px 12px;font-size:.78rem;color:var(--red)">Fehler beim Laden</div>`;
  }
}

async function deleteSchedule(sid, deviceId) {
  await api("DELETE", `/api/schedules/${sid}`);
  toast("Zeitplan entfernt", "info");
  loadSchedulesInModal(deviceId);
}

async function addSchedule() {
  if (!editDeviceId) { toast("Gerät zuerst speichern", "info"); return; }
  const cron  = document.getElementById("sched-cron").value.trim();
  const label = document.getElementById("sched-label").value.trim();
  if (!cron) { toast("Cron-Ausdruck eingeben", "error"); return; }
  try {
    await api("POST", `/api/devices/${editDeviceId}/schedules`, { cron_expr: cron, label });
    document.getElementById("sched-cron").value  = "";
    document.getElementById("sched-label").value = "";
    loadSchedulesInModal(editDeviceId);
    toast("Zeitplan hinzugefügt", "success");
  } catch (e) {
    toast("Fehler: " + e.message, "error");
  }
}

// ── Scan ──
async function loadScanResults() {
  try {
    const data = await api("GET", "/api/scan/results");
    scanResults = data.results || [];
    const status = data.status || {};
    const pst    = data.port_scan_status || {};
    renderScanTable();
    let txt = "Bereit";
    if (status.running) txt = "Scan läuft…";
    else if (status.last_run) txt = `Letzter Scan: ${fmt_dt(status.last_run)} · ${status.found} Geräte`;
    document.getElementById("scan-status").textContent = txt;

    const pEl = document.getElementById("port-scan-status");
    if (pEl) {
      if (pst.running) {
        pEl.style.display = "";
        pEl.textContent = "Port-Scan läuft…";
      } else if (pst.last_run) {
        pEl.style.display = "";
        pEl.textContent = `Ports: ${fmt_dt(pst.last_run)} · ${pst.scanned} IPs`;
      } else {
        pEl.style.display = "none";
      }
    }

    const cnt = document.getElementById("scan-count");
    if (cnt) cnt.textContent = scanResults.length ? `${scanResults.length} Hosts` : "";
  } catch (e) {
    toast("Scan-Ergebnisse konnten nicht geladen werden", "error");
  }
}

function ipToNum(ip) {
  return (ip || "").split(".").reduce((acc, oct) => (acc << 8) + parseInt(oct || 0, 10), 0) >>> 0;
}

function setScanSort(col) {
  if (scanSortCol === col) {
    scanSortAsc = !scanSortAsc;
  } else {
    scanSortCol = col;
    scanSortAsc = true;
  }
  ["ip","mac","hostname","vendor"].forEach(c => {
    const el = document.getElementById("sort-" + c);
    if (!el) return;
    el.textContent = c === scanSortCol ? (scanSortAsc ? "▲" : "▼") : "";
  });
  renderScanTable();
}

function sortedScanResults() {
  const col = scanSortCol;
  const asc = scanSortAsc;
  return [...scanResults].sort((a, b) => {
    let av = a[col] || "", bv = b[col] || "";
    if (col === "ip") {
      av = ipToNum(av); bv = ipToNum(bv);
      return asc ? av - bv : bv - av;
    }
    av = av.toLowerCase(); bv = bv.toLowerCase();
    return asc ? av.localeCompare(bv) : bv.localeCompare(av);
  });
}

function renderScanTable() {
  const tbody = document.getElementById("scan-tbody");
  const knownMacs = new Set(devices.map(d => (d.mac || "").toUpperCase()));
  if (!scanResults.length) {
    tbody.innerHTML = `<tr><td colspan="7" class="empty-cell">Noch kein Scan durchgeführt. Klicke "Scan starten".</td></tr>`;
    return;
  }
  tbody.innerHTML = sortedScanResults().map(h => {
    const already  = knownMacs.has((h.mac || "").toUpperCase());
    const pills    = servicePills(h.open_ports, h.ip || "");
    const pillsHtml = pills
      ? `<div class="service-pills">${pills}</div>`
      : `<span style="color:var(--text-4);font-size:.75rem">—</span>`;
    const actionHtml = already
      ? `<span style="color:var(--green);font-size:.78rem;font-weight:600">✓ Verwaltet</span>`
      : `<button class="btn btn-secondary btn-sm" onclick="prefillFromScan('${esc(h.mac)}','${esc(h.ip)}','${esc(h.hostname || '')}')">+ Hinzufügen</button>`;
    return `<tr>
      <td>
        <input type="checkbox" class="scan-cb" style="accent-color:var(--blue)"
          data-mac="${esc(h.mac)}" data-ip="${esc(h.ip)}" data-host="${esc(h.hostname || '')}"
          ${already ? "disabled title='Bereits verwaltet'" : ""}>
      </td>
      <td class="mono">${esc(h.ip)}</td>
      <td class="mono" style="color:var(--text-2)">${esc(h.mac || "—")}</td>
      <td>${esc(h.hostname || "—")}</td>
      <td style="color:var(--text-3)">${esc(h.vendor || "—")}</td>
      <td>${pillsHtml}</td>
      <td>${actionHtml}</td>
    </tr>`;
  }).join("");

  tbody.querySelectorAll(".scan-cb").forEach(cb => {
    cb.addEventListener("change", updateScanAddBar);
  });
}

function updateScanAddBar() {
  const checked = document.querySelectorAll(".scan-cb:checked");
  scanSelected = new Set([...checked].map(cb => cb.dataset.mac));
  const bar = document.getElementById("scan-add-bar");
  const cnt = document.getElementById("scan-add-count");
  bar.style.display = scanSelected.size ? "" : "none";
  if (cnt) cnt.textContent = scanSelected.size;
}

function toggleAllScan(checked) {
  document.querySelectorAll(".scan-cb:not(:disabled)").forEach(cb => {
    cb.checked = checked;
  });
  updateScanAddBar();
}

function prefillFromScan(mac, ip, host) {
  openEditModal(null);
  document.getElementById("modal-mac").value  = mac;
  document.getElementById("modal-ip").value   = ip;
  document.getElementById("modal-name").value = host || ip;
}

async function startScan() {
  const btn = document.getElementById("scan-btn");
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner"></span> Scannen…`;
  document.getElementById("scan-status").textContent = "Scan läuft…";
  try {
    await api("POST", "/api/scan/start");
    const t = setInterval(async () => {
      try {
        const data = await api("GET", "/api/scan/results");
        if (!data.status.running) {
          clearInterval(t);
          scanResults = data.results || [];
          renderScanTable();
          document.getElementById("scan-status").textContent =
            `Fertig · ${data.status.found} Geräte · ${fmt_dt(data.status.last_run)}`;
          const cnt = document.getElementById("scan-count");
          if (cnt) cnt.textContent = `${scanResults.length} Hosts`;
          btn.disabled = false;
          btn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg> Scan starten`;
          toast(`Scan abgeschlossen · ${data.status.found} Geräte gefunden`, "success");
        }
      } catch {}
    }, 3000);
  } catch (e) {
    toast("Scan konnte nicht gestartet werden: " + e.message, "error");
    btn.disabled = false;
    btn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg> Scan starten`;
  }
}

async function startPortScan() {
  const btn = document.getElementById("port-scan-btn");
  const pEl = document.getElementById("port-scan-status");
  btn.disabled = true;
  if (pEl) { pEl.style.display = ""; pEl.textContent = "Port-Scan läuft…"; }
  try {
    await api("POST", "/api/scan/ports");
    const t = setInterval(async () => {
      try {
        const st = await api("GET", "/api/scan/ports/status");
        if (!st.running) {
          clearInterval(t);
          btn.disabled = false;
          if (pEl) pEl.textContent = `Ports: ${fmt_dt(st.last_run)} · ${st.scanned} IPs`;
          toast(`Port-Scan abgeschlossen · ${st.scanned} IPs gescannt`, "success");
          loadScanResults();
        }
      } catch (ignore) { /* poll — errors are transient */ }
    }, 3000);
  } catch (e) {
    toast("Port-Scan konnte nicht gestartet werden: " + e.message, "error");
    btn.disabled = false;
  }
}

async function addSelectedFromScan() {
  const cbs = document.querySelectorAll(".scan-cb:checked");
  let count = 0;
  for (const cb of cbs) {
    if (!cb.dataset.mac) continue;
    await api("POST", "/api/devices", {
      name: cb.dataset.host || cb.dataset.ip,
      mac: cb.dataset.mac,
      ip:  cb.dataset.ip,
      group_name: "Entdeckt",
    }).catch(() => {});
    count++;
  }
  toast(`${count} Gerät(e) hinzugefügt`, "success");
  scanSelected.clear();
  document.getElementById("scan-add-bar").style.display = "none";
  document.getElementById("scan-check-all").checked = false;
  await loadDevices();
  renderScanTable();
}

// ── History ──
async function loadHistory() {
  try {
    const hist = await api("GET", "/api/history?limit=100");
    const tbody = document.getElementById("history-tbody");
    const cnt   = document.getElementById("history-count");
    if (cnt) cnt.textContent = hist.length ? `${hist.length} Einträge` : "";
    if (!hist.length) {
      tbody.innerHTML = `<tr><td colspan="5" class="empty-cell">Noch kein Verlauf vorhanden.</td></tr>`;
      return;
    }
    tbody.innerHTML = hist.map(h => `
      <tr>
        <td style="color:var(--text-3);white-space:nowrap">${fmt_dt(h.ts)}</td>
        <td style="font-weight:600">${esc(h.device_name || "—")}</td>
        <td class="mono" style="color:var(--text-2)">${esc(h.mac || "—")}</td>
        <td><span class="badge-trigger ${esc(h.triggered_by)}">${esc(h.triggered_by)}</span></td>
        <td>${h.success
          ? `<span style="color:var(--green);font-weight:600">✓ OK</span>`
          : `<span style="color:var(--red);font-weight:600">✗ Fehler</span>`
        }</td>
      </tr>`).join("");
  } catch (e) {
    toast("Verlauf konnte nicht geladen werden", "error");
  }
}

async function exportHistoryCsv() {
  try {
    const hist = await api("GET", "/api/history?limit=9999");
    const csv = ["Zeitpunkt,Gerät,MAC,Auslöser,Status",
      ...hist.map(h => `"${h.ts}","${h.device_name}","${h.mac}","${h.triggered_by}","${h.success ? "OK" : "Fehler"}"`)
    ].join("\n");
    dlBlob(csv, "text/csv", "wol-history.csv");
  } catch (e) {
    toast("Export fehlgeschlagen", "error");
  }
}

// ── Settings ──
async function loadSettings() {
  try {
    const cfg = await api("GET", "/api/config");
    const networks = Array.isArray(cfg.scan_networks) ? cfg.scan_networks : [cfg.scan_networks || ""];
    document.getElementById("cfg-networks").value  = networks.join("\n");
    document.getElementById("cfg-broadcast").value = cfg.broadcast_address || "";
    document.getElementById("cfg-port").value      = cfg.wol_port || 9;
    document.getElementById("cfg-interval").value  = cfg.scan_interval_seconds || 60;
    document.getElementById("cfg-repo").value      = cfg.github_repo || "";
  } catch (e) {
    toast("Konfiguration konnte nicht geladen werden", "error");
  }
}

async function saveSettings() {
  const cfg = {
    scan_networks:         document.getElementById("cfg-networks").value,
    broadcast_address:     document.getElementById("cfg-broadcast").value.trim(),
    wol_port:              +document.getElementById("cfg-port").value,
    scan_interval_seconds: +document.getElementById("cfg-interval").value,
    github_repo:           document.getElementById("cfg-repo").value.trim(),
  };
  try {
    await api("POST", "/api/config", cfg);
    toast("Einstellungen gespeichert", "success");
  } catch (e) {
    toast("Fehler: " + e.message, "error");
  }
}

function requestNotifPerm() {
  if (!("Notification" in window)) { toast("Browser unterstützt keine Benachrichtigungen", "error"); return; }
  Notification.requestPermission().then(p => {
    toast(p === "granted" ? "Benachrichtigungen aktiviert" : "Benachrichtigungen abgelehnt",
          p === "granted" ? "success" : "error");
  });
}

// ── Import / Export ──
async function exportDevices() {
  try {
    const devs = await api("GET", "/api/devices");
    dlBlob(JSON.stringify(devs, null, 2), "application/json", "wol-devices.json");
  } catch (e) {
    toast("Export fehlgeschlagen", "error");
  }
}

async function importDevices(e) {
  const file = e.target.files[0];
  if (!file) return;
  const text = await file.text();
  let list;
  try { list = JSON.parse(text); } catch { toast("Ungültige JSON-Datei", "error"); return; }
  if (!Array.isArray(list)) { toast("Dateiformat ungültig", "error"); return; }
  let count = 0;
  for (const dev of list) {
    if (!dev.mac || !dev.name) continue;
    await api("POST", "/api/devices", dev).catch(() => {});
    count++;
  }
  toast(`${count} Gerät(e) importiert`, "success");
  loadDevices();
  e.target.value = "";
}

// ── Update check ──
async function checkUpdate() {
  const info_box = document.getElementById("update-info");
  const cmds_box = document.getElementById("update-cmds");
  const badge    = document.getElementById("update-badge");
  info_box.textContent = "Prüfe…";
  try {
    const ver = await api("GET", "/api/update/version");
    const vb = document.getElementById("version-badge");
    if (vb) vb.textContent = "v" + ver.version;

    const info = await api("GET", "/api/update/check");
    if (info.available && info.remote) {
      badge.classList.remove("hidden");
      badge.textContent = "Update verfügbar";
      info_box.innerHTML = `<strong style="color:var(--amber)">Neue Version: ${esc(info.remote.tag)}</strong>
        &ensp;<a href="${esc(info.remote.url)}" target="_blank" style="color:var(--blue);font-size:.8rem">Release-Notes →</a>
        <br><span style="font-size:.78rem;color:var(--text-3)">Aktuell installiert: v${esc(info.local)}</span>`;
      const tag = esc(info.remote.tag);
      const tarball = esc(info.remote.tarball_url);
      const pre = document.getElementById("update-cmds-text");
      if (pre) pre.textContent =
`cd /opt
wget -q "${tarball}" -O wol-update.tar.gz
tar -xzf wol-update.tar.gz
cp -r wakeonlandashboard-${tag.replace(/^v/,"")}/* wol-dashboard/
rm -rf wakeonlandashboard-${tag.replace(/^v/,"")} wol-update.tar.gz
cd /opt/wol-dashboard
./venv/bin/pip install -r requirements.txt -q
systemctl restart wol-dashboard`;
      cmds_box.style.display = "";
    } else if (info.not_configured) {
      badge.classList.add("hidden");
      info_box.innerHTML = `<span style="color:var(--text-3)">⚠ GitHub-Repo nicht konfiguriert — bitte in den Einstellungen eintragen.</span>`;
      cmds_box.style.display = "none";
    } else if (info.error) {
      badge.classList.add("hidden");
      info_box.innerHTML = `<span style="color:var(--red)">Fehler: ${esc(info.error)}</span>`;
      cmds_box.style.display = "none";
    } else {
      badge.classList.add("hidden");
      info_box.innerHTML = `<span style="color:var(--green)">✓ Aktuell (v${esc(info.local)})</span>`;
      cmds_box.style.display = "none";
    }
  } catch (e) {
    info_box.textContent = "Prüfung fehlgeschlagen: " + e.message;
  }
}

// ── Auto-poll (30 s) ──
function startPoll() {
  pollTimer = setInterval(() => {
    if (currentPage === "dashboard") loadDevices();
  }, 30000);
}

// ── Boot ──
(async function init() {
  await loadDevices();
  checkUpdate();
  startPoll();
})();
