const state = {
  history: [],
  profile: "",
  memory: null,
  sending: false,
};

const els = {
  modelStatus: document.querySelector("#modelStatus"),
  statusDot: document.querySelector(".status-dot"),
  messages: document.querySelector("#messages"),
  composer: document.querySelector("#composer"),
  chatInput: document.querySelector("#chatInput"),
  sendButton: document.querySelector("#sendButton"),
  refreshState: document.querySelector("#refreshState"),
  clearHistory: document.querySelector("#clearHistory"),
  memoryText: document.querySelector("#memoryText"),
  memoryCategory: document.querySelector("#memoryCategory"),
  saveMemory: document.querySelector("#saveMemory"),
  memoryList: document.querySelector("#memoryList"),
  profileEditor: document.querySelector("#profileEditor"),
  saveProfile: document.querySelector("#saveProfile"),
  chatgptFile: document.querySelector("#chatgptFile"),
  importDraft: document.querySelector("#importDraft"),
  toast: document.querySelector("#toast"),
};

document.addEventListener("DOMContentLoaded", () => {
  wireTabs();
  wireEvents();
  refreshState();
});

function wireEvents() {
  els.composer.addEventListener("submit", async (event) => {
    event.preventDefault();
    await sendMessage();
  });

  els.chatInput.addEventListener("keydown", async (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      await sendMessage();
    }
  });

  els.refreshState.addEventListener("click", refreshState);
  els.clearHistory.addEventListener("click", clearHistory);
  els.saveMemory.addEventListener("click", saveMemory);
  els.saveProfile.addEventListener("click", saveProfile);
  els.chatgptFile.addEventListener("change", importChatGPTFile);
}

function wireTabs() {
  for (const button of document.querySelectorAll(".tab")) {
    button.addEventListener("click", () => {
      for (const tab of document.querySelectorAll(".tab")) {
        tab.classList.toggle("active", tab === button);
      }
      for (const panel of document.querySelectorAll(".tab-panel")) {
        panel.classList.toggle("active", panel.id === `tab-${button.dataset.tab}`);
      }
    });
  }
}

async function refreshState() {
  const data = await request("/api/state");
  state.history = data.history ?? [];
  state.profile = data.profile ?? "";
  state.memory = data.memory ?? {};
  els.profileEditor.value = state.profile;
  renderModel(data.model);
  renderMessages();
  renderMemory();
}

function renderModel(model) {
  const available = Boolean(model?.available);
  els.statusDot.classList.toggle("offline", !available);
  els.modelStatus.textContent = available ? model.name : "离线模式";
}

function renderMessages() {
  els.messages.replaceChildren();

  if (state.history.length === 0) {
    addMessage("assistant", "晚上好。我在这里。你可以慢慢说。");
    return;
  }

  for (const message of state.history) {
    addMessage(message.role, message.content);
  }
  scrollMessages();
}

function addMessage(role, content, options = {}) {
  const message = document.createElement("article");
  message.className = `message ${role}`;
  if (options.pending) {
    message.dataset.pending = "true";
  }

  const speaker = document.createElement("div");
  speaker.className = "speaker";
  speaker.textContent = role === "user" ? "你" : "樱茗";

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = content;

  message.append(speaker, bubble);
  els.messages.append(message);
  scrollMessages();
  return message;
}

async function sendMessage() {
  const text = els.chatInput.value.trim();
  if (!text || state.sending) {
    return;
  }

  state.sending = true;
  els.sendButton.disabled = true;
  els.chatInput.value = "";
  addMessage("user", text);
  const pending = addMessage("assistant", "我在想。", { pending: true });

  try {
    const data = await request("/api/chat", {
      method: "POST",
      body: { message: text },
    });
    state.history = data.history ?? [];
    renderMessages();
  } catch (error) {
    pending.querySelector(".bubble").textContent = `这边暂时没有接好：${error.message}`;
    showToast(error.message);
  } finally {
    state.sending = false;
    els.sendButton.disabled = false;
    els.chatInput.focus();
  }
}

async function saveMemory() {
  const text = els.memoryText.value.trim();
  if (!text) {
    showToast("记忆不能为空");
    return;
  }

  const data = await request("/api/memory", {
    method: "POST",
    body: {
      text,
      category: els.memoryCategory.value,
    },
  });
  state.memory = data.memory;
  els.memoryText.value = "";
  renderMemory();
  showToast("已写入长期记忆");
}

async function saveProfile() {
  const data = await request("/api/profile", {
    method: "POST",
    body: { profile: els.profileEditor.value },
  });
  state.profile = data.profile;
  showToast("画像已保存");
}

async function clearHistory() {
  await request("/api/history/clear", { method: "POST", body: {} });
  state.history = [];
  renderMessages();
  showToast("聊天已清空");
}

async function importChatGPTFile(event) {
  const file = event.target.files?.[0];
  if (!file) {
    return;
  }

  try {
    const text = await file.text();
    const conversations = JSON.parse(text);
    const data = await request("/api/import-chatgpt", {
      method: "POST",
      body: { conversations },
    });
    els.importDraft.value = data.profile_draft;
    showToast(`已提取 ${data.user_message_count} 条用户消息`);
  } catch (error) {
    showToast(error.message);
  } finally {
    event.target.value = "";
  }
}

function renderMemory() {
  const memories = state.memory?.long_term ?? [];
  els.memoryList.replaceChildren();

  if (memories.length === 0) {
    const empty = document.createElement("div");
    empty.className = "memory-item";
    empty.textContent = "现在还没有长期记忆。";
    els.memoryList.append(empty);
    return;
  }

  for (const memory of [...memories].reverse()) {
    const item = document.createElement("div");
    item.className = "memory-item";

    const meta = document.createElement("div");
    meta.className = "memory-meta";
    meta.textContent = memory.category ?? "memory";

    const text = document.createElement("div");
    text.textContent = memory.text ?? "";

    item.append(meta, text);
    els.memoryList.append(item);
  }
}

async function request(path, options = {}) {
  const init = {
    method: options.method ?? "GET",
    headers: {},
  };

  if (options.body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(options.body);
  }

  const response = await fetch(path, init);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error ?? "请求失败");
  }
  return data;
}

function showToast(message) {
  els.toast.textContent = message;
  els.toast.classList.add("show");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => {
    els.toast.classList.remove("show");
  }, 2400);
}

function scrollMessages() {
  els.messages.scrollTop = els.messages.scrollHeight;
}

