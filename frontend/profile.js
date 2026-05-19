const API_BASE_URL = "http://127.0.0.1:8000";
const token = localStorage.getItem("documind_access_token");
const storageUser = localStorage.getItem("documind_user");
const logoutBtn = document.getElementById("logout-btn");
const changePasswordForm = document.getElementById("change-password-form");
const message = document.getElementById("profile-message");

if (!token) {
  window.location.href = "index.html";
}

try {
  const cachedUser = JSON.parse(storageUser || "{}");
  if (cachedUser.full_name) {
    document.getElementById("profile-name").textContent = cachedUser.full_name;
  }
  if (cachedUser.email) {
    document.getElementById("profile-email").textContent = cachedUser.email;
  }
} catch (error) {
  // Ignore invalid cache and let API response populate values.
}

function setMessage(text, isError = false) {
  message.textContent = text;
  message.classList.toggle("error", isError);
}

async function loadProfile() {
  try {
    const response = await fetch(`${API_BASE_URL}/api/auth/me`, {
      method: "GET",
      headers: { Authorization: `Bearer ${token}` }
    });

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      if (response.status === 401) {
        localStorage.removeItem("documind_access_token");
        localStorage.removeItem("documind_user");
        window.location.href = "index.html";
        return;
      }
      setMessage(data.detail || "Unable to load profile.", true);
      return;
    }

    document.getElementById("profile-name").textContent = data.full_name || "-";
    document.getElementById("profile-email").textContent = data.email || "-";

    localStorage.setItem(
      "documind_user",
      JSON.stringify({ id: data.id, full_name: data.full_name, email: data.email })
    );
  } catch (error) {
    setMessage("Cannot reach backend API.", true);
  }
}

logoutBtn.addEventListener("click", () => {
  localStorage.removeItem("documind_access_token");
  localStorage.removeItem("documind_user");
  window.location.href = "index.html";
});

changePasswordForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  const currentPassword = document.getElementById("current-password").value;
  const newPassword = document.getElementById("new-password").value;
  const confirmPassword = document.getElementById("confirm-password").value;

  if (!currentPassword || !newPassword || !confirmPassword) {
    setMessage("Please fill all password fields.", true);
    return;
  }
  if (newPassword.length < 8) {
    setMessage("New password must be at least 8 characters.", true);
    return;
  }
  if (newPassword !== confirmPassword) {
    setMessage("New password and confirmation do not match.", true);
    return;
  }
  if (newPassword === currentPassword) {
    setMessage("New password must be different from current password.", true);
    return;
  }

  try {
    const response = await fetch(`${API_BASE_URL}/api/auth/change-password`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`
      },
      body: JSON.stringify({
        current_password: currentPassword,
        new_password: newPassword
      })
    });

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      if (response.status === 401) {
        localStorage.removeItem("documind_access_token");
        localStorage.removeItem("documind_user");
        window.location.href = "index.html";
        return;
      }
      setMessage(data.detail || "Password update failed.", true);
      return;
    }

    setMessage(data.message || "Password updated successfully.");
    changePasswordForm.reset();
  } catch (error) {
    setMessage("Cannot reach backend API.", true);
  }
});

loadProfile();
