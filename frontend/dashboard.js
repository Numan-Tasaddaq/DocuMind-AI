const historyList = document.getElementById("history-list");
const chatThread = document.getElementById("chat-thread");
const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const newChatBtn = document.getElementById("new-chat-btn");
const docUpload = document.getElementById("doc-upload");
const uploadedFiles = document.getElementById("uploaded-files");
const logoutBtn = document.getElementById("logout-btn");
const settingsToggle = document.getElementById("settings-toggle");
const settingsMenu = document.getElementById("settings-menu");
const openProfileViewBtn = document.getElementById("open-profile-view");
const dashboardMessage = document.getElementById("dashboard-message");
const conversationTitle = document.getElementById("conversation-title");

const API_BASE_URL = "http://127.0.0.1:8000";
const MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024;
const MAX_UPLOAD_FILES = 5;
const ALLOWED_EXTENSIONS = new Set(["pdf", "doc", "docx", "xls", "xlsx"]);
const ALLOWED_MIME_TYPES = new Set([
  "application/pdf",
  "application/msword",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/vnd.ms-excel",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
]);

const storageUser = localStorage.getItem("documind_user");
const storageToken = localStorage.getItem("documind_access_token");
if (!storageUser || !storageToken) {
  window.location.href = "index.html";
}

const currentUser = JSON.parse(storageUser || "{}");
const uploadedStorageKey = `documind_uploaded_${currentUser.id || currentUser.email || "guest"}`;

const state = {
  conversations: [],
  activeConversationId: null,
  uploaded: [],
  openMenuConversationId: null,
  renameConversationId: null
};

function setDashboardMessage(text, type = "") {
  dashboardMessage.textContent = text;
  dashboardMessage.classList.remove("ok", "error");
  if (type) {
    dashboardMessage.classList.add(type);
  }
}

function loadUploadedState() {
  try {
    const raw = localStorage.getItem(uploadedStorageKey);
    const parsed = raw ? JSON.parse(raw) : [];
    state.uploaded = Array.isArray(parsed) ? parsed : [];
  } catch (error) {
    state.uploaded = [];
  }
}

function persistUploadedState() {
  localStorage.setItem(uploadedStorageKey, JSON.stringify(state.uploaded));
}

function handleUnauthorized() {
  localStorage.removeItem("documind_access_token");
  localStorage.removeItem("documind_user");
  window.location.href = "index.html";
}

