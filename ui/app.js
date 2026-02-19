const chatStream = document.getElementById("chatStream");
const composer = document.getElementById("composer");
const promptInput = document.getElementById("promptInput");
const sendBtn = document.getElementById("sendBtn");
const statusMeta = document.getElementById("statusMeta");
const modelSelect = document.getElementById("modelSelect");
const mcpSelect = document.getElementById("mcpSelect");
const providerLabel = document.getElementById("providerLabel");
const latencyLabel = document.getElementById("latencyLabel");
const capabilitiesContent = document.getElementById("capabilitiesContent");

const brandMark = document.getElementById("brandMark");
const brandSub = document.getElementById("brandSub");
const identityTitle = document.getElementById("identityTitle");
const identityHelp = document.getElementById("identityHelp");
const workflowTitle = document.getElementById("workflowTitle");
const workflowList = document.getElementById("workflowList");
const quickActions = document.getElementById("quickActions");
const welcomeMessage = document.getElementById("welcomeMessage");

let threadId = crypto.randomUUID();
let currentAssistantBubble = null;
let pendingStart = null;

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
    placeholder: "Ask for inventory, deployment, or guided ECS flow...",
    workflowTitle: "Guided Workflow",
    workflowSteps: [
      "Start workflow and collect requirements",
      "Validate IDs, roles, and region prerequisites",
      "Create Terraform project",
      "Run plan then apply",
    ],
    quickActions: [
      { label: "Capabilities", prompt: "What can you do for me?" },
      { label: "Inventory", prompt: "List all AWS resources in my account" },
      { label: "Start ECS Flow", prompt: "Start ECS deployment workflow in ap-south-1" },
      { label: "Review ECS", prompt: "Review my current ECS deployment workflow" },
      { label: "Terraform Plan", prompt: "Run terraform_plan for my last project" },
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
    placeholder: "Ask for Azure resource options, capabilities, or Terraform plan preview...",
    workflowTitle: "Azure Workflow",
    workflowSteps: [
      "Capture Azure infrastructure requirements",
      "Generate Terraform skeleton for Azure resources",
      "Preview terraform_plan output",
      "Use under-construction response for apply/build",
    ],
    quickActions: [
      { label: "Capabilities", prompt: "What can you do for me?" },
      { label: "Azure Resources", prompt: "List all Azure resources available for build" },
      { label: "Terraform Plan", prompt: "Run terraform_plan for azure-demo" },
      { label: "Terraform Apply", prompt: "Run terraform_apply for azure-demo" },
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
    placeholder: "Select an MCP server, then ask for capabilities or workflows...",
    workflowTitle: "Guided Workflow",
    workflowSteps: [
      "Select MCP server",
      "Capture requirements",
      "Generate Terraform",
      "Plan and apply",
    ],
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
  if (workflowTitle) workflowTitle.textContent = context.workflowTitle;
  if (welcomeMessage) welcomeMessage.textContent = context.welcome;
  if (promptInput) promptInput.placeholder = context.placeholder;

  if (workflowList) {
    workflowList.innerHTML = "";
    context.workflowSteps.forEach((step) => {
      const li = document.createElement("li");
      li.textContent = step;
      workflowList.appendChild(li);
    });
  }

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

  setStatus("Running");
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
      setStatus("Error");
      return;
    }

    await parseSse(response, (event) => {
      if (event.type === "RUN_STARTED") {
        pendingStart = Date.now();
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
      if (event.type === "RUN_ERROR") {
        addMessage("assistant", event.message || "Agent error");
        setStatus("Error");
        sendBtn.disabled = false;
      }
      if (event.type === "RUN_FINISHED") {
        updateLatency(startedAt);
        setStatus("Idle");
        sendBtn.disabled = false;
      }
    });
  } catch (error) {
    console.error("Failed to send message", error);
    addMessage("assistant", "Error: failed while streaming agent response.");
    setStatus("Error");
  } finally {
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
    if (data.active) {
      awsIdentity.style.display = "flex";
      awsAccountLabel.innerHTML = `AWS: ${data.account} <small style="opacity: 0.7; margin-left: 5px;">(${data.profile})</small>`;
      awsLoginBtn.textContent = "Refresh CLI";
      awsLoginBtn.classList.remove("btn-primary");
      awsLoginBtn.classList.add("btn-secondary");
    } else {
      awsIdentity.style.display = "none";
      awsLoginBtn.textContent = "CLI Login";
      awsLoginBtn.classList.remove("btn-secondary");
      awsLoginBtn.classList.add("btn-primary");
    }
  } catch (error) {
    console.error("Failed to fetch AWS identity", error);
  }
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

  const profile = prompt("Enter AWS Profile name (e.g. sso-profile) or leave blank for 'default':", "default");
  if (profile === null) return;

  await fetch("/api/aws/profile", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ profile })
  });

  awsLoginBtn.disabled = true;
  awsLoginBtn.textContent = "Launching...";
  try {
    const response = await fetch("/api/aws/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ profile })
    });
    const data = await response.json();
    if (data.success) {
      alert(`CLI Login process started for profile '${profile}'! Please check your terminal or browser.`);
      addMessage("assistant", `AWS CLI Login initiated for profile: ${profile}. If no browser tab opened automatically, please run 'aws sso login --profile ${profile}' in your terminal.`);
      setTimeout(refreshAwsIdentity, 5000);
    } else {
      alert(data.error || "Failed to trigger login");
    }
  } catch (error) {
    alert("Error triggering login");
  } finally {
    awsLoginBtn.disabled = false;
    awsLoginBtn.textContent = "Refresh CLI";
  }
});

mcpSelect.addEventListener("change", () => {
  applyCloudContext();
  loadCapabilities();
});

setInterval(refreshAwsIdentity, 30000);

loadModels();
applyCloudContext();
loadCapabilities();
