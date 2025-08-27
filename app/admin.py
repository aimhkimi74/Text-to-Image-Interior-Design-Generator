# app/admin.py
from flask import (
    Blueprint, request, jsonify, render_template,
    abort, make_response, flash, redirect, url_for
)
from flask_login import login_required, current_user
from .models import db, User, SUSFeedback, ChatMessage, ImageRating, FavoriteImage, StyleFeedback
from sqlalchemy import func, or_
from flask_wtf.csrf import CSRFError, validate_csrf
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash
from .auth import admin_required
from collections import defaultdict
import logging, csv, io, random

logger = logging.getLogger(__name__)
admin = Blueprint('admin', __name__)

# ===========================================
# 💡 Helper Function for SUS Score Calculation
# ===========================================
def calculate_sus_score(answers: dict) -> float:
    if not isinstance(answers, dict):
        raise ValueError("Answers must be a dictionary.")
    points = []
    points.append(answers['q1_frequency'] - 1)
    points.append(5 - answers['q2_complexity'])
    points.append(answers['q3_ease_of_use'] - 1)
    points.append(5 - answers['q4_tech_support'])
    points.append(answers['q5_integration'] - 1)
    points.append(5 - answers['q6_inconsistency'])
    points.append(answers['q7_learnability'] - 1)
    points.append(5 - answers['q8_awkwardness'])
    points.append(answers['q9_confidence'] - 1)
    points.append(5 - answers['q10_learning_curve'])
    return sum(points) * 2.5

# ===========================================
# 📊 USER FEEDBACK ROUTES
# ===========================================
@admin.route('/feedback', methods=['GET'])
@login_required
def feedback_form():
    recent_feedback = SUSFeedback.query.filter(
        SUSFeedback.user_id == current_user.id,
        SUSFeedback.timestamp >= datetime.utcnow() - timedelta(days=7)
    ).order_by(SUSFeedback.timestamp.desc()).first()
    initial_sus_score = recent_feedback.sus_score if recent_feedback else None
    return render_template('feedback_form.html',
                           recent_feedback=recent_feedback,
                           initial_sus_score=initial_sus_score)

@admin.route('/api/feedback', methods=['POST'])
@login_required
def submit_feedback():
    try:
        csrf_token = request.headers.get('X-CSRFToken')
        validate_csrf(csrf_token)

        data = request.get_json() or {}
        required_questions = [
            'q1_frequency','q2_complexity','q3_ease_of_use','q4_tech_support',
            'q5_integration','q6_inconsistency','q7_learnability',
            'q8_awkwardness','q9_confidence','q10_learning_curve'
        ]
        answers = {}
        for q in required_questions:
            value = data.get(q)
            if value is None:
                return jsonify({'success': False, 'message': f'Missing answer for {q}'}), 400
            try:
                answers[q] = int(value)
                if not (1 <= answers[q] <= 5):
                    return jsonify({'success': False, 'message': f'Invalid value for {q}'}), 400
            except ValueError:
                return jsonify({'success': False, 'message': f'Invalid type for {q}'}), 400

        sus_score = calculate_sus_score(answers)
        comments = (data.get('comments') or '').strip()
        user_type = (data.get('user_type') or '').strip()

        # Enforce 1 submission per day
        recent_feedback = SUSFeedback.query.filter(
            SUSFeedback.user_id == current_user.id,
            func.date(SUSFeedback.timestamp) == datetime.utcnow().date()
        ).first()
        if recent_feedback:
            return jsonify({'success': False, 'message': 'Only 1 feedback per day'}), 429

        feedback_entry = SUSFeedback(user_id=current_user.id,
                                     comments=comments,
                                     user_type=user_type,
                                     sus_score=sus_score,
                                     timestamp=datetime.utcnow(),
                                     **answers)
        db.session.add(feedback_entry)
        db.session.commit()
        logger.info(f"SUS feedback submitted for user {current_user.id}")
        return jsonify({'success': True, 'sus_score': f'{sus_score:.2f}'}), 201

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error submitting feedback: {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'Internal server error'}), 500