async function apiRequest(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${storageToken}`,
      ...(options.headers || {})
    }
  });

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401) {
      handleUnauthorized();
      return null;
    }
    throw new Error(data.detail || "Request failed.");
  }

  return data;
}

function getActiveConversation() {
  return state.conversations.find((conversation) => conversation.id === state.activeConversationId) || null;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatTimestamp(isoValue) {
  if (!isoValue) {
    return "No date";
  }
  const date = new Date(isoValue);
  if (Number.isNaN(date.getTime())) {
    return "Unknown date";
  }
  return date.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

function renderHistory() {
  historyList.innerHTML = "";
  state.conversations.forEach((conversation) => {
    const item = document.createElement("article");
    item.className = `history-item ${conversation.id === state.activeConversationId ? "active" : ""}`;
    const safeTitle = escapeHtml(conversation.title);
    item.innerHTML = `
      <button type="button" class="history-item-main" data-conv-id="${conversation.id}">
        ${
          state.renameConversationId === conversation.id
            ? `<input type="text" class="history-rename-input" value="${safeTitle}" maxlength="160" aria-label="Rename conversation" />`
            : `<h4>${safeTitle}</h4>`
        }
        <p>${formatTimestamp(conversation.last_message_at || conversation.updated_at)}</p>
      </button>
      <div class="history-item-actions">
        <button type="button" class="history-action-btn menu" data-conv-id="${conversation.id}" aria-label="Open chat options">
          <i class="fas fa-ellipsis"></i>
        </button>
        <div class="history-actions-menu ${state.openMenuConversationId === conversation.id ? "" : "hidden"}">
          <button type="button" class="history-menu-option rename" data-conv-id="${conversation.id}">
            <i class="fas fa-pen"></i>
            Rename
          </button>
          <button type="button" class="history-menu-option delete" data-conv-id="${conversation.id}">
            <i class="fas fa-trash"></i>
            Delete
          </button>
        </div>
      </div>
    `;

    const mainBtn = item.querySelector(".history-item-main");
    const menuBtn = item.querySelector(".history-action-btn.menu");
    const renameBtn = item.querySelector(".history-menu-option.rename");
    const deleteBtn = item.querySelector(".history-menu-option.delete");
    const renameInput = item.querySelector(".history-rename-input");

    mainBtn.addEventListener("click", async () => {
      if (state.renameConversationId === conversation.id) {
        return;
      }
      await loadConversation(conversation.id);
    });

    menuBtn.addEventListener("click", (event) => {
      event.stopPropagation();
      state.openMenuConversationId = state.openMenuConversationId === conversation.id ? null : conversation.id;
      renderHistory();
    });

    renameBtn.addEventListener("click", (event) => {
      event.stopPropagation();
      state.openMenuConversationId = null;
      state.renameConversationId = conversation.id;
      renderHistory();
    });

    if (renameInput) {
      const saveRename = async () => {
        const cleaned = renameInput.value.trim();
        state.renameConversationId = null;

        if (!cleaned) {
          setDashboardMessage("Conversation title cannot be empty.", "error");
          renderHistory();
          return;
        }

        if (cleaned === conversation.title) {
          renderHistory();
          return;
        }

        try {
          const updated = await apiRequest(`/api/chats/${conversation.id}`, {
            method: "PATCH",
            body: JSON.stringify({ title: cleaned })
          });
          if (!updated) {
            renderHistory();
            return;
          }

          const index = state.conversations.findIndex((itemConversation) => itemConversation.id === updated.id);
          if (index >= 0) {
            state.conversations[index] = updated;
          }
          renderHistory();
          renderThread();
        } catch (error) {
          setDashboardMessage(error.message || "Unable to rename conversation.", "error");
          renderHistory();
        }
      };

      setTimeout(() => {
        renameInput.focus();
        renameInput.select();
      }, 0);

      renameInput.addEventListener("click", (event) => {
        event.stopPropagation();
      });

      renameInput.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
          event.preventDefault();
          saveRename();
          return;
        }
        if (event.key === "Escape") {
          event.preventDefault();
          state.renameConversationId = null;
          renderHistory();
        }
      });

      renameInput.addEventListener("blur", () => {
        if (state.renameConversationId === conversation.id) {
          saveRename();
        }
      });
    }

    deleteBtn.addEventListener("click", async (event) => {
      event.stopPropagation();
      state.openMenuConversationId = null;
      const hasConfirmed = confirm(`Delete "${conversation.title}"?`);
      if (!hasConfirmed) {
        renderHistory();
        return;
      }

      try {
        await apiRequest(`/api/chats/${conversation.id}`, { method: "DELETE" });
        state.conversations = state.conversations.filter((itemConversation) => itemConversation.id !== conversation.id);

        if (!state.conversations.length) {
          const created = await createConversation("New Chat");
          if (created) {
            state.conversations = [created];
            state.activeConversationId = created.id;
          }
        } else if (state.activeConversationId === conversation.id) {
          state.activeConversationId = state.conversations[0].id;
          await loadConversation(state.activeConversationId);
        }

        renderHistory();
        renderThread();
      } catch (error) {
        setDashboardMessage(error.message || "Unable to delete conversation.", "error");
      }
    });

    historyList.appendChild(item);
  });
}

function renderThread() {
  const active = getActiveConversation();
  if (!active) {
    conversationTitle.textContent = "Document Assistant";
    chatThread.innerHTML = "";
    return;
  }

  conversationTitle.textContent = active.title;
  chatThread.innerHTML = "";

  if (!active.messages || !active.messages.length) {
    const bubble = document.createElement("article");
    bubble.className = "message assistant";
    bubble.textContent = "New chat started. Ask about your documents.";
    chatThread.appendChild(bubble);
    return;
  }

  active.messages.forEach((message) => {
    const bubble = document.createElement("article");
    bubble.className = `message ${message.role}`;
    bubble.textContent = message.content;
    chatThread.appendChild(bubble);
  });

  chatThread.scrollTop = chatThread.scrollHeight;
}

function renderUploadedFiles() {
  uploadedFiles.innerHTML = "";
  state.uploaded.forEach((name) => {
    const chip = document.createElement("span");
    chip.className = "file-chip";
    chip.textContent = name;
    uploadedFiles.appendChild(chip);
  });
}

function getExtension(fileName) {
  const parts = fileName.toLowerCase().split(".");
  return parts.length > 1 ? parts.pop() : "";
}

function isAllowedFileType(file) {
  const extension = getExtension(file.name);
  if (!ALLOWED_EXTENSIONS.has(extension)) {
    return false;
  }
  return !file.type || ALLOWED_MIME_TYPES.has(file.type);
}

async function isEncryptedPdf(file) {
  if (getExtension(file.name) !== "pdf") {
    return false;
  }

  const headerChunk = await file.slice(0, 1024 * 1024).arrayBuffer();
  const headerText = new TextDecoder("latin1").decode(new Uint8Array(headerChunk));
  return /\/Encrypt\b/i.test(headerText);
}

async function createConversation(title = "New Chat") {
  try {
    return await apiRequest("/api/chats", {
      method: "POST",
      body: JSON.stringify({ title })
    });
  } catch (error) {
    setDashboardMessage(error.message || "Unable to create new conversation.", "error");
    return null;
  }
}

async function fetchConversations() {
  try {
    const list = await apiRequest("/api/chats");
    if (!list) {
      return;
    }
    state.conversations = list.map((conversation) => ({ ...conversation, messages: [] }));
  } catch (error) {
    setDashboardMessage(error.message || "Unable to load conversation history.", "error");
  }
}

async function loadConversation(conversationId) {
  try {
    const detail = await apiRequest(`/api/chats/${conversationId}`);
    if (!detail) {
      return;
    }

    const index = state.conversations.findIndex((conversation) => conversation.id === detail.id);
    if (index >= 0) {
      state.conversations[index] = detail;
    } else {
      state.conversations.unshift(detail);
    }

    state.activeConversationId = detail.id;
    renderHistory();
    renderThread();
  } catch (error) {
    setDashboardMessage(error.message || "Unable to load selected conversation.", "error");
  }
}

chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = chatInput.value.trim();
  if (!text) {
    return;
  }

  const active = getActiveConversation();
  if (!active) {
    setDashboardMessage("No active conversation selected.", "error");
    return;
  }

  chatInput.value = "";
  chatInput.disabled = true;

  const optimisticUser = {
    id: `tmp-u-${Date.now()}`,
    role: "user",
    content: text,
    created_at: new Date().toISOString()
  };
  const optimisticAssistant = {
    id: `tmp-a-${Date.now() + 1}`,
    role: "assistant",
    content: "Thinking...",
    created_at: new Date().toISOString()
  };

  active.messages = active.messages || [];
  active.messages.push(optimisticUser, optimisticAssistant);
  renderThread();

  try {
    const data = await apiRequest(`/api/chats/${active.id}/messages`, {
      method: "POST",
      body: JSON.stringify({
        prompt: text,
        uploaded_files: state.uploaded
      })
    });
    if (!data) {
      return;
    }

    await loadConversation(active.id);
  } catch (error) {
    optimisticAssistant.content = error.message || "Unable to get AI response right now.";
    renderThread();
    setDashboardMessage(optimisticAssistant.content, "error");
  } finally {
    chatInput.disabled = false;
    chatInput.focus();
  }
});

chatInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    chatForm.requestSubmit();
  }
});

newChatBtn.addEventListener("click", async () => {
  const created = await createConversation(`New Conversation ${state.conversations.length + 1}`);
  if (!created) {
    return;
  }

  state.conversations.unshift(created);
  state.activeConversationId = created.id;
  renderHistory();
  renderThread();
});

docUpload.addEventListener("change", async () => {
  const files = Array.from(docUpload.files || []);
  if (!files.length) {
    return;
  }

  if (files.length > MAX_UPLOAD_FILES) {
    setDashboardMessage(`You can select up to ${MAX_UPLOAD_FILES} files at a time.`, "error");
    docUpload.value = "";
    return;
  }

  const accepted = [];
  for (const file of files) {
    if (!isAllowedFileType(file)) {
      setDashboardMessage("Only PDF, DOC, DOCX, XLS, and XLSX files are allowed.", "error");
      docUpload.value = "";
      return;
    }

    if (file.size > MAX_FILE_SIZE_BYTES) {
      setDashboardMessage(`"${file.name}" exceeds the 10 MB limit.`, "error");
      docUpload.value = "";
      return;
    }

    if (await isEncryptedPdf(file)) {
      setDashboardMessage(`"${file.name}" is encrypted/password-protected and cannot be uploaded.`, "error");
      docUpload.value = "";
      return;
    }

    accepted.push(file);
  }

  if (state.uploaded.length + accepted.length > MAX_UPLOAD_FILES) {
    setDashboardMessage(`Maximum ${MAX_UPLOAD_FILES} uploaded files allowed in this session.`, "error");
    docUpload.value = "";
    return;
  }

  accepted.forEach((file) => state.uploaded.push(file.name));
  persistUploadedState();
  renderUploadedFiles();
  setDashboardMessage(`Uploaded ${accepted.length} file(s).`, "ok");
  docUpload.value = "";
});

logoutBtn.addEventListener("click", () => {
  localStorage.removeItem("documind_access_token");
  localStorage.removeItem("documind_user");
  window.location.href = "index.html";
});

settingsToggle.addEventListener("click", () => {
  settingsMenu.classList.toggle("hidden");
});

openProfileViewBtn.addEventListener("click", () => {
  window.location.href = "profile.html";
  settingsMenu.classList.add("hidden");
});

document.addEventListener("click", (event) => {
  if (!settingsMenu.contains(event.target) && !settingsToggle.contains(event.target)) {
    settingsMenu.classList.add("hidden");
  }
  if (!event.target.closest(".history-item-actions") && state.openMenuConversationId) {
    state.openMenuConversationId = null;
    renderHistory();
  }
});

async function initDashboard() {
  loadUploadedState();
  renderUploadedFiles();

  await fetchConversations();
  if (!state.conversations.length) {
    const created = await createConversation("Policy Handbook Q&A");
    if (created) {
      state.conversations.push(created);
    }
  }

  if (state.conversations.length) {
    state.activeConversationId = state.conversations[0].id;
    await loadConversation(state.activeConversationId);
  } else {
    renderHistory();
    renderThread();
  }
}

initDashboard();
