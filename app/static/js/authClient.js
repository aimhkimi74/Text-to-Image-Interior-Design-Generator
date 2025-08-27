// authClient.js — FINAL SAFE VERSION
function getCSRFToken() {
  const name = "csrftoken";
  const cookies = document.cookie.split(";").map(c => c.trim());
  for (let c of cookies) {
    if (c.startsWith(name + "=")) return c.substring(name.length + 1);
  }
  return "";
}

class AuthClient {
  static async login(email, password) {
    const response = await fetch("/auth/login", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCSRFToken(),
      },
      body: JSON.stringify({ email, password }),
    });

    const data = await response.json();
    if (!response.ok) {
      const errorMsg = data?.message || data?.error || "Login failed";
      throw new Error(errorMsg);
    }
    return data;
  }

  static async signup(username, email, password) {
    const response = await fetch("/auth/signup", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCSRFToken(),
      },
      body: JSON.stringify({ username, email, password }),
    });

    const data = await response.json();
    if (!response.ok) {
      const errorMsg = data?.message || data?.error || "Signup failed";
      throw new Error(errorMsg);
    }
    return data;
  }
}
