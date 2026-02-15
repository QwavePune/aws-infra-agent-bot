// Session & Auth State
let sessionActive = false;
let currentProfile = null;
let currentAccount = null;

// DOM Elements
const loginModal = document.getElementById("loginModal");
const appShell = document.getElementById("appShell");
const usernameInput = document.getElementById("usernameInput");
const passwordInput = document.getElementById("passwordInput");
const basicLoginBtn = document.getElementById("basicLoginBtn");
const ssoProfileInput = document.getElementById("ssoProfileInput");
const ssoLoginBtn = document.getElementById("ssoLoginBtn");
const ssoStatus = document.getElementById("ssoStatus");
const ssoProgressBar = document.getElementById("ssoProgressBar");
const ssoStatusText = document.getElementById("ssoStatusText");
const ssoDoneBtn = document.getElementById("ssoDoneBtn");
const loginError = document.getElementById("loginError");
const loginLoading = document.getElementById("loginLoading");
const profileMenuBtn = document.getElementById("profileMenuBtn");
const profileDropdown = document.getElementById("profileDropdown");
const logoutBtn = document.getElementById("logoutBtn");
const switchProfileBtn = document.getElementById("switchProfileBtn");

// Chat & Agent Elements
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

// AWS UI Elements
const awsConsoleBtn = document.getElementById("awsConsoleBtn");
const awsIdentity = document.getElementById("awsIdentity");
const awsAccountLabel = document.getElementById("awsAccount");

let threadId = crypto.randomUUID();
let currentAssistantBubble = null;
let pendingStart = null;
let ssoPoll = null;

threadIdLabel.textContent = threadId;

const MODEL_SEPARATOR = "::";

// ========== SESSION MANAGEMENT ==========
const showLoginModal = () => {
  loginModal.classList.add("modal-active");
  appShell.style.display = "none";
  sessionActive = false;
};

const hideLoginModal = () => {
  loginModal.classList.remove("modal-active");
  appShell.style.display = "block";
  sessionActive = true;
};

const checkSessionOnLoad = async () => {
  try {
    const response = await fetch("/api/aws/identity");
    const data = await response.json();
    if (data.active) {
      currentProfile = data.profile;
      currentAccount = data.account;
      hideLoginModal();
      refreshAwsIdentity();
    } else {
      showLoginModal();
    }
  } catch (error) {
    console.error("Session check failed:", error);
    showLoginModal();
  }
};

// ========== LOGIN FLOW ==========
const loginWithUsername = async () => {
  const username = usernameInput.value.trim();
  const password = passwordInput.value || "";
  loginError.style.display = "none";
  loginLoading.style.display = "flex";
  basicLoginBtn.disabled = true;
  try {
    const resp = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password })
    });
    const data = await resp.json();
    if (data.success) {
      loginLoading.style.display = "none";
      hideLoginModal();
      addMessage("assistant", `✅ Signed in as ${data.username}. (Local demo account)`);
      loadModels();
    } else {
      loginLoading.style.display = "none";
      loginError.textContent = data.error || "Invalid credentials";
      loginError.style.display = "block";
      basicLoginBtn.disabled = false;
    }
  } catch (err) {
    loginLoading.style.display = "none";
    loginError.textContent = "Network error while logging in";
    loginError.style.display = "block";
    basicLoginBtn.disabled = false;
  }
};

const loginWithSsoShell = async () => {
  const profile = (ssoProfileInput && ssoProfileInput.value.trim()) || "default";
  loginError.style.display = "none";
  loginLoading.style.display = "flex";
  try {
    // Set server profile
    await fetch("/api/aws/profile", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ profile })
    });

    // Open terminal and run aws sso login
    const resp = await fetch("/api/aws/login_shell", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ profile })
    });
    const data = await resp.json();
    if (!data.success) {
      loginLoading.style.display = "none";
      loginError.textContent = data.error || "Failed to open terminal for SSO login";
      loginError.style.display = "block";
      return;
    }

    addMessage("assistant", "✅ Opened a terminal window. In the new terminal, follow the prompts to complete SSO.");

    // Show SSO progress UI
    if (ssoStatus) ssoStatus.style.display = "block";
    let attempts = 0;
    const maxAttempts = 60; // ~2 minutes
    if (ssoProgressBar) ssoProgressBar.style.width = "0%";

    ssoPoll = setInterval(async () => {
      attempts++;
      try {
        const idResp = await fetch("/api/aws/identity");
        const idData = await idResp.json();
        const pct = Math.min(100, Math.round((attempts / maxAttempts) * 100));
        if (ssoProgressBar) ssoProgressBar.style.width = `${pct}%`;
        if (idData.active) {
          clearInterval(ssoPoll);
          ssoPoll = null;
          loginLoading.style.display = "none";
          if (ssoStatus) ssoStatus.style.display = "none";
          currentProfile = idData.profile;
          currentAccount = idData.account;
          hideLoginModal();
          loadModels();
          addMessage("assistant", `✅ AWS session active: account ${idData.account}`);
        } else if (attempts > maxAttempts) {
          clearInterval(ssoPoll);
          ssoPoll = null;
          loginLoading.style.display = "none";
          if (ssoStatus) ssoStatus.style.display = "block";
          if (ssoStatusText) ssoStatusText.textContent = "Timed out waiting for SSO login. Please complete login in the terminal and try again.";
        }
      } catch (err) {
        console.error("Poll identity error", err);
      }
    }, 2000);

  } catch (err) {
    loginLoading.style.display = "none";
    loginError.textContent = "Failed to start SSO flow";
    loginError.style.display = "block";
  }
};

