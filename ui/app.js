const chatStream = document.getElementById("chatStream");
const composer = document.getElementById("composer");
const promptInput = document.getElementById("promptInput");
const sendBtn = document.getElementById("sendBtn");
const statusPill = document.querySelector(".status-pill");
const statusMeta = document.getElementById("statusMeta");
const runProgress = document.getElementById("runProgress");
const runProgressText = document.getElementById("runProgressText");
const runProgressTimer = document.getElementById("runProgressTimer");
const toolOutputSelect = document.getElementById("toolOutputSelect");
const modelSelect = document.getElementById("modelSelect");
const mcpSelect = document.getElementById("mcpSelect");
const providerLabel = document.getElementById("providerLabel");
const latencyLabel = document.getElementById("latencyLabel");
const capabilitiesContent = document.getElementById("capabilitiesContent");
const consoleView = document.getElementById("consoleView");
const auditView = document.getElementById("auditView");
const navAuditBtn = document.getElementById("navAuditBtn");
const navConsoleBtn = document.getElementById("navConsoleBtn");
const mcFlowSteps = document.getElementById("mcFlowSteps");
const mcTotalItems = document.getElementById("mcTotalItems");
const mcProfileLabel = document.getElementById("mcProfileLabel");
const mcPendingList = document.getElementById("mcPendingList");
const mcRefreshBtn = document.getElementById("mcRefreshBtn");
const mcManageRolesBtn = document.getElementById("mcManageRolesBtn");
const mcExecuteBtn = document.getElementById("mcExecuteBtn");
const mcModal = document.getElementById("mcModal");
const mcModalClose = document.getElementById("mcModalClose");
const mcModalTitle = document.getElementById("mcModalTitle");
const mcModalMeta = document.getElementById("mcModalMeta");
const mcModalPlan = document.getElementById("mcModalPlan");
const mcCommentThread = document.getElementById("mcCommentThread");
const mcCommentInput = document.getElementById("mcCommentInput");
const mcAddCommentBtn = document.getElementById("mcAddCommentBtn");
const mcApproveBtn = document.getElementById("mcApproveBtn");
const mcRejectBtn = document.getElementById("mcRejectBtn");
const awsLoginModal = document.getElementById("awsLoginModal");
const awsLoginModalClose = document.getElementById("awsLoginModalClose");
const awsProfileSelect = document.getElementById("awsProfileSelect");
const awsStartLoginBtn = document.getElementById("awsStartLoginBtn");
const awsLoginStatusText = document.getElementById("awsLoginStatusText");
const awsRunDiagnosticsBtn = document.getElementById("awsRunDiagnosticsBtn");
const awsDiagnosticsMeta = document.getElementById("awsDiagnosticsMeta");
const awsDiagnosticsPanel = document.getElementById("awsDiagnosticsPanel");
const mcRolesModal = document.getElementById("mcRolesModal");
const mcRolesModalClose = document.getElementById("mcRolesModalClose");
const mcRolesStatusText = document.getElementById("mcRolesStatusText");
const mcCheckerProfilesList = document.getElementById("mcCheckerProfilesList");
const mcMakerProfilesList = document.getElementById("mcMakerProfilesList");
const mcIamUsersList = document.getElementById("mcIamUsersList");
const mcSaveRolesBtn = document.getElementById("mcSaveRolesBtn");

const AGUI_CLIENT_ID_KEY = "aguiClientId";
let aguiClientId = localStorage.getItem(AGUI_CLIENT_ID_KEY);
if (!aguiClientId) {
  aguiClientId = crypto.randomUUID();
  localStorage.setItem(AGUI_CLIENT_ID_KEY, aguiClientId);
}
const nativeFetch = window.fetch.bind(window);
window.fetch = (input, init = {}) => {
  const headers = new Headers(init.headers || {});
  headers.set("X-AGUI-Client-ID", aguiClientId);
  return nativeFetch(input, { ...init, headers });
};

const brandMark = document.getElementById("brandMark");
const brandSub = document.getElementById("brandSub");
const identityTitle = document.getElementById("identityTitle");
const identityHelp = document.getElementById("identityHelp");
const quickActions = document.getElementById("quickActions");
const welcomeMessage = document.getElementById("welcomeMessage");

let threadId = crypto.randomUUID();
let currentAssistantBubble = null;
let pendingStart = null;
let currentView = "console";
let makerCheckerConfig = null;
let makerCheckerQueue = [];
let activeMakerCheckerRequest = null;
let awsLoginPollTimer = null;
let runTimerInterval = null;
let runStartedAt = null;
let makerCheckerRolesCache = null;
let awsIdentityPollAttempts = 0;
const TOOL_OUTPUT_MODE_KEY = "aguiToolOutputMode";

const MODEL_SEPARATOR = "::";
const CLOUD_AWS = "aws";
const CLOUD_AZURE = "azure";
const CLOUD_GENERIC = "generic";

const CLOUD_CONTEXT = {
  [CLOUD_AWS]: {
    brandMark: "AWS Infra Agent",
    brandSub: "Operations Console",
    loginLabel: "CLI Login",
    consoleLabel: "AWS Console",
    consoleUrl: "https://console.aws.amazon.com",
    identityTitle: "AWS Identity",
    identityHelp: "Use CLI Login to refresh profile credentials without leaving this console.",
    identityPrefix: "AWS",
    welcome:
      "Welcome back. I can guide AWS infrastructure workflows, validate prerequisites, and execute MCP tools in real time.",
    placeholder: "Ask for AWS inventory, billing, identity, or infrastructure changes...",
    quickActions: [
      { label: "Capabilities", prompt: "What can you do for me?" },
      { label: "Inventory", prompt: "List all AWS resources in my account" },
      { label: "Cost", prompt: "What is my total billed cost of AWS resources?" },
      { label: "Who Am I", prompt: "Show my current AWS identity and permissions" },
    ],
  },
  [CLOUD_AZURE]: {
    brandMark: "Azure Infra Agent",
    brandSub: "Operations Console",
    loginLabel: "Login N/A",
    consoleLabel: "Azure Portal",
    consoleUrl: "https://portal.azure.com",
    identityTitle: "Azure Identity",
    identityHelp: "Azure auth wiring is under construction in this build. You can still inspect available Azure tools and dummy terraform plan output.",
    identityPrefix: "Azure",
    welcome:
      "Welcome back. I can show Azure infrastructure capabilities and provide a dummy Terraform plan preview while full Azure execution is under construction.",
    placeholder: "Ask for Azure resource options, capabilities, or identity context...",
    quickActions: [
      { label: "Capabilities", prompt: "What can you do for me?" },
      { label: "Azure Resources", prompt: "List all Azure resources available for build" },
      { label: "Build VM", prompt: "Create an Azure VM with Terraform" },
      { label: "Status", prompt: "Are you ready to build real Azure infrastructure?" },
    ],
  },
  [CLOUD_GENERIC]: {
    brandMark: "Infra Agent",
    brandSub: "Operations Console",
    loginLabel: "CLI Login",
    consoleLabel: "Cloud Console",
    consoleUrl: "https://console.aws.amazon.com",
    identityTitle: "Cloud Identity",
    identityHelp: "Select an MCP server to enable cloud-specific tools and identity details.",
    identityPrefix: "Cloud",
    welcome:
      "Welcome back. Select an MCP server to enable cloud-specific infrastructure tooling.",
    placeholder: "Select an MCP server, then ask for capabilities or infrastructure actions...",
    quickActions: [
      { label: "Capabilities", prompt: "What can you do for me?" },
      { label: "Enable MCP", prompt: "Enable MCP and show capabilities" },
      { label: "Terraform", prompt: "Show Terraform capabilities" },
    ],
  },
};

