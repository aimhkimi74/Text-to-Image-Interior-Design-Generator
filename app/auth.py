# app/auth.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app, abort, session
from flask_login import login_user, logout_user, login_required, current_user
from .models import User, db, FavoriteImage, ChatMessage, ImageRating, ChatSession
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from sqlalchemy import or_
from functools import wraps
from flask_mail import Mail, Message
from flask_wtf.csrf import CSRFError, validate_csrf, generate_csrf
from sqlalchemy.orm import joinedload
from collections import Counter
import logging, re, os, random
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)
auth = Blueprint("auth", __name__)
mail = Mail()

# ---------------- Helpers ----------------
def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated

def get_serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"])

def validate_email(email): return re.match(r"^[\w\.-]+@[\w\.-]+\.\w+$", email)
def validate_username(username): return re.match(r"^[a-zA-Z0-9_]{3,20}$", username)

def strong_password(pw:str)->bool:
    if len(pw) < 12: return False
    classes = sum([
        bool(re.search(r"[a-z]", pw)),
        bool(re.search(r"[A-Z]", pw)),
        bool(re.search(r"\d", pw)),
        bool(re.search(r"[^\w\s]", pw))
    ])
    return classes >= 3

# ---------------- CSRF token ----------------
@auth.route("/csrf-token")
def get_csrf_token():
    session.permanent = True
    return jsonify({"csrf_token": generate_csrf()})

# ---------------- Signup & Verification ----------------
@auth.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "GET":
        return render_template("signup.html")

    data = request.get_json() or {}
    email, username, password = data.get("email","").strip(), data.get("username","").strip(), data.get("password","")

    if not all([email, username, password]): return jsonify({"success":False,"message":"All fields required"}),400
    if not validate_email(email): return jsonify({"success":False,"message":"Invalid email"}),400
    if not validate_username(username): return jsonify({"success":False,"message":"Invalid username"}),400
    if not strong_password(password): return jsonify({"success":False,"message":"Weak password"}),400
    if User.query.filter(or_(User.email==email, User.username==username)).first():
        return jsonify({"success":False,"message":"Email or username already in use"}),400

    try:
        code = "".join(random.choices("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ", k=6))
        new_user = User(email=email, username=username,
                        password=generate_password_hash(password),
                        is_verified=False, verification_code=code,
                        verification_expires_at=datetime.utcnow()+timedelta(minutes=10))
        db.session.add(new_user); db.session.commit()
        mail.send(Message("Verification Code", recipients=[email],
                          body=f"Hi {username}, your code is: {code} (expires in 10 min)"))
        return jsonify({"success":True,"message":"Check your email for the verification code."}),200
    except Exception as e:
        db.session.rollback(); logger.error(f"Signup error: {e}")
        return jsonify({"success":False,"message":"Internal error"}),500

@auth.route("/verify-code", methods=["POST"])
def verify_code():
    data=request.get_json() or {}
    email, code = data.get("email","").strip(), data.get("code","").strip()
    user = User.query.filter_by(email=email).first()
    if not user: return jsonify({"success":False,"message":"User not found"}),404
    if user.is_verified: return jsonify({"success":False,"message":"Already verified"}),400
    if user.verification_code!=code or user.verification_expires_at<datetime.utcnow():
        return jsonify({"success":False,"message":"Invalid/expired code"}),400
    user.is_verified=True; user.verification_code=None; user.verification_expires_at=None
    db.session.commit()
    return jsonify({"success":True,"message":"Account verified"}),200

@auth.route("/resend-code", methods=["POST"])
def resend_code():
    validate_csrf(request.headers.get("X-CSRFToken"))
    data=request.get_json() or {}; email=data.get("email","").strip()
    user=User.query.filter_by(email=email).first()
    if not user: return jsonify({"success":False,"message":"User not found"}),404
    if user.is_verified: return jsonify({"success":False,"message":"Already verified"}),400
    code="".join(random.choices("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ",k=6))
    user.verification_code=code; user.verification_expires_at=datetime.utcnow()+timedelta(minutes=10)
    db.session.commit()
    mail.send(Message("New Verification Code",recipients=[email],body=f"Hi {user.username}, code: {code}"))
    return jsonify({"success":True,"message":"New code sent"}),200

# ---------------- Login / Logout ----------------
@auth.route("/login", methods=["GET","POST"])
def login():
    if request.method=="GET": return render_template("login.html")
    data=request.get_json() or {}
    email,password=data.get("email","").strip(),data.get("password","")
    user=User.query.filter_by(email=email).first()
    if not user or not check_password_hash(user.password,password):
        return jsonify({"success":False,"message":"Invalid credentials"}),401
    if user.is_blocked: return jsonify({"success":False,"message":"Blocked account"}),403
    if not user.is_verified and os.getenv("TEST_MODE","false").lower()!="true":
        return jsonify({"success":False,"message":"Not verified"}),403
    login_user(user,remember=True)
    logger.info(f"User logged in: {user.id}")
    return jsonify({"success":True,"redirect":url_for("views.home")}),200

@auth.route("/logout")
@login_required
def logout():
    uid=current_user.id; logout_user()
    logger.info(f"User logged out: {uid}")
    return jsonify({"success":True}),200

