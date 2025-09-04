# 🛠️ Living Room Style Analyzer (Flask Backend)

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python Version">
  <img src="https://img.shields.io/badge/flask-2.3%2B-green.svg" alt="Flask Version">
  <img src="https://img.shields.io/badge/license-MIT-yellow.svg" alt="License">
  <img src="https://img.shields.io/badge/build-passing-brightgreen.svg" alt="Build Status">
</p>

A Flask-based backend system for generating and analyzing living room design styles.  
Features include user authentication, AI-powered image generation, favorites management, ratings, style feedback, and robust security.

---

## 📦 Features

- **🔐 User Authentication:** Signup, login, email verification, password reset
- **👤 Admin Management:** Create or update admin users via CLI
- **💬 Chat Sessions:** Store, rename, and delete user chat history
- **🎨 Image Generation:** AI-powered designs with detected styles
- **⭐ Favorites & Ratings:** Save, rate, and manage generated images
- **📊 Style Feedback:** Collect user ratings and corrections for styles
- **🔒 Security:** CSRF protection, rate-limiting, password hashing

---

## ⚙️ Installation

1. **Clone the repository:**
   ```sh
   git clone https://github.com/aimhkimi74/Text-to-Image-Interior-Design-Generator.git
   cd living-room-analyzer
   ```

2. **Set up a virtual environment:**
   ```sh
   python -m venv venv
   # Linux / macOS
   source venv/bin/activate
   # Windows
   venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```sh
   pip install -r requirements.txt
   ```

---

## 🔑 Configuration

1. **Copy `.env.example` to `.env`:**
   ```sh
   cp .env.example .env
   ```

2. **Fill in your secrets:**
   - `SECRET_KEY` → Generate with:
     ```sh
     python -c "import secrets; print(secrets.token_hex(32))"
     ```
   - `MAIL_*` → SMTP settings (e.g., Gmail, SendGrid)
   - `COLAB_ENDPOINT` → Your AI backend URL

---

## ▶️ Running the App

- **Run the Flask server:**
  ```sh
  flask run
  ```
- **Or with main.py:**
  ```sh
  python main.py
  ```
- Server starts at [http://127.0.0.1:5000/](http://127.0.0.1:5000/)

---

## 👨‍💻 Admin User Setup

- **Create an admin:**
  ```sh
  python create_admin.py --username admin --email admin@example.com
  ```
- **Update existing user to admin:**
  ```sh
  python create_admin.py --username admin --update
  ```

---

## 📂 Project Structure

```
app/
  __init__.py        # Flask app factory
  models.py          # Database models
  auth.py            # User authentication
  chat.py            # Chat sessions
  routes.py          # API endpoints
  views.py           # Frontend routes
  admin.py           # Admin management
  services/          # AI / backend services
create_admin.py      # CLI tool to create admin users
main.py              # App entry point
requirements.txt     # Dependencies
README.md            # Project documentation
.env.example         # Environment config template
```

---

## 🧪 Testing

Test manually or via Postman:

- ✅ Signup → Verify email → Login
- ✅ Generate image → Add to favorites → Rate → Delete
- ✅ Admin login → Manage users
- ✅ Check 404 & 500 error pages

---

## 🔒 Security Notes

- Do **not** commit `.env` or `database.db` (already in `.gitignore`)
- Always use a strong `SECRET_KEY` in production
- Set CORS origins to trusted domains only
- Increase password minimum length to 12+ characters

---

## 📜 License

MIT License © 2025 aimhkimi74
