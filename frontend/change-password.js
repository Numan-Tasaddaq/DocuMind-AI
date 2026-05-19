const API_BASE_URL = "http://127.0.0.1:8000";
const token = localStorage.getItem("documind_access_token");
const form = document.getElementById("change-password-form");
const message = document.getElementById("change-message");
const logoutBtn = document.getElementById("logout-btn");

if (!token) {
  window.location.href = "index.html";
}

function setMessage(text, isError = false) {
  message.textContent = text;
  message.classList.toggle("error", isError);
}

logoutBtn.addEventListener("click", () => {
  localStorage.removeItem("documind_access_token");
  localStorage.removeItem("documind_user");
  window.location.href = "index.html";
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  const currentPassword = document.getElementById("current-password").value;
  const newPassword = document.getElementById("new-password").value;
  const confirmPassword = document.getElementById("confirm-password").value;

  if (!currentPassword || !newPassword || !confirmPassword) {
    setMessage("Please fill all fields.", true);
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
    form.reset();
  } catch (error) {
    setMessage("Cannot reach backend API.", true);
  }
});