# ---------------- Admin-only Delete ----------------
@auth.route("/api/admin/user/<int:user_id>", methods=["DELETE"])
@login_required @admin_required
def delete_user(user_id):
    u=User.query.get(user_id)
    if not u: return jsonify({"message":"Not found"}),404
    db.session.delete(u); db.session.commit()
    return jsonify({"message":"Deleted"}),200

# ---------------- Profile ----------------
@auth.route("/profile")
@login_required
def profile():
    favorites=FavoriteImage.query.filter_by(user_id=current_user.id).all()
    recent_msgs=(ChatMessage.query.join(ChatSession)
                 .options(joinedload(ChatMessage.session_obj))
                 .filter(ChatSession.user_id==current_user.id, ChatMessage.image_url!=None)
                 .order_by(ChatMessage.timestamp.desc()).limit(9).all())
    detected=[m.detected_style for m in recent_msgs if m.detected_style]
    most_detected=Counter(detected).most_common(1)[0][0] if detected else ""
    rating_summary=db.session.query(db.func.avg(ImageRating.prompt_relevance),
                                    db.func.avg(ImageRating.image_quality),
                                    db.func.avg(ImageRating.style_accuracy))\
                             .filter(ImageRating.user_id==current_user.id).first()
    ratings={"prompt_relevance":round(rating_summary[0] or 0,2),
             "image_quality":round(rating_summary[1] or 0,2),
             "style_accuracy":round(rating_summary[2] or 0,2)}
    return render_template("profile.html",user=current_user,
                           favorites=favorites,recent_messages=recent_msgs,
                           ratings_overview=ratings,most_detected_style=most_detected)

# ---------------- Profile Update ----------------
@auth.route("/update_profile", methods=["POST"])
@login_required
def update_profile():
    validate_csrf(request.headers.get("X-CSRFToken"))
    data=request.get_json() or {}
    username,email=data.get("username",""),data.get("email","")
    curr_pw,new_pw=data.get("current_password"),data.get("new_password")
    if not check_password_hash(current_user.password,curr_pw):
        return jsonify({"success":False,"message":"Current password wrong"}),400
    if username!=current_user.username and User.query.filter_by(username=username).first():
        return jsonify({"success":False,"message":"Username exists"}),400
    if email!=current_user.email and User.query.filter_by(email=email).first():
        return jsonify({"success":False,"message":"Email exists"}),400
    current_user.username=username; current_user.email=email
    if new_pw:
        if not strong_password(new_pw): return jsonify({"success":False,"message":"Weak password"}),400
        current_user.password=generate_password_hash(new_pw)
    db.session.commit(); logger.info(f"User updated profile: {current_user.id}")
    return jsonify({"success":True,"message":"Profile updated"}),200

# ---------------- Forgot / Reset Password ----------------
@auth.route("/forgot-password", methods=["POST"])
def forgot_password():
    validate_csrf(request.headers.get("X-CSRFToken"))
    data=request.get_json() or {}; email=data.get("email","").strip()
    user=User.query.filter_by(email=email).first()
    if not user: return jsonify({"success":False,"message":"Email not found"}),404
    code="".join(random.choices("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ",k=6))
    user.reset_code=code; user.reset_expires_at=datetime.utcnow()+timedelta(minutes=10)
    db.session.commit()
    mail.send(Message("Password Reset Code",recipients=[email],body=f"Code: {code}"))
    return jsonify({"success":True}),200

@auth.route("/reset-password-code", methods=["POST"])
def reset_password_code():
    validate_csrf(request.headers.get("X-CSRFToken"))
    data=request.get_json() or {}; email,code,new_pw=data.get("email"),data.get("code"),data.get("new_password")
    user=User.query.filter_by(email=email).first()
    if not user or user.reset_code!=code or user.reset_expires_at<datetime.utcnow():
        return jsonify({"success":False,"message":"Invalid reset"}),400
    if not strong_password(new_pw): return jsonify({"success":False,"message":"Weak password"}),400
    user.password=generate_password_hash(new_pw); user.reset_code=None; user.reset_expires_at=None
    db.session.commit()
    return jsonify({"success":True}),200

@auth.route("/reset-password/<token>", methods=["POST"])
def reset_password(token):
    validate_csrf(request.headers.get("X-CSRFToken"))
    serializer=get_serializer()
    try: email=serializer.loads(token,salt="password-reset-salt",max_age=3600)
    except (SignatureExpired,BadSignature): return jsonify({"success":False,"message":"Invalid/expired token"}),400
    data=request.get_json() or {}; pw=data.get("password","")
    if not strong_password(pw): return jsonify({"success":False,"message":"Weak password"}),400
    user=User.query.filter_by(email=email).first()
    if not user: return jsonify({"success":False,"message":"User not found"}),404
    user.password=generate_password_hash(pw); db.session.commit()
    return jsonify({"success":True,"message":"Password reset ok"}),200

# ---------------- CSRF error ----------------
@auth.errorhandler(CSRFError)
def handle_csrf_error(e): return jsonify({"message":"CSRF token missing or invalid"}),400
