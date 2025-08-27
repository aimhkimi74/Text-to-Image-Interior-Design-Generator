from flask import Blueprint, jsonify, request, current_app
from flask_login import login_required, current_user
from datetime import datetime
from markupsafe import escape
from flask_cors import CORS
import logging

from . import db, csrf, limiter
from .models import (
    UserStyle, ChatMessage, ChatSession,
    FavoriteImage, ImageRating, StyleFeedback, PromptFeedback
)
from .services.bert_validation import validate_prompt_locally, format_bot_message

logger = logging.getLogger(__name__)
api = Blueprint("api", __name__)
CORS(api)


# ------------------------------
# Helpers
# ------------------------------
def sanitize_input(text):
    if not text or not isinstance(text, str):
        return ""
    return escape(text).strip()


def shorten_url(url: str, max_len: int = 60) -> str:
    """Shorten URLs in logs to avoid spam"""
    if not url:
        return ""
    if len(url) <= max_len:
        return url
    return url[: max_len // 2] + "..." + url[-max_len // 2 :]


# ------------------------------
# Health check
# ------------------------------
@api.route("/health", methods=["GET"])
def unified_health_check():
    """Basic system & backend health info"""
    try:
        backend_url = current_app.config.get("COLAB_ENDPOINT")
        backend_health = "not configured"
        backend_connected = False

        if backend_url:
            try:
                backend_connected = current_app.backend_service._test_connection()
                backend_health = "healthy" if backend_connected else "unhealthy"
            except Exception as e:
                backend_health = f"error ({e})"

        return jsonify(
            {
                "status": "healthy",
                "timestamp": datetime.utcnow().isoformat(),
                "backend": {
                    "configured": bool(backend_url),
                    "connected": backend_connected,
                    "health": backend_health,
                    "url": backend_url or "not set",
                },
            }
        )
    except Exception as e:
        logger.error(f"Unified health check error: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500


# ------------------------------
# Prompt validation
# ------------------------------
@api.route("/api/validate-prompt", methods=["POST"])
def validate_prompt():
    prompt = request.json.get("prompt", "")
    result = validate_prompt_locally(prompt)
    bot_message = format_bot_message(result)

    return jsonify(
        {
            "valid": result["valid"],
            "style": result["detected_style"],
            "confidence": result["style_confidence"],
            "bot_message": bot_message,
        }
    )


# ------------------------------
# Image generation
# ------------------------------
@api.route("/generate-image", methods=["POST"])
@login_required
def generate_image():
    try:
        data = request.get_json() or {}
        prompt = data.get("prompt", "").strip()
        style = data.get("style", "")
        session_id = data.get("session_id")

        if not prompt:
            return jsonify({"error": "No prompt provided"}), 400

        validation_result, validation_error = current_app.backend_service.validate_prompt(prompt)
        if validation_error:
            return jsonify({"error": f"Prompt validation failed: {validation_error}"}), 400

        # Ensure session exists
        if not session_id:
            new_session = ChatSession(user_id=current_user.id, name=f"Chat {datetime.utcnow()}")
            db.session.add(new_session)
            db.session.flush()
            session_id = new_session.uuid
            logger.info(f"Created new session: {session_id}")

        session_check = ChatSession.query.filter_by(uuid=session_id, user_id=current_user.id).first()
        if not session_check:
            return jsonify({"error": "Invalid or unauthorized session"}), 403

        # Handle invalid prompt
        if not validation_result or not validation_result.get("valid"):
            message = validation_result.get("message", "Prompt validation failed")
            db.session.add(ChatMessage(session_id=session_id, user_id=current_user.id, content=prompt, is_user=True))
            db.session.add(ChatMessage(session_id=session_id, user_id=current_user.id, content=message, is_user=False))
            db.session.commit()
            return jsonify({"error": message, "validation": validation_result}), 400

        final_style = style if style and style != "auto" else validation_result.get("detected_style", "modern")
        style_reasons = validation_result.get("style_reasons", [])

        # Save user prompt
        db.session.add(ChatMessage(session_id=session_id, user_id=current_user.id, content=prompt, is_user=True))

        # Call backend
        result, generation_error = current_app.backend_service.generate_image(prompt, final_style)
        if generation_error or not result.get("image_url"):
            return jsonify({"error": generation_error or "No image URL returned"}), 500

        image_url = result["image_url"]

        # Save assistant response
        explanation = "\n".join([f"🔹 {i+1}. {r.capitalize()}" for i, r in enumerate(style_reasons[:3])]) or "Timeless design elements"
        message = (
            f"🎨 Here is your generated design in **{final_style.capitalize()}** style!\n\n"
            f"🔍 **Why this style?**\n{explanation}\n\n"
            "🖼️ You can **rate** this image or **add it to favorites** below."
        )
        db.session.add(
            ChatMessage(
                session_id=session_id,
                user_id=current_user.id,
                content=message,
                is_user=False,
                image_url=image_url,
                detected_style=final_style,
                style_reasons="\n".join(style_reasons) if style_reasons else None,
            )
        )

        # Update stats
        current_user.designs_created += 1
        user_style = UserStyle.query.filter_by(user_id=current_user.id, style_name=final_style).first()
        if user_style:
            user_style.count += 1
        else:
            db.session.add(UserStyle(user_id=current_user.id, style_name=final_style))

        db.session.commit()

        return jsonify({"image": image_url, "message": message, "style": final_style})

    except Exception as e:
        db.session.rollback()
        logger.exception("generate_image error")
        return jsonify({"error": str(e)}), 500


# ------------------------------
# Detect style
# ------------------------------
@api.route("/detect-style", methods=["POST"])
def detect_style():
    data = request.get_json() or {}
    prompt = data.get("prompt", "").strip()
    if not prompt:
        return jsonify({"error": "Prompt is required"}), 400

    result = validate_prompt_locally(prompt)
    return jsonify({"style": result.get("detected_style")})


# ------------------------------
# Favorite styles summary
# ------------------------------
@api.route("/favorite-styles", methods=["GET"])
@login_required
def get_favorite_styles():
    styles = (
        UserStyle.query.filter_by(user_id=current_user.id).order_by(UserStyle.count.desc()).limit(3).all()
    )
    return jsonify({"styles": [{"style_name": s.style_name, "count": s.count} for s in styles]})


# ------------------------------
# Sharing tracker
# ------------------------------
@api.route("/share-design", methods=["POST"])
@login_required
def share_design():
    data = request.get_json() or {}
    if not data.get("image_url"):
        return jsonify({"error": "Image URL is required"}), 400
    current_user.designs_shared += 1
    db.session.commit()
    return jsonify({"success": True})


# ------------------------------
# Favorites (add/get/delete)
# ------------------------------
@api.route("/favorite", methods=["POST"])
@csrf.exempt
@login_required
def add_favorite():
    data = request.get_json() or {}
    image_url = sanitize_input(data.get("image_url"))
    prompt = sanitize_input(data.get("prompt"))
    style_name = sanitize_input(data.get("style_name"))

    if not image_url or not prompt:
        return jsonify({"success": False, "message": "Image URL and prompt are required"}), 400

    existing = FavoriteImage.query.filter_by(user_id=current_user.id, image_url=image_url).first()
    if existing:
        return jsonify({"success": True, "message": "Already in favorites"}), 200

    favorite = FavoriteImage(user_id=current_user.id, image_url=image_url, prompt=prompt, style_name=style_name)
    db.session.add(favorite)
    current_user.designs_shared += 1
    db.session.commit()
    return jsonify({"success": True, "favorite_id": favorite.id}), 201


@api.route("/favorites", methods=["GET"])
@login_required
def get_favorites():
    page = max(int(request.args.get("page", 1)), 1)
    size = max(min(int(request.args.get("page_size", 20)), 50), 1)
    q = FavoriteImage.query.filter_by(user_id=current_user.id).order_by(FavoriteImage.timestamp.desc())
    total = q.count()
    favorites = q.offset((page - 1) * size).limit(size).all()
    return jsonify(
        {
            "page": page,
            "total": total,
            "favorites": [
                {
                    "id": f.id,
                    "image_url": f.image_url,
                    "style_name": f.style_name,
                    "prompt": f.prompt,
                    "timestamp": f.timestamp.isoformat(),
                }
                for f in favorites
            ],
        }
    )


@api.route("/favorites/<int:favorite_id>", methods=["DELETE"])
@login_required
def remove_favorite(favorite_id):
    favorite = FavoriteImage.query.filter_by(id=favorite_id, user_id=current_user.id).first()
    if not favorite:
        return jsonify({"success": False, "message": "Favorite not found"}), 404
    db.session.delete(favorite)
    if current_user.designs_shared > 0:
        current_user.designs_shared -= 1
    db.session.commit()
    return jsonify({"success": True})


# ------------------------------
# Ratings
# ------------------------------
@api.route("/rate-image", methods=["POST"])
@login_required
def rate_image():
    data = request.get_json() or {}
    image_url = sanitize_input(data.get("image_url"))
    if not image_url:
        return jsonify({"success": False, "message": "Image URL required"}), 400

    pr, iq, sa = data.get("prompt_relevance"), data.get("image_quality"), data.get("style_accuracy")
    if not all([pr, iq, sa]):
        return jsonify({"success": False, "message": "All rating fields required"}), 400

    existing = ImageRating.query.filter_by(user_id=current_user.id, image_url=image_url).first()
    if existing:
        existing.prompt_relevance, existing.image_quality, existing.style_accuracy = pr, iq, sa
        db.session.commit()
        return jsonify({"success": True, "message": "Rating updated"}), 200

    chat_msg = ChatMessage.query.filter_by(image_url=image_url).order_by(ChatMessage.timestamp.desc()).first()
    style_tag = chat_msg.detected_style if chat_msg else None

    rating = ImageRating(
        user_id=current_user.id,
        image_url=image_url,
        prompt_relevance=pr,
        image_quality=iq,
        style_accuracy=sa,
        style_tag=style_tag,
    )
    db.session.add(rating)
    db.session.commit()
    return jsonify({"success": True, "message": "Rating submitted"}), 201


@api.route("/ratings", methods=["GET"])
@login_required
def get_ratings():
    ratings = ImageRating.query.filter_by(user_id=current_user.id).all()
    return jsonify(
        {
            "ratings": [
                {
                    "image_url": r.image_url,
                    "prompt_relevance": r.prompt_relevance,
                    "image_quality": r.image_quality,
                    "style_accuracy": r.style_accuracy,
                    "style_tag": r.style_tag,
                    "created_at": r.timestamp.isoformat() if r.timestamp else None,
                }
                for r in ratings
            ]
        }
    )


# ------------------------------
# Style explanation & feedback
# ------------------------------
@api.route("/style-explanation", methods=["POST"])
@login_required
def get_style_explanation():
    data = request.get_json() or {}
    style = sanitize_input(data.get("style"))
    if not style:
        return jsonify({"error": "Style is required"}), 400
    explanation, error = current_app.backend_service.get_style_explanation(style)
    if error:
        return jsonify({"error": error}), 500
    return jsonify({"explanation": explanation})


@api.route("/style-feedback", methods=["POST"])
@login_required
def submit_style_feedback():
    data = request.get_json() or {}
    orig = sanitize_input(data.get("original_style"))
    corr = sanitize_input(data.get("corrected_style"))
    if not orig or not corr:
        return jsonify({"error": "Both original and corrected style required"}), 400
    fb = StyleFeedback(user_id=current_user.id, image_url=data.get("image_url", ""), original_style=orig, corrected_style=corr)
    db.session.add(fb)
    db.session.commit()
    return jsonify({"success": True})


@api.route("/prompt-feedback", methods=["POST"])
@login_required
def prompt_feedback():
    data = request.get_json() or {}
    prompt, feedback = data.get("prompt", "").strip(), data.get("feedback", "").strip()
    category = data.get("category", "general")
    if not prompt or not feedback:
        return jsonify({"error": "Prompt and feedback required"}), 400

    fb = PromptFeedback(user_id=current_user.id, prompt=prompt, feedback=feedback, category=category, timestamp=datetime.utcnow())
    db.session.add(fb)
    db.session.commit()
    return jsonify({"success": True})