const setStatus = (value) => {
  statusMeta.textContent = value;
};

const currentToolOutputMode = () => toolOutputSelect?.value || "text-only";

const formatElapsed = (ms) => {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(totalSeconds / 60)
    .toString()
    .padStart(2, "0");
  const seconds = (totalSeconds % 60).toString().padStart(2, "0");
  return `${minutes}:${seconds}`;
};

const startRunTimer = (label = "Running") => {
  if (runTimerInterval) {
    clearInterval(runTimerInterval);
  }
  runStartedAt = Date.now();
  if (statusPill) statusPill.classList.add("is-running");
  if (runProgress) runProgress.classList.remove("hidden-view");
  if (runProgressText) runProgressText.textContent = "Operation in progress. Please wait...";
  if (sendBtn) sendBtn.textContent = "Running 00:00";
  setStatus(`${label} • ${formatElapsed(0)}`);
  if (runProgressTimer) runProgressTimer.textContent = formatElapsed(0);
  runTimerInterval = setInterval(() => {
    if (!runStartedAt) return;
    const elapsed = formatElapsed(Date.now() - runStartedAt);
    setStatus(`${label} • ${elapsed}`);
    if (runProgressTimer) runProgressTimer.textContent = elapsed;
    if (sendBtn) sendBtn.textContent = `Running ${elapsed}`;
  }, 1000);
};

const stopRunTimer = (finalStatus = "Idle") => {
  if (runTimerInterval) {
    clearInterval(runTimerInterval);
    runTimerInterval = null;
  }
  runStartedAt = null;
  if (statusPill) statusPill.classList.remove("is-running");
  if (runProgress) runProgress.classList.add("hidden-view");
  if (runProgressTimer) runProgressTimer.textContent = "00:00";
  if (sendBtn) sendBtn.textContent = "Run";
  setStatus(finalStatus);
};

const setMakerCheckerFlow = (workflow) => {
  if (!mcFlowSteps) return;
  const children = [...mcFlowSteps.querySelectorAll(".mc-step")];
  const steps = workflow?.steps || [];
  const total = workflow?.total || children.length;

  if (mcTotalItems) {
    mcTotalItems.textContent = `Total Items: ${total}`;
  }

  children.forEach((button, idx) => {
    const stepData = steps[idx];
    const state = stepData?.state || "pending";
    button.classList.remove("completed", "current", "pending");
    button.classList.add(state === "completed" ? "completed" : state === "current" ? "current" : "pending");
    if (stepData?.name) {
      button.textContent = `${idx + 1}. ${stepData.name}`;
    }
  });
};

const setView = (view, updateHash = true) => {
  currentView = view === "audit" ? "audit" : "console";

  if (consoleView && auditView) {
    consoleView.classList.toggle("hidden-view", currentView !== "console");
    auditView.classList.toggle("hidden-view", currentView !== "audit");
  }

  if (navAuditBtn) navAuditBtn.style.display = currentView === "audit" ? "none" : "inline-flex";
  if (navConsoleBtn) navConsoleBtn.style.display = currentView === "audit" ? "inline-flex" : "none";
  if (awsLoginBtn) awsLoginBtn.style.display = currentView === "audit" ? "none" : "inline-flex";
  if (awsConsoleBtn) awsConsoleBtn.style.display = currentView === "audit" ? "none" : "inline-flex";

  if (brandMark && brandSub) {
    if (currentView === "audit") {
      brandMark.textContent = "Audit Trail";
      brandSub.textContent = "Operations Audit";
    } else {
      applyCloudContext();
    }
  }

  if (updateHash) {
    const nextHash = currentView === "audit" ? "#audit" : "#console";
    if (window.location.hash !== nextHash) {
      window.location.hash = nextHash;
    }
  }
};

const escapeHtml = (value) =>
  value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");

const formatToolResult = (result) => {
  if (!result || typeof result !== "object") {
    return String(result ?? "");
  }

  const lines = [];
  if (Object.prototype.hasOwnProperty.call(result, "success")) {
    lines.push(`success: ${result.success}`);
  }
  if (Object.prototype.hasOwnProperty.call(result, "returncode")) {
    lines.push(`returncode: ${result.returncode}`);
  }

  const appendBlock = (label, value) => {
    if (value === undefined || value === null || value === "") return;
    lines.push("");
    lines.push(`${label}:`);
    lines.push(String(value));
  };

  appendBlock("stdout", result.stdout);
  appendBlock("stderr", result.stderr);
  appendBlock("error", result.error);

  const extra = { ...result };
  delete extra.success;
  delete extra.returncode;
  delete extra.stdout;
  delete extra.stderr;
  delete extra.error;
  if (Object.keys(extra).length > 0) {
    lines.push("");
    lines.push("details:");
    lines.push(JSON.stringify(extra, null, 2));
  }

  return lines.join("\n");
};

const addMessage = (role, content) => {
  const message = document.createElement("div");
  message.className = `message ${role}`;

  const meta = document.createElement("div");
  meta.className = "message-meta";
  meta.textContent = role === "user" ? "You" : "Assistant";

  const body = document.createElement("div");
  body.className = "message-body";
  body.textContent = content;

  message.append(meta, body);
  chatStream.appendChild(message);
  chatStream.scrollTop = chatStream.scrollHeight;
  return body;
};

