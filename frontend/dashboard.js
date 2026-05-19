const historyList = document.getElementById("history-list");
const chatThread = document.getElementById("chat-thread");
const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const newChatBtn = document.getElementById("new-chat-btn");
const docUpload = document.getElementById("doc-upload");
const uploadedFiles = document.getElementById("uploaded-files");
const logoutBtn = document.getElementById("logout-btn");
const dashboardMessage = document.getElementById("dashboard-message");
const profileName = document.getElementById("profile-name");
const profileEmail = document.getElementById("profile-email");
const conversationTitle = document.getElementById("conversation-title");
const changePasswordForm = document.getElementById("change-password-form");
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
profileName.textContent = currentUser.full_name || "DocuMind User";
profileEmail.textContent = currentUser.email || "user@example.com";

const state = {
  activeConversationId: "conv-1",
  conversations: [
    {
      id: "conv-1",
      title: "Policy Handbook Q&A",
      timestamp: "Today",
      messages: [
        { role: "assistant", text: "Hi, I am your document copilot. Upload a file and ask anything." }
      ]
    }
  ],
  uploaded: []
};

function setDashboardMessage(text, type = "") {
  dashboardMessage.textContent = text;
  dashboardMessage.classList.remove("ok", "error");
  if (type) {
    dashboardMessage.classList.add(type);
  }
}

function getActiveConversation() {
  return state.conversations.find((conversation) => conversation.id === state.activeConversationId);
}

function renderHistory() {
  historyList.innerHTML = "";
  state.conversations.forEach((conversation) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `history-item ${conversation.id === state.activeConversationId ? "active" : ""}`;
    button.innerHTML = `
      <h4>${conversation.title}</h4>
      <p>${conversation.timestamp}</p>
    `;
    button.addEventListener("click", () => {
      state.activeConversationId = conversation.id;
      renderHistory();
      renderThread();
    });
    historyList.appendChild(button);
  });
}

function renderThread() {
  const active = getActiveConversation();
  if (!active) {
    return;
  }

  conversationTitle.textContent = active.title;
  chatThread.innerHTML = "";

  active.messages.forEach((message) => {
    const bubble = document.createElement("article");
    bubble.className = `message ${message.role}`;
    bubble.textContent = message.text;
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

  // Some browsers may provide an empty MIME type for local files; extension check remains fallback.
  return !file.type || ALLOWED_MIME_TYPES.has(file.type);
}

async function isEncryptedPdf(file) {
  if (getExtension(file.name) !== "pdf") {
    return false;
  }

  // Frontend-only best effort check for encrypted PDFs.
  const headerChunk = await file.slice(0, 1024 * 1024).arrayBuffer();
  const headerText = new TextDecoder("latin1").decode(new Uint8Array(headerChunk));
  return /\/Encrypt\b/i.test(headerText);
}

chatForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const text = chatInput.value.trim();
  if (!text) {
    return;
  }

  const active = getActiveConversation();
  active.messages.push({ role: "user", text });

  // Frontend-only simulated response; backend RAG will replace this.
  const simulated = `I found related information in your uploaded documents. Next, we can connect this to your backend RAG API for real grounded answers.`;
  active.messages.push({ role: "assistant", text: simulated });
  active.timestamp = "Just now";

  chatInput.value = "";
  renderHistory();
  renderThread();
});

newChatBtn.addEventListener("click", () => {
  const id = `conv-${Date.now()}`;
  const title = `New Conversation ${state.conversations.length + 1}`;
  state.conversations.unshift({
    id,
    title,
    timestamp: "Just now",
    messages: [{ role: "assistant", text: "New chat started. Ask about your documents." }]
  });
  state.activeConversationId = id;
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
  renderUploadedFiles();
  setDashboardMessage(`Uploaded ${accepted.length} file(s).`, "ok");
  docUpload.value = "";
});

changePasswordForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const current = document.getElementById("current-password").value.trim();
  const next = document.getElementById("new-password").value.trim();
  const confirm = document.getElementById("confirm-password").value.trim();

  if (!current || !next || !confirm) {
    setDashboardMessage("Please fill all password fields.", "error");
    return;
  }

  if (next.length < 8) {
    setDashboardMessage("New password must be at least 8 characters.", "error");
    return;
  }

  if (next !== confirm) {
    setDashboardMessage("New password and confirmation do not match.", "error");
    return;
  }

  setDashboardMessage("Password UI validated. Connect this to backend endpoint next.", "ok");
  changePasswordForm.reset();
});

logoutBtn.addEventListener("click", () => {
  localStorage.removeItem("documind_access_token");
  localStorage.removeItem("documind_user");
  window.location.href = "index.html";
});

renderHistory();
renderThread();
renderUploadedFiles();
