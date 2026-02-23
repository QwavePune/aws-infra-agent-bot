const cloudFilter = document.getElementById("cloudFilter");
const statusFilter = document.getElementById("statusFilter");
const actionFilter = document.getElementById("actionFilter");
const userFilter = document.getElementById("userFilter");
const clearFiltersBtn = document.getElementById("clearFiltersBtn");
const exportBtn = document.getElementById("exportBtn");
const tableBody = document.getElementById("auditTableBody");
const entryCount = document.getElementById("entryCount");

const totalActions = document.getElementById("totalActions");
const successfulActions = document.getElementById("successfulActions");
const failedActions = document.getElementById("failedActions");
const blockedActions = document.getElementById("blockedActions");

const state = {
  filters: {
    cloud: "",
    status: "",
    action: "",
    user: "",
  },
};

if (
  !cloudFilter ||
  !statusFilter ||
  !actionFilter ||
  !userFilter ||
  !clearFiltersBtn ||
  !exportBtn ||
  !tableBody
) {
  throw new Error("Audit UI elements are missing from the page.");
}

const escapeHtml = (value) =>
  String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#039;");

const formatTimestamp = (iso) => {
  if (!iso) return "n/a";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return escapeHtml(iso);
  return date.toLocaleString();
};

const renderStatus = (status) => {
  const safe = escapeHtml(status || "unknown");
  const cls = safe === "success"
    ? "audit-status-success"
    : safe === "failed"
      ? "audit-status-failed"
      : "audit-status-blocked";
  return `<span class="audit-status-pill ${cls}">${safe}</span>`;
};

const setSelectOptions = (select, options, current) => {
  const normalized = new Set((options || []).map((x) => String(x || "")));
  const first = select.options[0];
  select.innerHTML = "";
  select.appendChild(first);
  Array.from(normalized).sort().forEach((value) => {
    const opt = document.createElement("option");
    opt.value = value;
    opt.textContent = value;
    if (value === current) {
      opt.selected = true;
    }
    select.appendChild(opt);
  });
};

const buildQuery = () => {
  const params = new URLSearchParams();
  Object.entries(state.filters).forEach(([k, v]) => {
    if (v) params.set(k, v);
  });
  params.set("limit", "500");
  return params.toString();
};

const renderTable = (entries) => {
  if (!entries.length) {
    tableBody.innerHTML = `<tr><td colspan="7">No audit entries for current filters.</td></tr>`;
    entryCount.textContent = "Showing 0 entries";
    return;
  }

  tableBody.innerHTML = entries.map((entry) => `
    <tr>
      <td class="audit-mono">${escapeHtml(formatTimestamp(entry.timestamp))}</td>
      <td class="audit-mono">${escapeHtml(entry.user)}</td>
      <td>${escapeHtml(entry.cloud)}</td>
      <td class="audit-mono">${escapeHtml(entry.action)}</td>
      <td class="audit-mono">${escapeHtml(entry.resource)}</td>
      <td>${renderStatus(entry.status)}</td>
      <td>${escapeHtml(entry.details)}</td>
    </tr>
  `).join("");
  entryCount.textContent = `Showing ${entries.length} entr${entries.length === 1 ? "y" : "ies"}`;
};

const updateSummary = (summary) => {
  totalActions.textContent = String(summary.total || 0);
  successfulActions.textContent = String(summary.successful || 0);
  failedActions.textContent = String(summary.failed || 0);
  blockedActions.textContent = String(summary.blocked || 0);
};

const fetchAuditLogs = async () => {
  const query = buildQuery();
  const response = await fetch(`/api/audit/logs?${query}`);
  if (!response.ok) {
    throw new Error("Failed to load audit logs");
  }

  const data = await response.json();
  updateSummary(data.summary || {});
  renderTable(data.entries || []);

  const filters = data.filters || {};
  setSelectOptions(cloudFilter, filters.clouds || [], state.filters.cloud);
  setSelectOptions(statusFilter, filters.statuses || [], state.filters.status);
  setSelectOptions(actionFilter, filters.actions || [], state.filters.action);
  setSelectOptions(userFilter, filters.users || [], state.filters.user);
};

const applyFiltersFromUi = () => {
  state.filters.cloud = cloudFilter.value;
  state.filters.status = statusFilter.value;
  state.filters.action = actionFilter.value;
  state.filters.user = userFilter.value;
  fetchAuditLogs().catch((err) => {
    tableBody.innerHTML = `<tr><td colspan="7">${escapeHtml(err.message)}</td></tr>`;
  });
};

[cloudFilter, statusFilter, actionFilter, userFilter].forEach((el) => {
  el.addEventListener("change", applyFiltersFromUi);
});

clearFiltersBtn.addEventListener("click", () => {
  state.filters = { cloud: "", status: "", action: "", user: "" };
  cloudFilter.value = "";
  statusFilter.value = "";
  actionFilter.value = "";
  userFilter.value = "";
  fetchAuditLogs().catch((err) => {
    tableBody.innerHTML = `<tr><td colspan="7">${escapeHtml(err.message)}</td></tr>`;
  });
});

exportBtn.addEventListener("click", () => {
  const query = buildQuery();
  window.location.href = `/api/audit/export?${query}`;
});

fetchAuditLogs().catch((err) => {
  tableBody.innerHTML = `<tr><td colspan="7">${escapeHtml(err.message)}</td></tr>`;
});
