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

let threadId = crypto.randomUUID();
let currentAssistantBubble = null;
let pendingStart = null;

threadIdLabel.textContent = threadId;

const MODEL_SEPARATOR = "::";

const setStatus = (value) => {
  statusMeta.textContent = value;
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

    const defaultOption = [...modelSelect.options].find((opt) => opt.dataset.default === "true");
    if (defaultOption) {
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
    sendBtn.disabled = false;
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
      toolBubble.innerHTML = `<strong>Tool: ${event.toolName}</strong><br><pre style="background: #1e1e1e; color: #d4d4d4; padding: 10px; border-radius: 4px; overflow-x: auto; font-size: 12px; font-family: 'Consolas', 'Monaco', monospace;">${JSON.stringify(event.result, null, 2)}</pre>`;
      chatStream.scrollTop = chatStream.scrollHeight;
    }
    if (event.type === "RUN_ERROR") {
      addMessage("assistant", event.message || "Agent error");
    }
    if (event.type === "RUN_FINISHED") {
      updateLatency(startedAt);
      setStatus("Idle");
      sendBtn.disabled = false;
    }
  });
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
      awsAccountLabel.textContent = `AWS: ${data.account}`;
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
  awsLoginBtn.disabled = true;
  awsLoginBtn.textContent = "Launching...";
  try {
    const response = await fetch("/api/aws/login", { method: "POST" });
    const data = await response.json();
    if (data.success) {
      alert("CLI Login process started! Please check your terminal or browser.");
      addMessage("assistant", "AWS CLI Login initiated. If no browser tab opened automatically, please run 'aws sso login' in your Mac terminal.");
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