const fetchMakerCheckerConfig = async () => {
  if (currentCloud() !== CLOUD_AWS) return;
  try {
    const response = await fetch("/api/maker-checker/config");
    if (!response.ok) throw new Error("Unable to load maker-checker config");
    makerCheckerConfig = await response.json();
    if (mcProfileLabel) {
      const role = makerCheckerConfig.is_checker ? "Checker" : makerCheckerConfig.is_maker ? "Maker" : "Unassigned";
      const checkers = (makerCheckerConfig.checker_profiles || []).join(", ") || "none";
      mcProfileLabel.textContent = `Profile: ${makerCheckerConfig.current_profile} (${role}) • Checkers: ${checkers}`;
    }
  } catch (error) {
    console.error("Failed to fetch maker-checker config", error);
    if (mcProfileLabel) mcProfileLabel.textContent = "Profile: unavailable";
  }
};

const renderRoleCheckboxes = (container, profiles, selected) => {
  if (!container) return;
  const selectedSet = new Set(selected || []);
  if (!profiles.length) {
    container.textContent = "No profiles discovered.";
    return;
  }
  container.innerHTML = profiles
    .map(
      (profile) => `
      <label class="mc-role-check">
        <input type="checkbox" value="${escapeHtml(profile)}" ${selectedSet.has(profile) ? "checked" : ""} />
        <span>${escapeHtml(profile)}</span>
      </label>
    `
    )
    .join("");
};

const collectCheckedValues = (container) => {
  if (!container) return [];
  return [...container.querySelectorAll("input[type='checkbox']:checked")]
    .map((el) => (el.value || "").trim())
    .filter(Boolean);
};

const fetchMakerCheckerRoles = async () => {
  const response = await fetch("/api/maker-checker/roles");
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || "Unable to load role configuration");
  }
  makerCheckerRolesCache = data;
  return data;
};

const openMakerCheckerRolesModal = async () => {
  if (!mcRolesModal) return;
  mcRolesStatusText.textContent = "Loading role assignments...";
  mcRolesModal.classList.remove("hidden-view");
  try {
    const data = await fetchMakerCheckerRoles();
    const profiles = data.profiles || [];
    const selectedCheckers = data.checker_profiles || [];
    const selectedMakers =
      (data.maker_profiles || []).length > 0
        ? data.maker_profiles || []
        : profiles.filter((p) => !selectedCheckers.includes(p));
    renderRoleCheckboxes(mcCheckerProfilesList, profiles, selectedCheckers);
    renderRoleCheckboxes(mcMakerProfilesList, profiles, selectedMakers);
    const iamUsers = data.iam_users || [];
    if (mcIamUsersList) {
      mcIamUsersList.innerHTML = iamUsers.length
        ? iamUsers.map((u) => `<span class="mc-iam-chip">${escapeHtml(u)}</span>`).join("")
        : "No IAM users available or permission denied.";
    }
    const role = data.is_checker ? "Checker" : data.is_maker ? "Maker" : "Unassigned";
    mcRolesStatusText.textContent = `Current profile: ${data.current_profile || "unknown"} (${role})`;
  } catch (error) {
    mcRolesStatusText.textContent = `Failed to load role assignments: ${error.message || "unknown error"}`;
  }
};

const closeMakerCheckerRolesModal = () => {
  if (mcRolesModal) mcRolesModal.classList.add("hidden-view");
};

const renderCommentThread = (comments = []) => {
  if (!mcCommentThread) return;
  if (!comments.length) {
    mcCommentThread.textContent = "No comments yet.";
    return;
  }
  mcCommentThread.innerHTML = comments
    .map((c) => `
      <div class="mc-comment-item">
        <div class="mc-comment-meta">${escapeHtml(c.author_role || "user")} · ${escapeHtml(c.author_profile || "unknown")} · ${escapeHtml(c.timestamp || "")}</div>
        <div>${escapeHtml(c.message || "")}</div>
      </div>
    `)
    .join("");
  mcCommentThread.scrollTop = mcCommentThread.scrollHeight;
};

const updateExecuteButton = () => {
  if (!mcExecuteBtn) return;
  const show = Boolean(activeMakerCheckerRequest && activeMakerCheckerRequest.status === "approved");
  mcExecuteBtn.classList.toggle("hidden-view", !show);
  mcExecuteBtn.disabled = !show;
};

const setFlowFromStatus = (status) => {
  const s = String(status || "").toLowerCase();
  if (s === "pending") {
    setMakerCheckerFlow({
      total: 4,
      steps: [
        { name: "Request Captured", state: "completed" },
        { name: "Awaiting Approval", state: "current" },
        { name: "Approved", state: "pending" },
        { name: "Executed", state: "pending" },
      ],
    });
    return;
  }
  if (s === "approved") {
    setMakerCheckerFlow({
      total: 4,
      steps: [
        { name: "Request Captured", state: "completed" },
        { name: "Awaiting Approval", state: "completed" },
        { name: "Approved", state: "current" },
        { name: "Executed", state: "pending" },
      ],
    });
    return;
  }
  if (s === "executing") {
    setMakerCheckerFlow({
      total: 4,
      steps: [
        { name: "Request Captured", state: "completed" },
        { name: "Awaiting Approval", state: "completed" },
        { name: "Approved", state: "completed" },
        { name: "Executed", state: "current" },
      ],
    });
    return;
  }
  if (s === "executed") {
    setMakerCheckerFlow({
      total: 4,
      steps: [
        { name: "Request Captured", state: "completed" },
        { name: "Awaiting Approval", state: "completed" },
        { name: "Approved", state: "completed" },
        { name: "Executed", state: "completed" },
      ],
    });
    return;
  }
  if (s === "rejected" || s === "failed") {
    setMakerCheckerFlow({
      total: 4,
      steps: [
        { name: "Request Captured", state: "completed" },
        { name: "Awaiting Approval", state: s === "failed" ? "completed" : "current" },
        { name: "Approved", state: "pending" },
        { name: "Executed", state: "pending" },
      ],
    });
  }
};

const openMakerCheckerModal = async (requestId) => {
  if (!requestId) return;
  const response = await fetch(`/api/maker-checker/request/${encodeURIComponent(requestId)}`);
  const data = await response.json();
  if (!data.success) {
    addMessage("assistant", `Unable to load maker-checker request: ${data.error || "unknown error"}`);
    return;
  }
  activeMakerCheckerRequest = data.request;
  if (mcModalTitle) mcModalTitle.textContent = `Maker-Checker Review: ${activeMakerCheckerRequest.request_id}`;
  if (mcModalMeta) {
    mcModalMeta.textContent = `Tool: ${activeMakerCheckerRequest.tool_name} • Requester: ${activeMakerCheckerRequest.requester_profile} • Status: ${activeMakerCheckerRequest.status}`;
  }
  if (mcModalPlan) mcModalPlan.textContent = activeMakerCheckerRequest.plan_preview || "No plan preview available.";
  renderCommentThread(activeMakerCheckerRequest.comments || []);
  setFlowFromStatus(activeMakerCheckerRequest.status);
  if (mcApproveBtn) mcApproveBtn.disabled = !makerCheckerConfig?.is_checker;
  if (mcRejectBtn) mcRejectBtn.disabled = !makerCheckerConfig?.is_checker;
  updateExecuteButton();
  if (mcModal) mcModal.classList.remove("hidden-view");
};

