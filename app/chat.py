# app/chat.py
from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from .models import ChatMessage, ChatSession, FavoriteImage, ImageRating
from . import db, limiter
from flask_wtf.csrf import validate_csrf
import uuid, logging, time
from datetime import datetime

logger = logging.getLogger(__name__)
chat = Blueprint("chat", __name__)

# --- In-memory invalid prompt cache (fallback; better: Redis) ---
recent_invalid_prompts = {}
CACHE_TTL = 300  # 5 min

def is_recently_invalid(user_id, prompt):
    ts = recent_invalid_prompts.get(user_id, {}).get(prompt)
    return bool(ts and (time.time() - ts) < CACHE_TTL)

def mark_invalid(user_id, prompt):
    recent_invalid_prompts.setdefault(user_id, {})[prompt] = time.time()

# --- Routes ---
@chat.route("/new", methods=["POST"])
@login_required
def create_chat():
    try:
        validate_csrf(request.headers.get("X-CSRFToken"))
        session_id = str(uuid.uuid4())
        name = request.json.get("name", f"Chat {datetime.utcnow():%Y-%m-%d %H:%M:%S}")
        chat_sess = ChatSession(uuid=session_id, user_id=current_user.id, name=name, created_at=datetime.utcnow())
        db.session.add(chat_sess); db.session.commit()
        logger.info(f"New chat created uid={current_user.id} sid={session_id}")
        return jsonify({"session_id": session_id, "name": name}), 201
    except Exception as e:
        db.session.rollback(); logger.error(f"create_chat failed: {e}", exc_info=True)
        return jsonify({"error":"Failed to create chat"}),500

@chat.route("/rename", methods=["POST"])
@login_required
def rename_chat():
    try:
        validate_csrf(request.headers.get("X-CSRFToken"))
        data=request.get_json() or {}
        sid,new_name=data.get("session_id"),data.get("name")
        if not sid or not new_name: return jsonify({"error":"Missing session_id or name"}),400
        session=ChatSession.query.filter_by(uuid=sid,user_id=current_user.id).first()
        if not session: return jsonify({"error":"Not found"}),404
        session.name=new_name; db.session.commit()
        return jsonify({"success":True,"session_id":sid,"name":new_name}),200
    except Exception as e:
        db.session.rollback(); logger.error(f"rename_chat failed: {e}",exc_info=True)
        return jsonify({"error":"Failed to rename"}),500

@chat.route('/delete', methods=['POST'])
@login_required
def delete_chat():
    try:
        data = request.get_json()
        session_id = data.get('session_uuid') or data.get('session_id')

        if not session_id:
            return jsonify({'error': 'Session ID is required'}), 400

        session = ChatSession.query.filter_by(uuid=session_id, user_id=current_user.id).first()
        if not session:
            logger.warning(f"Session {session_id} not found or unauthorized for user {current_user.id}")
            return jsonify({'error': 'Session not found or access denied'}), 404

        # Now cascade handles everything: messages, favorites, ratings
        db.session.delete(session)
        db.session.commit()

        return jsonify({'success': True, 'message': 'Chat session and related data deleted successfully'}), 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Failed to delete chat session: {str(e)}")
        return jsonify({'error': str(e)}), 500

@chat.route("/save", methods=["POST"])
@login_required
def save_msg():
    try:
        validate_csrf(request.headers.get("X-CSRFToken"))
        data=request.get_json() or {}
        msg, sid = data.get("message","").strip(), data.get("session_uuid")
        if not msg or not sid: return jsonify({"error":"Missing message/session"}),400
        if not ChatSession.query.filter_by(uuid=sid,user_id=current_user.id).first():
            return jsonify({"error":"Session not found"}),404
        db.session.add(ChatMessage(session_id=sid,user_id=current_user.id,content=msg,is_user=True))
        db.session.commit()
        return jsonify({"success":True}),200
    except Exception as e:
        db.session.rollback(); logger.error(f"save_msg failed: {e}",exc_info=True)
        return jsonify({"error":"Save failed"}),500

# GET routes (read-only, no CSRF needed)
@chat.route("/session/<sid>")
@login_required
def get_session(sid):
    session=ChatSession.query.filter_by(uuid=sid,user_id=current_user.id).first()
    if not session: return jsonify({"error":"Not found"}),404
    messages=ChatMessage.query.filter_by(session_id=sid).order_by(ChatMessage.timestamp.asc()).all()
    return jsonify({"session_id":sid,"name":session.name,
                    "messages":[{"id":m.id,"content":m.content,"image_url":m.image_url,"is_user":m.is_user,
                                 "timestamp":m.timestamp.isoformat()} for m in messages]})

@chat.route("/history")
@login_required
def history():
    sessions=ChatSession.query.filter_by(user_id=current_user.id).order_by(ChatSession.created_at.desc()).all()
    data=[{"session_id":s.uuid,"title":s.name,"created_at":s.created_at.isoformat()} for s in sessions]
    return jsonify({"sessions":data})

@chat.route("/sessions")
@login_required
def list_sessions():
    page=int(request.args.get("page",1)); size=int(request.args.get("page_size",20))
    sessions=ChatSession.query.filter_by(user_id=current_user.id).order_by(ChatSession.created_at.desc())\
                              .limit(size).offset((page-1)*size).all()
    return jsonify([{"session_id":s.uuid,"name":s.name,"created_at":s.created_at.isoformat()} for s in sessions])

@chat.route("/current-session")
@login_required
def current_session():
    sid=request.args.get("session_uuid")
    if not sid:
        latest=ChatSession.query.filter_by(user_id=current_user.id).order_by(ChatSession.created_at.desc()).first()
        sid=latest.uuid if latest else None
    return jsonify({"session_uuid":sid})