basicLoginBtn.addEventListener("click", loginWithUsername);
usernameInput.addEventListener("keydown", (e) => { if (e.key === "Enter") loginWithUsername(); });
passwordInput.addEventListener("keydown", (e) => { if (e.key === "Enter") loginWithUsername(); });
ssoLoginBtn.addEventListener("click", loginWithSsoShell);

// ========== PROFILE DROPDOWN ==========
profileMenuBtn.addEventListener("click", (e) => {
  e.preventDefault();
  profileDropdown.style.display = profileDropdown.style.display === "none" ? "block" : "none";
});

document.addEventListener("click", (e) => {
  if (!profileMenuBtn.contains(e.target) && !profileDropdown.contains(e.target)) {
    profileDropdown.style.display = "none";
  }
});

logoutBtn.addEventListener("click", async (e) => {
  e.preventDefault();
  try {
    await fetch("/api/auth/logout", { method: "POST" });
    sessionActive = false;
    currentProfile = null;
    currentAccount = null;
    profileDropdown.style.display = "none";
    conversation_store = {};
    showLoginModal();
    chatStream.innerHTML = '<div class="message assistant"><div class="message-meta">Assistant</div><div class="message-body">Welcome back. Ask me anything about AWS infra, guardrails, or deployments.</div></div>';
  } catch (error) {
    console.error("Logout failed:", error);
  }
});

switchProfileBtn.addEventListener("click", () => {
  showLoginModal();
  usernameInput.focus();
});

// Manual SSO completion button
if (typeof ssoDoneBtn !== 'undefined' && ssoDoneBtn) {
  ssoDoneBtn.addEventListener('click', async () => {
    if (ssoPoll) {
      // Do an immediate check
      try {
        const idResp = await fetch('/api/aws/identity');
        const idData = await idResp.json();
        if (idData.active) {
          clearInterval(ssoPoll);
          ssoPoll = null;
          loginLoading.style.display = 'none';
          if (ssoStatus) ssoStatus.style.display = 'none';
          currentProfile = idData.profile;
          currentAccount = idData.account;
          hideLoginModal();
          loadModels();
          addMessage('assistant', `✅ AWS session active: account ${idData.account}`);
          return;
        }
      } catch (err) {
        console.error('SSO manual check failed', err);
      }
    }
    // If not active yet, update UI
    if (ssoStatusText) ssoStatusText.textContent = 'Still waiting for SSO; please complete login in the terminal.';
  });
}

// ========== CHAT & AGENT FUNCTIONS ==========
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

// ========== AWS INTEGRATION ==========
const refreshAwsIdentity = async () => {
  try {
    const response = await fetch("/api/aws/identity");
    const data = await response.json();
    if (data.active) {
      awsIdentity.style.display = "flex";
      awsAccountLabel.innerHTML = `AWS: ${data.account} <small style="opacity: 0.7; margin-left: 5px;">(${data.profile})</small>`;
    } else {
      awsIdentity.style.display = "none";
    }
  } catch (error) {
    console.error("Failed to fetch AWS identity", error);
  }
};

awsConsoleBtn.addEventListener("click", async () => {
  try {
    awsConsoleBtn.disabled = true;
    awsConsoleBtn.textContent = "Opening...";
    const resp = await fetch('/api/aws/console', { method: 'POST' });
    const data = await resp.json();
    if (data && data.success && data.url) {
      window.open(data.url, '_blank');
    } else {
      alert('Failed to generate AWS Console link: ' + (data.error || 'unknown'));
    }
  } catch (err) {
    console.error('Console open error', err);
    alert('Error opening AWS Console');
  } finally {
    awsConsoleBtn.disabled = false;
    awsConsoleBtn.textContent = 'AWS Console';
  }
});

// Refresh identity periodically
setInterval(refreshAwsIdentity, 30000);

// Session & Conversation Store
let conversation_store = {};

// ========== INITIALIZATION ==========
window.addEventListener("load", () => {
  checkSessionOnLoad();
});

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

awsConsoleBtn.addEventListener("click", async () => {
  try {
    awsConsoleBtn.disabled = true;
    awsConsoleBtn.textContent = "Opening...";
    // Request a federated console URL from the server
    const resp = await fetch('/api/aws/console', { method: 'POST' });
    const data = await resp.json();
    if (data && data.success && data.url) {
      window.open(data.url, '_blank');
    } else {
      alert('Failed to generate AWS Console link: ' + (data.error || 'unknown'));
    }
  } catch (err) {
    console.error('Console open error', err);
    alert('Error opening AWS Console');
  } finally {
    awsConsoleBtn.disabled = false;
    awsConsoleBtn.textContent = 'AWS Console';
  }
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