const closeMakerCheckerModal = () => {
  if (mcModal) mcModal.classList.add("hidden-view");
};

const submitMakerCheckerDecision = async (action, requestId, notes = "") => {
  const endpoint = action === "approve" ? "/api/maker-checker/approve" : "/api/maker-checker/reject";
  const response = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ request_id: requestId, notes }),
  });
  const data = await response.json();
  if (!data.success) {
    addMessage("assistant", `${action} failed: ${data.error || "unknown error"}`);
    return null;
  }
  activeMakerCheckerRequest = data.request;
  setFlowFromStatus(activeMakerCheckerRequest.status);
  updateExecuteButton();
  await refreshMakerCheckerQueue();
  return data.request;
};

const executeMakerCheckerRequest = async (requestId, notes = "") => {
  const response = await fetch("/api/maker-checker/execute", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ request_id: requestId, notes }),
  });
  const data = await response.json();
  if (!data.success) {
    addMessage("assistant", `Execute failed: ${data.error || "unknown error"}`);
    return;
  }
  activeMakerCheckerRequest = data.request;
  setFlowFromStatus(activeMakerCheckerRequest.status);
  updateExecuteButton();

  const result = activeMakerCheckerRequest.execution_result || {};
  const content = `Maker-checker execution result for ${activeMakerCheckerRequest.tool_name}\n${formatToolResult(result)}`;
  addMessage("assistant", content);
  await refreshMakerCheckerQueue();
};

const renderMakerCheckerQueue = (items = []) => {
  if (!mcPendingList) return;
  if (!items.length) {
    mcPendingList.textContent = "No pending approvals.";
    return;
  }
  mcPendingList.innerHTML = items
    .map((item) => {
      return `
        <div class="mc-queue-item">
          <div class="mc-queue-head">
            <span>${escapeHtml(item.request_id || "")}</span>
            <span>${escapeHtml(item.status || "")}</span>
          </div>
          <div class="mc-queue-tool">${escapeHtml(item.tool_name || "")}</div>
          <div class="mc-queue-actions">
            <button type="button" class="mc-btn-approve" data-action="review" data-id="${escapeHtml(item.request_id || "")}">Approve</button>
          </div>
        </div>
      `;
    })
    .join("");

  mcPendingList.querySelectorAll("button[data-action]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const requestId = btn.getAttribute("data-id");
      if (!requestId) return;
      await openMakerCheckerModal(requestId);
    });
  });
};

const refreshMakerCheckerQueue = async () => {
  if (currentCloud() !== CLOUD_AWS) return;
  await fetchMakerCheckerConfig();
  try {
    const response = await fetch("/api/maker-checker/requests");
    if (!response.ok) throw new Error("Unable to load pending requests");
    const data = await response.json();
    makerCheckerQueue = data.requests || [];
    const prioritized = makerCheckerQueue.filter((r) => ["pending", "approved"].includes(String(r.status || "").toLowerCase()));
    renderMakerCheckerQueue(prioritized);

    const approved = makerCheckerQueue.find((r) => String(r.status || "").toLowerCase() === "approved");
    if (approved && (!activeMakerCheckerRequest || activeMakerCheckerRequest.request_id !== approved.request_id)) {
      activeMakerCheckerRequest = approved;
      setFlowFromStatus("approved");
    } else if (!approved && !prioritized.length) {
      activeMakerCheckerRequest = null;
    }
    updateExecuteButton();
  } catch (error) {
    console.error("Failed to load maker-checker requests", error);
    if (mcPendingList) mcPendingList.textContent = "Failed to load pending approvals.";
  }
};

const updateLatency = (startTime) => {
  const elapsedMs = Date.now() - startTime;
  latencyLabel.textContent = `${(elapsedMs / 1000).toFixed(2)}s`;
};

const updateProviderLabel = () => {
  const selected = modelSelect.value.split(MODEL_SEPARATOR);
  providerLabel.textContent = selected[0] || "unknown";
};

const currentCloud = () => {
  if (mcpSelect.value === "aws_terraform") return CLOUD_AWS;
  if (mcpSelect.value === "azure_terraform") return CLOUD_AZURE;
  return CLOUD_GENERIC;
};

const cloudForCapabilities = () => {
  if (mcpSelect.value === "aws_terraform") return CLOUD_AWS;
  if (mcpSelect.value === "azure_terraform") return CLOUD_AZURE;
  return CLOUD_GENERIC;
};

const renderQuickActions = (items) => {
  if (!quickActions) return;
  quickActions.innerHTML = "";

  items.forEach((item) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "prompt-chip";
    button.dataset.prompt = item.prompt;
    button.textContent = item.label;
    button.addEventListener("click", () => {
      const prompt = button.dataset.prompt || "";
      if (!prompt) return;
      promptInput.value = prompt;
      promptInput.style.height = "auto";
      promptInput.style.height = `${promptInput.scrollHeight}px`;
      promptInput.focus();
    });
    quickActions.appendChild(button);
  });
};

const applyCloudContext = () => {
  const cloud = currentCloud();
  const context = CLOUD_CONTEXT[cloud] || CLOUD_CONTEXT[CLOUD_GENERIC];

  if (brandMark) brandMark.textContent = context.brandMark;
  if (brandSub) brandSub.textContent = context.brandSub;
  if (identityTitle) identityTitle.textContent = context.identityTitle;
  if (identityHelp) identityHelp.textContent = context.identityHelp;
  if (welcomeMessage) welcomeMessage.textContent = context.welcome;
  if (promptInput) promptInput.placeholder = context.placeholder;

  renderQuickActions(context.quickActions);
  syncCloudButtons(cloud);
  syncIdentityPanel(cloud);
};

