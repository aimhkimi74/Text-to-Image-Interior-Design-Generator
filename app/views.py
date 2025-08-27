from flask import (
    Blueprint, current_app, request, jsonify,
    render_template, redirect, url_for, session
)
from flask_login import login_required, current_user
from datetime import datetime
from markupsafe import escape

from .models import ChatSession, ChatMessage
from . import db

views = Blueprint("views", __name__)


# ---------------------------
# Landing page
# ---------------------------
@views.route("/")
def landing():
    return redirect(url_for("auth.login"))


# ---------------------------
# Home / Chat page
# ---------------------------
@views.route("/home")
@login_required
def home():
    session_id = request.args.get("session_id")
    scroll_to_id = request.args.get("scroll_to")

    # Step 1: Pick current session
    if session_id:
        chat_session = ChatSession.query.filter_by(uuid=session_id, user_id=current_user.id).first()
        if chat_session:
            session["current_session_id"] = session_id
    elif "current_session_id" not in session:
        most_recent = (
            ChatSession.query.filter_by(user_id=current_user.id)
            .order_by(ChatSession.created_at.desc())
            .first()
        )
        if most_recent:
            session["current_session_id"] = most_recent.uuid

    current_session_id = session.get("current_session_id")
    chat_session = (
        ChatSession.query.filter_by(uuid=current_session_id, user_id=current_user.id).first()
        if current_session_id else None
    )

    # Step 2: Fetch messages
    messages, first_time = [], False
    if chat_session:
        messages = (
            ChatMessage.query.filter_by(session_id=chat_session.uuid)
            .order_by(ChatMessage.timestamp.asc())
            .all()
        )
        first_time = not any(m.is_user for m in messages)  # no user msg yet

    return render_template(
        "index.html",
        messages=messages,
        first_time=first_time,
        scroll_to_id=scroll_to_id,
    )


# ---------------------------
# Help page
# ---------------------------
@views.route("/help")
@login_required
def help():
    return render_template("help.html")


# ---------------------------
# Style list
# ---------------------------
@views.route("/styles")
@login_required
def get_styles():
    return jsonify(
        [
            "Modern", "Contemporary", "Traditional", "Minimalist",
            "Industrial", "Scandinavian", "Bohemian", "Mid-century Modern",
        ]
    )


# ---------------------------
# Connect model (Colab/Backend)
# ---------------------------
@views.route("/connect-model", methods=["POST"])
@login_required
def connect_model():
    data = request.get_json() or {}
    endpoint = str(data.get("endpoint", "")).strip()

    if not endpoint:
        return jsonify({"error": "Colab endpoint URL is required"}), 400

    try:
        # Sanitize + standardize
        endpoint = escape(endpoint)
        if not endpoint.startswith("http"):
            endpoint = f"https://{endpoint}"
        endpoint = endpoint.rstrip("/")

        current_app.config["COLAB_ENDPOINT"] = endpoint

        from .services.backend_service import BackendService

        backend_service = BackendService()
        backend_service.base_url = endpoint

        if backend_service._test_connection():
            return jsonify({"success": True, "message": "Model connected successfully"})
        return jsonify({"error": "Failed to connect to backend"}), 500

    except Exception as e:
        return jsonify({"error": f"Connection failed: {str(e)}"}), 500