@admin.route('/api/feedback/latest', methods=['GET'])
@login_required
def get_latest_feedback():
    try:
        recent = SUSFeedback.query.filter_by(user_id=current_user.id)\
                                  .order_by(SUSFeedback.timestamp.desc()).first()
        if not recent:
            return jsonify({'success': False, 'message': 'No feedback yet'}), 404
        return jsonify({
            'success': True,
            'sus_score': f'{recent.sus_score:.2f}',
            'timestamp': recent.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')
        })
    except Exception as e:
        logger.error(f"Error fetching feedback: {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'Internal server error'}), 500

@admin.route('/feedback/history')
@login_required
def feedback_history():
    history = SUSFeedback.query.filter_by(user_id=current_user.id)\
                               .order_by(SUSFeedback.timestamp.desc()).all()
    return render_template('feedback_history.html', feedback_list=history)

# ===========================================
# 👑 ADMIN ROUTES
# ===========================================
@admin.route('/feedback/all', methods=['GET'])
@admin_required
def view_all_feedback():
    # fixed: no double /admin/admin
    try:
        filters = {k: request.args.get(k, '').strip() for k in
                   ['user_type','date_from','date_to','score_min','score_max']}
        query = SUSFeedback.query
        if filters['user_type']:
            query = query.filter(SUSFeedback.user_type == filters['user_type'])
        if filters['date_from']:
            query = query.filter(SUSFeedback.timestamp >= filters['date_from'])
        if filters['date_to']:
            query = query.filter(SUSFeedback.timestamp <= filters['date_to'])
        if filters['score_min']:
            query = query.filter(SUSFeedback.sus_score >= float(filters['score_min']))
        if filters['score_max']:
            query = query.filter(SUSFeedback.sus_score <= float(filters['score_max']))

        page = request.args.get('page', 1, type=int)
        pagination = query.order_by(SUSFeedback.timestamp.desc()).paginate(page=page, per_page=10)
        all_user_types = [ut[0] for ut in db.session.query(SUSFeedback.user_type).distinct() if ut[0]]

        return render_template('admin/admin_feedback_list.html',
                               pagination=pagination,
                               filters=filters,
                               all_user_types=all_user_types)
    except Exception as e:
        logger.error(f"Admin view_all_feedback error: {e}", exc_info=True)
        return render_template('errors/500.html', error_message=str(e)), 500

@admin.route('/feedback/export-csv')
@admin_required
def export_feedback_csv():
    try:
        # similar filter logic...
        query = SUSFeedback.query
        results = query.order_by(SUSFeedback.timestamp.asc()).all()

        si = io.StringIO()
        cw = csv.writer(si)
        cw.writerow(['ID','User ID','Username','SUS Score','Timestamp'])
        for fb in results:
            cw.writerow([fb.id, fb.user_id, fb.user.username,
                         f'{fb.sus_score:.2f}', fb.timestamp.strftime('%Y-%m-%d %H:%M:%S')])
        output = make_response(si.getvalue())
        output.headers["Content-Disposition"] = "attachment; filename=feedback.csv"
        output.headers["Content-type"] = "text/csv"
        return output
    except Exception as e:
        logger.error(f"Export error: {e}", exc_info=True)
        abort(500, description="Failed to export feedback.")

@admin.route('/feedback/<int:feedback_id>')
@admin_required
def view_feedback_detail(feedback_id):
    feedback = SUSFeedback.query.get_or_404(feedback_id)
    user = User.query.get_or_404(feedback.user_id)
    return render_template('admin/admin_feedback_detail.html', feedback=feedback, user=user)

# ===========================================
# 🔑 ADMIN USER MANAGEMENT
# ===========================================
@admin.route('/create-admin', methods=['POST'])
@admin_required
def create_admin_user():
    try:
        csrf_token = request.headers.get('X-CSRFToken')
        validate_csrf(csrf_token)

        data = request.get_json() or {}
        username, email, password = data.get('username'), data.get('email'), data.get('password')
        if not username or not email or not password:
            return jsonify({'success': False, 'message': 'Missing fields'}), 400
        if len(password) < 12:
            return jsonify({'success': False, 'message': 'Password must be 12+ chars'}), 400

        existing = User.query.filter(or_(User.username == username, User.email == email)).first()
        if existing:
            if existing.is_admin:
                return jsonify({'success': False, 'message': 'Already an admin'}), 409
            existing.is_admin = True
            existing.password = generate_password_hash(password)
            db.session.commit()
            return jsonify({'success': True, 'message': 'Upgraded to admin'}), 200

        new_user = User(username=username, email=email,
                        password=generate_password_hash(password),
                        is_verified=True, is_admin=True)
        db.session.add(new_user)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Admin created'}), 201
    except Exception as e:
        db.session.rollback()
        logger.error(f"Create admin error: {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'Internal error'}), 500

@admin.route('/block-user/<int:user_id>', methods=['POST'])
@admin_required
def block_user(user_id):
    user = User.query.get(user_id)
    if not user: return jsonify({'success': False,'message':'Not found'}),404
    if user.is_admin: return jsonify({'success': False,'message':'Cannot block admin'}),403
    user.is_blocked=True; db.session.commit()
    return jsonify({'success':True,'message':'User blocked'})

@admin.route('/unblock-user/<int:user_id>', methods=['POST'])
@admin_required
def unblock_user(user_id):
    user = User.query.get(user_id)
    if not user: return jsonify({'success': False,'message':'Not found'}),404
    user.is_blocked=False; db.session.commit()
    return jsonify({'success':True,'message':'User unblocked'})

@admin.route('/users')
@admin_required
def manage_users():
    page = request.args.get('page',1,type=int)
    query = User.query.order_by(User.username.asc())
    users = query.paginate(page=page, per_page=10)
    return render_template('admin/admin_user_list.html', users=users)

# ===========================================
# CSRF Error Handler
# ===========================================
@admin.errorhandler(CSRFError)
def handle_csrf_error(e):
    return jsonify({"message": "CSRF token missing or invalid."}), 400