const loadModels = async () => {
  try {
    const response = await fetch("/api/models");
    if (!response.ok) {
      throw new Error("Unable to load models");
    }
    const data = await response.json();
    modelSelect.innerHTML = "";

    data.providers.forEach((provider) => {
      provider.models.forEach((model) => {
        const option = document.createElement("option");
        option.value = `${provider.key}${MODEL_SEPARATOR}${model}`;
        option.textContent = `${provider.name} · ${model}`;
        if (model === provider.default_model) {
          option.dataset.default = "true";
        }
        modelSelect.appendChild(option);
      });
    });

    const options = [...modelSelect.options];
    const preferredOpenAI =
      options.find((opt) => opt.value === "openai::gpt-4o-mini") ||
      options.find((opt) => opt.value.startsWith("openai::"));
    const defaultOption = options.find((opt) => opt.dataset.default === "true");
    if (preferredOpenAI) {
      modelSelect.value = preferredOpenAI.value;
    } else if (defaultOption) {
      modelSelect.value = defaultOption.value;
    }

    updateProviderLabel();
  } catch (error) {
    console.error(error);
    modelSelect.innerHTML = '<option value="openai::gpt-4o-mini">OpenAI · gpt-4o-mini</option>';
  }
};

modelSelect.addEventListener("change", updateProviderLabel);

if (toolOutputSelect) {
  const savedToolMode = localStorage.getItem(TOOL_OUTPUT_MODE_KEY);
  if (savedToolMode === "full-tool-output" || savedToolMode === "text-only") {
    toolOutputSelect.value = savedToolMode;
  }
  toolOutputSelect.addEventListener("change", () => {
    localStorage.setItem(TOOL_OUTPUT_MODE_KEY, toolOutputSelect.value);
  });
}

const categorizeTools = (tools, cloud) => {
  const dedupedMap = new Map();
  (tools || []).forEach((tool) => {
    const name = (tool.name || "").trim();
    if (!name) return;
    const existing = dedupedMap.get(name);
    if (!existing) {
      dedupedMap.set(name, tool);
      return;
    }
    const currentDesc = String(tool.description || "");
    const existingDesc = String(existing.description || "");
    if (currentDesc.length > existingDesc.length) {
      dedupedMap.set(name, tool);
    }
  });

  const groups = {
    discovery: [],
    automation: [],
    terraform: [],
    identity: [],
    workflow: [],
    other: [],
  };

  [...dedupedMap.values()].forEach((tool) => {
    const name = (tool.name || "").trim();

    if (
      name === "list_account_inventory" ||
      name === "list_aws_resources" ||
      name === "describe_resource" ||
      name === "list_azure_resources"
    ) {
      groups.discovery.push(tool);
      return;
    }
    if (name.startsWith("terraform_") || name === "get_infrastructure_state") {
      groups.terraform.push(tool);
      return;
    }
    if (name === "get_user_permissions" || name === "get_azure_subscription_context") {
      groups.identity.push(tool);
      return;
    }
    if (name.startsWith("start_") || name.startsWith("update_") || name.startsWith("review_")) {
      groups.workflow.push(tool);
      return;
    }
    if (name.startsWith("create_")) {
      groups.automation.push(tool);
      return;
    }

    if (cloud === CLOUD_AZURE && (name.includes("azure") || name.includes("resource"))) {
      groups.automation.push(tool);
      return;
    }

    groups.other.push(tool);
  });

  return groups;
};

const renderCapabilities = (tools) => {
  if (!capabilitiesContent) return;

  const cloud = cloudForCapabilities();
  const groups = categorizeTools(tools || [], cloud);
  const cards = [];

  if (groups.discovery.length > 0) {
    cards.push({
      title: "Discovery & Inventory",
      description:
        cloud === CLOUD_AZURE
          ? "List available Azure resources and inspect discovery options."
          : "Account-wide listing and detailed resource lookups across regions.",
      hint:
        cloud === CLOUD_AZURE
          ? "Ask: List all Azure resources available for build"
          : "Ask: List all resources in my account",
    });
  }

  if (groups.automation.length > 0) {
    cards.push({
      title: cloud === CLOUD_AZURE ? "Azure Infra Automation" : "AWS Infra Automation",
      description:
        cloud === CLOUD_AZURE
          ? "Dummy Azure provisioning commands are exposed while real execution is under construction."
          : "Provision and manage compute, storage, database, and networking resources.",
      hint: cloud === CLOUD_AZURE ? "Ask: Create an Azure VM" : "Ask: Show ECS capabilities",
    });
  }

  if (groups.terraform.length > 0) {
    cards.push({
      title: "Terraform Lifecycle",
      description:
        cloud === CLOUD_AZURE
          ? "Preview terraform plan output for Azure. Apply/build is currently under construction."
          : "Generic plan, apply, destroy, and state operations.",
      hint: "Ask: Show Terraform capabilities",
    });
  }

  if (groups.identity.length > 0) {
    cards.push({
      title: "Identity & Access",
      description:
        cloud === CLOUD_AZURE
          ? "Subscription/identity context checks (dummy in this build)."
          : "AWS identity checks and permissions context.",
      hint: cloud === CLOUD_AZURE ? "Ask: Show Azure identity context" : "Ask: Show IAM capabilities",
    });
  }

  if (groups.workflow.length > 0) {
    cards.push({
      title: "Guided Workflows",
      description: "Multi-step orchestration with preflight validation gates.",
      hint: "Ask: Show workflow capabilities",
    });
  }

  if (cards.length === 0 && (tools || []).length > 0) {
    (tools || []).forEach((tool) => {
      cards.push({
        title: tool.name || "Tool",
        description: tool.description || "No description available.",
        hint: "",
      });
    });
  }

  const rendered = cards
    .map(
      (item) =>
        `<div class="cap-tool"><div class="cap-tool-name">${escapeHtml(item.title)}</div><div class="cap-tool-desc">${escapeHtml(item.description)}</div>${item.hint ? `<div class="cap-tool-hint">${escapeHtml(item.hint)}</div>` : ""}</div>`
    )
    .join("");

  capabilitiesContent.innerHTML = rendered || "No capabilities available.";
};

const loadCapabilities = async () => {
  if (!capabilitiesContent) return;
  capabilitiesContent.textContent = "Loading capabilities...";

  if (mcpSelect.value === "none") {
    capabilitiesContent.textContent = "MCP disabled. Enable an MCP server to view executable capabilities.";
    return;
  }

  try {
    const serverName = encodeURIComponent(mcpSelect.value);
    const response = await fetch(`/api/mcp/tools?mcpServer=${serverName}`);
    if (!response.ok) {
      throw new Error("Unable to fetch MCP tools");
    }
    const data = await response.json();
    renderCapabilities(data.tools || []);
  } catch (error) {
    console.error("Failed to load capabilities", error);
    capabilitiesContent.textContent = "Failed to load capabilities.";
  }
};

