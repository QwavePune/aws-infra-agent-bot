const chatStream = document.getElementById("chatStream");
const composer = document.getElementById("composer");
const promptInput = document.getElementById("promptInput");
const sendBtn = document.getElementById("sendBtn");
const statusMeta = document.getElementById("statusMeta");
const modelSelect = document.getElementById("modelSelect");
const mcpSelect = document.getElementById("mcpSelect");
const threadIdLabel = document.getElementById("threadId");
const providerLabel = document.getElementById("providerLabel");
const latencyLabel = document.getElementById("latencyLabel");
const promptChips = document.querySelectorAll(".prompt-chip");
const capabilitiesContent = document.getElementById("capabilitiesContent");

let threadId = crypto.randomUUID();
let currentAssistantBubble = null;
let pendingStart = null;

if (threadIdLabel) {
  threadIdLabel.textContent = threadId;
}

const MODEL_SEPARATOR = "::";

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
    modelSelect.innerHTML = "<option value=\"openai::gpt-4o-mini\">OpenAI · gpt-4o-mini</option>";
  }
};

const updateProviderLabel = () => {
  const selected = modelSelect.value.split(MODEL_SEPARATOR);
  providerLabel.textContent = selected[0] || "unknown";
};

modelSelect.addEventListener("change", updateProviderLabel);

const categorizeTools = (tools) => {
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
    // Prefer the richer description when duplicate tool names appear.
    if (currentDesc.length > existingDesc.length) {
      dedupedMap.set(name, tool);
    }
  });

  const groups = {
    "Discovery & Read-Only": [],
    "AWS Infra Automation": [],
    "Workflow Orchestration": [],
    "Terraform Lifecycle (Generic)": [],
    "Identity & Access": [],
    "Other Tools": [],
  };

  [...dedupedMap.values()].forEach((tool) => {
    const name = (tool.name || "").trim();
    if (name === "list_account_inventory" || name === "list_aws_resources" || name === "describe_resource") {
      groups["Discovery & Read-Only"].push(tool);
    } else if (name.startsWith("create_")) {
      groups["AWS Infra Automation"].push(tool);
    } else if (name.startsWith("start_") || name.startsWith("update_") || name.startsWith("review_")) {
      groups["Workflow Orchestration"].push(tool);
    } else if (name.startsWith("terraform_") || name === "get_infrastructure_state") {
      groups["Terraform Lifecycle (Generic)"].push(tool);
    } else if (name === "get_user_permissions") {
      groups["Identity & Access"].push(tool);
    } else {
      groups["Other Tools"].push(tool);
    }
  });

  return groups;
};

const renderCapabilities = (tools) => {
  if (!capabilitiesContent) return;
  const groups = categorizeTools(tools || []);
  const serviceSummary = [
    {
      title: "Discovery & Inventory",
      description: "Account-wide listing and detailed resource lookups across regions.",
      active: groups["Discovery & Read-Only"].length > 0,
      hint: "Ask: List all resources in my account",
    },
    {
      title: "Compute",
      description: "Provision and manage EC2, Lambda, and ECS deployment flows.",
      active: groups["AWS Infra Automation"].some((t) => ["create_ec2_instance", "create_lambda_function", "create_ecs_service"].includes(t.name)),
      hint: "Ask: Show ECS capabilities",
    },
    {
      title: "Storage",
      description: "S3 bucket provisioning and related infrastructure automation.",
      active: groups["AWS Infra Automation"].some((t) => t.name === "create_s3_bucket"),
      hint: "Ask: Show S3 capabilities",
    },
    {
      title: "Database",
      description: "RDS provisioning workflows and deployment support.",
      active: groups["AWS Infra Automation"].some((t) => t.name === "create_rds_instance"),
      hint: "Ask: Show RDS capabilities",
    },
    {
      title: "Networking",
      description: "VPC and subnet-oriented infrastructure setup and validation.",
      active: groups["AWS Infra Automation"].some((t) => t.name === "create_vpc"),
      hint: "Ask: Show VPC capabilities",
    },
    {
      title: "Terraform Lifecycle",
      description: "Generic plan, apply, destroy, and state operations.",
      active: groups["Terraform Lifecycle (Generic)"].length > 0,
      hint: "Ask: Show Terraform capabilities",
    },
    {
      title: "Identity & Access",
      description: "AWS identity checks and permissions context.",
      active: groups["Identity & Access"].length > 0,
      hint: "Ask: Show IAM capabilities",
    },
    {
      title: "Guided Workflows",
      description: "Multi-step orchestration with preflight validation gates.",
      active: groups["Workflow Orchestration"].length > 0,
      hint: "Ask: Show workflow capabilities",
    },
  ];

  const activeCards = serviceSummary
    .filter((item) => item.active)
    .map(
      (item) =>
        `<div class="cap-tool"><div class="cap-tool-name">${escapeHtml(item.title)}</div><div class="cap-tool-desc">${escapeHtml(item.description)}</div><div class="cap-tool-hint">${escapeHtml(item.hint)}</div></div>`
    )
    .join("");

  capabilitiesContent.innerHTML = activeCards || "No capabilities available.";
};

const loadCapabilities = async () => {
  if (!capabilitiesContent) return;
  capabilitiesContent.textContent = "Loading capabilities...";

  if (mcpSelect.value === "none") {
    capabilitiesContent.textContent = "MCP disabled. Enable an MCP server to view executable capabilities.";
    return;
  }

  try {
    const response = await fetch("/api/mcp/tools");
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

mcpSelect.addEventListener("change", () => {
  loadCapabilities();
});

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

promptChips.forEach((chip) => {
  chip.addEventListener("click", () => {
    const prompt = chip.dataset.prompt || "";
    if (!prompt) return;
    promptInput.value = prompt;
    promptInput.style.height = "auto";
    promptInput.style.height = `${promptInput.scrollHeight}px`;
    promptInput.focus();
  });
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

// AWS Login & Identity Handling
const awsLoginBtn = document.getElementById("awsLoginBtn");
const awsConsoleBtn = document.getElementById("awsConsoleBtn");
const awsIdentity = document.getElementById("awsIdentity");
const awsAccountLabel = document.getElementById("awsAccount");

const refreshAwsIdentity = async () => {
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
  window.open("https://console.aws.amazon.com", "_blank");
});

awsLoginBtn.addEventListener("click", async () => {
  const profile = prompt("Enter AWS Profile name (e.g. sso-profile) or leave blank for 'default':", "default");
  if (profile === null) return; // Cancelled

  // Set the profile first
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
      // Refresh identity after a short delay
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

// Refresh identity every 30 seconds
setInterval(refreshAwsIdentity, 30000);
refreshAwsIdentity();

loadModels();
loadCapabilities();
