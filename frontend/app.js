const tabs = document.querySelectorAll(".tab");
const forms = document.querySelectorAll(".auth-form");
const message = document.getElementById("auth-message");
const captchaState = new Map();
const refreshButtons = document.querySelectorAll("[data-refresh-captcha]");
const API_BASE_URL = "http://127.0.0.1:8000";
const DASHBOARD_URL = new URL("dashboard.html", window.location.href).href;

function redirectToDashboard() {
  try {
    window.location.assign(DASHBOARD_URL);
  } catch (error) {
    window.location.href = DASHBOARD_URL;
  }
}

if (localStorage.getItem("documind_access_token")) {
  redirectToDashboard();
}

function setMessage(text, type = "") {
  message.textContent = text;
  message.classList.remove("error", "success");
  if (type) {
    message.classList.add(type);
  }
}

function generateCaptcha(formId) {
  const first = Math.floor(Math.random() * 9) + 1;
  const second = Math.floor(Math.random() * 9) + 1;
  const answer = first + second;

  captchaState.set(formId, answer);

  const questionEl = document.getElementById(`${formId.replace("-form", "")}-captcha-question`);
  const answerEl = document.getElementById(`${formId.replace("-form", "")}-captcha-answer`);

  if (questionEl) {
    questionEl.textContent = `${first} + ${second} = ?`;
  }

  if (answerEl) {
    answerEl.value = "";
  }
}

tabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    const targetId = tab.dataset.target;

    tabs.forEach((btn) => {
      btn.classList.remove("active");
      btn.setAttribute("aria-selected", "false");
    });

    forms.forEach((form) => form.classList.remove("active"));

    tab.classList.add("active");
    tab.setAttribute("aria-selected", "true");
    document.getElementById(targetId).classList.add("active");
    setMessage("");
  });
});

refreshButtons.forEach((button) => {
  button.addEventListener("click", () => {
    const targetFormId = button.dataset.refreshCaptcha;
    generateCaptcha(targetFormId);
    setMessage("CAPTCHA refreshed. Please solve the new challenge.");
  });
});

forms.forEach((form) => {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();

    if (!form.checkValidity()) {
      form.reportValidity();
      return;
    }

    const expected = captchaState.get(form.id);
    const captchaInput = document.getElementById(`${form.id.replace("-form", "")}-captcha-answer`);
    const provided = Number(captchaInput.value.trim());

    if (!Number.isFinite(provided) || provided !== expected) {
      setMessage("CAPTCHA incorrect. Please try again.", "error");
      generateCaptcha(form.id);
      return;
    }

    const submitButton = form.querySelector(".primary-btn");
    const originalButtonContent = submitButton.innerHTML;
    submitButton.disabled = true;
    submitButton.innerHTML = "Please wait...";

    const isLogin = form.id === "login-form";
    const endpoint = isLogin ? "/api/auth/login" : "/api/auth/signup";
    const payload = isLogin
      ? {
          email: document.getElementById("login-email").value.trim(),
          password: document.getElementById("login-password").value
        }
      : {
          full_name: document.getElementById("signup-name").value.trim(),
          email: document.getElementById("signup-email").value.trim(),
          password: document.getElementById("signup-password").value
        };

    try {
      const response = await fetch(`${API_BASE_URL}${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });

      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        const errMsg = data.detail || "Request failed. Please try again.";
        setMessage(errMsg, "error");
        generateCaptcha(form.id);
        return;
      }

      if (data.access_token) {
        localStorage.setItem("documind_access_token", data.access_token);
      }
      if (data.user) {
        localStorage.setItem("documind_user", JSON.stringify(data.user));
      }

      const successMsg = isLogin
        ? `Welcome back, ${data.user.full_name}. Login successful.`
        : `Account created for ${data.user.full_name}. You are now signed in.`;
      setMessage(`${successMsg} Redirecting to workspace...`, "success");
      form.reset();
      generateCaptcha(form.id);
      redirectToDashboard();
    } catch (error) {
      setMessage("Cannot reach backend API. Make sure FastAPI server is running.", "error");
      generateCaptcha(form.id);
    } finally {
      submitButton.disabled = false;
      submitButton.innerHTML = originalButtonContent;
    }
  });
});

forms.forEach((form) => generateCaptcha(form.id));