const parseSse = async (response, onEvent) => {
  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop();

    for (const part of parts) {
      const line = part
        .split("\n")
        .find((entry) => entry.startsWith("data:"));
      if (!line) continue;
      const json = line.replace(/^data:\s?/, "");
      try {
        const event = JSON.parse(json);
        onEvent(event);
      } catch (error) {
        console.warn("Failed to parse event", error);
      }
    }
  }
};

const sendMessage = async (message) => {
  const trimmed = message.trim();
  if (!trimmed) return;

  addMessage("user", trimmed);
  promptInput.value = "";
  promptInput.style.height = "auto";

  const [provider, model] = modelSelect.value.split(MODEL_SEPARATOR);
  const mcpServer = mcpSelect.value;
  const payload = {
    message: trimmed,
    threadId,
    provider,
    model,
    mcpServer,
  };

  startRunTimer("Starting");
  sendBtn.disabled = true;
  const startedAt = Date.now();
  try {
    const response = await fetch("/api/run", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      addMessage("assistant", "Error: unable to reach agent server.");
      stopRunTimer("Error");
      return;
    }

    await parseSse(response, (event) => {
      if (event.type === "RUN_STARTED") {
        startRunTimer("Running");
        pendingStart = Date.now();
        setMakerCheckerFlow({
          total: 4,
          steps: [
            { name: "Request Captured", state: "current" },
            { name: "Awaiting Approval", state: "pending" },
            { name: "Approved", state: "pending" },
            { name: "Executed", state: "pending" },
          ],
        });
      }
      if (event.type === "TEXT_MESSAGE_START") {
        currentAssistantBubble = addMessage("assistant", "");
      }
      if (event.type === "TEXT_MESSAGE_CONTENT") {
        if (!currentAssistantBubble) {
          currentAssistantBubble = addMessage("assistant", "");
        }
        currentAssistantBubble.textContent += event.delta || "";
        chatStream.scrollTop = chatStream.scrollHeight;
      }
      if (event.type === "TEXT_MESSAGE_END") {
        currentAssistantBubble = null;
      }
      if (event.type === "TOOL_RESULT") {
        if (currentToolOutputMode() === "full-tool-output") {
          const toolBubble = addMessage("assistant", "");
          const toolName = escapeHtml(String(event.toolName || "unknown_tool"));
          const rendered = formatToolResult(event.result);
          toolBubble.innerHTML = `<strong>Tool: ${toolName}</strong>`;
          const pre = document.createElement("pre");
          pre.className = "tool-result";
          pre.textContent = rendered;
          toolBubble.appendChild(pre);
          chatStream.scrollTop = chatStream.scrollHeight;
        }
        if (event.result?.queued_for_approval) {
          setMakerCheckerFlow({
            total: 4,
            steps: [
              { name: "Request Captured", state: "completed" },
              { name: "Awaiting Approval", state: "current" },
              { name: "Approved", state: "pending" },
              { name: "Executed", state: "pending" },
            ],
          });
          refreshMakerCheckerQueue();
        }
      }
      if (event.type === "MAKER_CHECKER_REQUEST") {
        if (event.request) {
          activeMakerCheckerRequest = event.request;
        }
        refreshMakerCheckerQueue();
      }
      if (event.type === "MAKER_CHECKER_STATUS") {
        setMakerCheckerFlow(event.workflow || {});
      }
      if (event.type === "RUN_ERROR") {
        addMessage("assistant", event.message || "Agent error");
        stopRunTimer("Error");
        sendBtn.disabled = false;
      }
      if (event.type === "RUN_FINISHED") {
        updateLatency(startedAt);
        stopRunTimer("Idle");
        sendBtn.disabled = false;
      }
    });
  } catch (error) {
    console.error("Failed to send message", error);
    addMessage("assistant", "Error: failed while streaming agent response.");
    stopRunTimer("Error");
  } finally {
    if (runTimerInterval || runStartedAt) {
      stopRunTimer("Idle");
    }
    if (sendBtn.disabled) {
      sendBtn.disabled = false;
    }
  }
};

composer.addEventListener("submit", (event) => {
  event.preventDefault();
  sendMessage(promptInput.value);
});

promptInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendMessage(promptInput.value);
  }
});

promptInput.addEventListener("input", () => {
  promptInput.style.height = "auto";
  promptInput.style.height = `${promptInput.scrollHeight}px`;
});

const awsLoginBtn = document.getElementById("awsLoginBtn");
const awsConsoleBtn = document.getElementById("awsConsoleBtn");
const awsIdentity = document.getElementById("awsIdentity");
const awsAccountLabel = document.getElementById("awsAccount");
const identityHelpText = document.getElementById("identityHelp");

const syncCloudButtons = (cloud) => {
  const context = CLOUD_CONTEXT[cloud] || CLOUD_CONTEXT[CLOUD_GENERIC];
  awsConsoleBtn.textContent = context.consoleLabel;
  awsConsoleBtn.dataset.targetUrl = context.consoleUrl;

  if (cloud === CLOUD_AZURE) {
    awsLoginBtn.textContent = context.loginLabel;
    awsLoginBtn.disabled = true;
    awsLoginBtn.classList.remove("btn-primary");
    awsLoginBtn.classList.add("btn-secondary");
    return;
  }

  awsLoginBtn.disabled = false;
};

const syncIdentityPanel = (cloud) => {
  const context = CLOUD_CONTEXT[cloud] || CLOUD_CONTEXT[CLOUD_GENERIC];

  if (cloud !== CLOUD_AWS) {
    awsIdentity.style.display = "flex";
    awsAccountLabel.textContent = `${context.identityPrefix}: context unavailable in this build`;
    return;
  }

  refreshAwsIdentity();
};

const refreshAwsIdentity = async () => {
  if (currentCloud() !== CLOUD_AWS) return;

  try {
    const response = await fetch("/api/aws/identity");
    const data = await response.json();
    const profileLabel = data.profile || "no profile selected";
    awsIdentity.style.display = "flex";
    if (data.active) {
      awsAccountLabel.innerHTML = `AWS: ${data.account} · ${data.user_name || "unknown"} <small style="opacity: 0.7; margin-left: 5px;">(${data.profile})</small>`;
      if (identityHelpText) {
        identityHelpText.textContent = "Authenticated via AWS CLI. Identity is ready for MCP operations.";
      }
      awsLoginBtn.textContent = "Refresh CLI";
      awsLoginBtn.classList.remove("btn-primary");
      awsLoginBtn.classList.add("btn-secondary");
    } else {
      awsAccountLabel.innerHTML = `AWS Profile: <strong>${escapeHtml(profileLabel)}</strong> <small style="opacity: 0.75; margin-left: 5px;">session not verified</small>`;
      if (identityHelpText) {
        identityHelpText.textContent = data.error
          ? `Selected profile could not be verified yet: ${data.error}`
          : "Use CLI Login to authenticate the selected AWS profile.";
      }
      awsLoginBtn.textContent = "CLI Login";
      awsLoginBtn.classList.remove("btn-secondary");
      awsLoginBtn.classList.add("btn-primary");
    }
  } catch (error) {
    console.error("Failed to fetch AWS identity", error);
    awsIdentity.style.display = "flex";
    awsAccountLabel.textContent = "AWS Profile: unavailable";
    if (identityHelpText) {
      identityHelpText.textContent = "Failed to load AWS identity state from the backend.";
    }
  }
};

const stopAwsLoginPolling = () => {
  if (awsLoginPollTimer) {
    clearInterval(awsLoginPollTimer);
    awsLoginPollTimer = null;
  }
  awsIdentityPollAttempts = 0;
};

const closeAwsLoginModal = () => {
  stopAwsLoginPolling();
  if (awsLoginModal) awsLoginModal.classList.add("hidden-view");
};

const runAwsDiagnostics = async (profile) => {
  const selected = (profile || awsProfileSelect?.value || "").trim() || "default";
  if (awsDiagnosticsMeta) awsDiagnosticsMeta.textContent = `Running diagnostics for '${selected}'...`;
  if (awsDiagnosticsPanel) awsDiagnosticsPanel.textContent = "Loading diagnostics...";
  try {
    const response = await fetch(`/api/aws/diagnostics?profile=${encodeURIComponent(selected)}`);
    const data = await response.json();
    const runtimeProfile = data.profile || selected;
    const loginProfile = data.login_profile || runtimeProfile;
    if (awsDiagnosticsMeta) {
      awsDiagnosticsMeta.textContent = `Runtime profile: ${runtimeProfile} • Login profile: ${loginProfile}`;
    }
    if (awsDiagnosticsPanel) {
      awsDiagnosticsPanel.textContent = JSON.stringify(data, null, 2);
    }
  } catch (error) {
    if (awsDiagnosticsMeta) awsDiagnosticsMeta.textContent = `Diagnostics failed for '${selected}'.`;
    if (awsDiagnosticsPanel) awsDiagnosticsPanel.textContent = String(error);
  }
};

const openAwsLoginModal = async () => {
  if (!awsLoginModal || !awsProfileSelect) return;
  awsProfileSelect.innerHTML = "";
  awsLoginStatusText.textContent = "Loading profiles...";
  try {
    const response = await fetch("/api/aws/profiles");
    const data = await response.json();
    const profiles = data.profiles || [];
    profiles.forEach((profile) => {
      const option = document.createElement("option");
      option.value = profile;
      option.textContent = profile;
      if (profile === data.current_profile) option.selected = true;
      awsProfileSelect.appendChild(option);
    });
    if (profiles.length === 0) {
      const opt = document.createElement("option");
      opt.value = "default";
      opt.textContent = "default";
      awsProfileSelect.appendChild(opt);
    }
    const checkers = (data.checker_profiles || []).join(", ");
    awsLoginStatusText.textContent = `Checker profiles: ${checkers || "not configured"}`;
    await runAwsDiagnostics(data.current_profile || profiles[0] || "default");
  } catch (error) {
    awsLoginStatusText.textContent = "Failed to load AWS profiles.";
    if (awsDiagnosticsMeta) awsDiagnosticsMeta.textContent = "Diagnostics unavailable.";
    if (awsDiagnosticsPanel) awsDiagnosticsPanel.textContent = "Unable to load diagnostics.";
  }
  awsLoginModal.classList.remove("hidden-view");
};

const pollAwsIdentity = (profile) => {
  stopAwsLoginPolling();
  awsLoginPollTimer = setInterval(async () => {
    try {
      awsIdentityPollAttempts += 1;
      const response = await fetch("/api/aws/identity");
      const data = await response.json();
      if (data.active) {
        stopAwsLoginPolling();
        await refreshAwsIdentity();
        await refreshMakerCheckerQueue();
        await runAwsDiagnostics(profile || data.profile);
        addMessage("assistant", `AWS login successful for profile '${data.profile}'.`);
        closeAwsLoginModal();
        return;
      }
      awsLoginStatusText.textContent = `Waiting for AWS session on profile '${profile}'...`;
      if (awsIdentityPollAttempts >= 60) {
        stopAwsLoginPolling();
        addMessage("assistant", `AWS login did not complete for profile '${profile}'. Check the browser login tab and try again.`);
        await runAwsDiagnostics(profile);
      }
    } catch (error) {
      awsLoginStatusText.textContent = "Polling failed. Check backend logs.";
    }
  }, 2000);
};

awsConsoleBtn.addEventListener("click", () => {
  const cloud = currentCloud();
  const context = CLOUD_CONTEXT[cloud] || CLOUD_CONTEXT[CLOUD_GENERIC];
  const target = awsConsoleBtn.dataset.targetUrl || context.consoleUrl;
  window.open(target, "_blank");
});

awsLoginBtn.addEventListener("click", async () => {
  if (currentCloud() !== CLOUD_AWS) {
    addMessage("assistant", "Azure login integration is currently under construction.");
    return;
  }
  await openAwsLoginModal();
});

if (awsLoginModal) {
  awsLoginModal.addEventListener("click", (event) => {
    const target = event.target;
    if (target && target.getAttribute && target.getAttribute("data-close-aws-login") === "true") {
      closeAwsLoginModal();
    }
  });
}

if (awsLoginModalClose) {
  awsLoginModalClose.addEventListener("click", () => closeAwsLoginModal());
}

if (awsProfileSelect) {
  awsProfileSelect.addEventListener("change", async () => {
    await runAwsDiagnostics((awsProfileSelect.value || "").trim() || "default");
  });
}

if (mcManageRolesBtn) {
  mcManageRolesBtn.addEventListener("click", async () => {
    await openMakerCheckerRolesModal();
  });
}

if (mcRolesModal) {
  mcRolesModal.addEventListener("click", (event) => {
    const target = event.target;
    if (target && target.getAttribute && target.getAttribute("data-close-mc-roles") === "true") {
      closeMakerCheckerRolesModal();
    }
  });
}

if (mcRolesModalClose) {
  mcRolesModalClose.addEventListener("click", () => closeMakerCheckerRolesModal());
}

if (mcSaveRolesBtn) {
  mcSaveRolesBtn.addEventListener("click", async () => {
    const checkerProfiles = collectCheckedValues(mcCheckerProfilesList);
    const makerProfiles = collectCheckedValues(mcMakerProfilesList);
    if (!checkerProfiles.length) {
      mcRolesStatusText.textContent = "At least one checker profile must be selected.";
      return;
    }
    mcSaveRolesBtn.disabled = true;
    mcRolesStatusText.textContent = "Saving role assignments...";
    try {
      const response = await fetch("/api/maker-checker/roles", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          checker_profiles: checkerProfiles,
          maker_profiles: makerProfiles,
        }),
      });
      const data = await response.json();
      if (!data.success) {
        mcRolesStatusText.textContent = data.error || "Failed to save roles.";
        return;
      }
      mcRolesStatusText.textContent = "Role assignments saved.";
      await fetchMakerCheckerConfig();
      await refreshMakerCheckerQueue();
      addMessage("assistant", `Maker-checker roles updated. Checkers: ${checkerProfiles.join(", ")}.`);
      closeMakerCheckerRolesModal();
    } catch (error) {
      mcRolesStatusText.textContent = "Failed to save role assignments.";
    } finally {
      mcSaveRolesBtn.disabled = false;
    }
  });
}

if (awsStartLoginBtn) {
  awsStartLoginBtn.addEventListener("click", async () => {
    const profile = (awsProfileSelect?.value || "").trim() || "default";
    awsLoginStatusText.textContent = `Starting login for profile '${profile}'...`;
    awsStartLoginBtn.disabled = true;
    try {
      await fetch("/api/aws/profile", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ profile }),
      });
      const response = await fetch("/api/aws/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ profile }),
      });
      const data = await response.json();
      if (!data.success) {
        awsLoginStatusText.textContent = data.error || "Failed to start login.";
        return;
      }
      awsLoginStatusText.textContent = "Browser login started. Complete AWS authentication in the browser; AGUI is polling for an active session.";
      await runAwsDiagnostics(profile);
      pollAwsIdentity(profile);
    } catch (error) {
      awsLoginStatusText.textContent = "Login start failed.";
    } finally {
      awsStartLoginBtn.disabled = false;
    }
  });
}

if (awsRunDiagnosticsBtn) {
  awsRunDiagnosticsBtn.addEventListener("click", async () => {
    await runAwsDiagnostics((awsProfileSelect?.value || "").trim() || "default");
  });
}

mcpSelect.addEventListener("change", () => {
  applyCloudContext();
  loadCapabilities();
  refreshMakerCheckerQueue();
});

if (mcFlowSteps) {
  mcFlowSteps.querySelectorAll(".mc-step").forEach((stepBtn) => {
    stepBtn.addEventListener("click", async () => {
      const candidate = makerCheckerQueue.find((r) => ["pending", "approved", "executing"].includes(String(r.status || "").toLowerCase()));
      if (candidate) {
        await openMakerCheckerModal(candidate.request_id);
      } else {
        addMessage("assistant", "No maker-checker request is currently awaiting review.");
      }
    });
  });
}

if (mcModal) {
  mcModal.addEventListener("click", (event) => {
    const target = event.target;
    if (target && target.getAttribute && target.getAttribute("data-close") === "true") {
      closeMakerCheckerModal();
    }
  });
}

if (mcModalClose) {
  mcModalClose.addEventListener("click", () => closeMakerCheckerModal());
}

if (mcAddCommentBtn) {
  mcAddCommentBtn.addEventListener("click", async () => {
    if (!activeMakerCheckerRequest) return;
    const msg = (mcCommentInput?.value || "").trim();
    if (!msg) return;
    const response = await fetch("/api/maker-checker/comment", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ request_id: activeMakerCheckerRequest.request_id, message: msg }),
    });
    const data = await response.json();
    if (!data.success) {
      addMessage("assistant", `Comment failed: ${data.error || "unknown error"}`);
      return;
    }
    activeMakerCheckerRequest = data.request;
    renderCommentThread(activeMakerCheckerRequest.comments || []);
    if (mcCommentInput) mcCommentInput.value = "";
    await refreshMakerCheckerQueue();
  });
}

if (mcApproveBtn) {
  mcApproveBtn.addEventListener("click", async () => {
    if (!activeMakerCheckerRequest) return;
    const notes = (mcCommentInput?.value || "").trim();
    const updated = await submitMakerCheckerDecision("approve", activeMakerCheckerRequest.request_id, notes);
    if (updated) {
      addMessage("assistant", `Approved request ${updated.request_id}. Use Execute Plan to run it.`);
      activeMakerCheckerRequest = updated;
      renderCommentThread(updated.comments || []);
      if (mcCommentInput) mcCommentInput.value = "";
    }
  });
}

if (mcRejectBtn) {
  mcRejectBtn.addEventListener("click", async () => {
    if (!activeMakerCheckerRequest) return;
    const notes = (mcCommentInput?.value || "").trim();
    const updated = await submitMakerCheckerDecision("reject", activeMakerCheckerRequest.request_id, notes);
    if (updated) {
      addMessage("assistant", `Rejected request ${updated.request_id}.`);
      activeMakerCheckerRequest = updated;
      renderCommentThread(updated.comments || []);
      if (mcCommentInput) mcCommentInput.value = "";
    }
  });
}

if (mcExecuteBtn) {
  mcExecuteBtn.addEventListener("click", async () => {
    if (!activeMakerCheckerRequest) return;
    const notes = (mcCommentInput?.value || "").trim();
    setFlowFromStatus("executing");
    await executeMakerCheckerRequest(activeMakerCheckerRequest.request_id, notes);
    if (mcCommentInput) mcCommentInput.value = "";
  });
}

if (mcRefreshBtn) {
  mcRefreshBtn.addEventListener("click", () => {
    refreshMakerCheckerQueue();
  });
}

if (navAuditBtn) {
  navAuditBtn.addEventListener("click", () => setView("audit"));
}

if (navConsoleBtn) {
  navConsoleBtn.addEventListener("click", () => setView("console"));
}

document.querySelectorAll('[data-nav="audit"]').forEach((el) => {
  el.addEventListener("click", (event) => {
    event.preventDefault();
    setView("audit");
  });
});

window.addEventListener("hashchange", () => {
  if (window.location.hash === "#audit") {
    setView("audit", false);
  } else {
    setView("console", false);
  }
});

setInterval(refreshAwsIdentity, 30000);

loadModels();
applyCloudContext();
loadCapabilities();
refreshMakerCheckerQueue();
if (window.location.hash === "#audit") {
  setView("audit", false);
} else {
  setView("console", false);
}
