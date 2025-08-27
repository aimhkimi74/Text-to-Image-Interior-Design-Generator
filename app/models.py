from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from sqlalchemy.sql import func
from datetime import datetime

db = SQLAlchemy()


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    designs_created = db.Column(db.Integer, default=0)
    designs_shared = db.Column(db.Integer, default=0)
    is_verified = db.Column(db.Boolean, default=False)
    is_admin = db.Column(db.Boolean, default=False)
    is_blocked = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())
    verification_code = db.Column(db.String(10), nullable=True)
    verification_expires_at = db.Column(db.DateTime, nullable=True)
    reset_code = db.Column(db.String(10))
    reset_expires_at = db.Column(db.DateTime)

    favorite_styles = db.relationship('UserStyle', backref='user', lazy=True, cascade='all, delete-orphan')
    messages = db.relationship('ChatMessage', backref='user', lazy=True, cascade='all, delete-orphan')
    sessions = db.relationship('ChatSession', backref='user', lazy=True, cascade='all, delete-orphan')
    favorites = db.relationship('FavoriteImage', backref='user', lazy=True, cascade='all, delete-orphan')
    ratings = db.relationship('ImageRating', backref='user', lazy=True, cascade='all, delete-orphan')
    style_feedback = db.relationship('StyleFeedback', backref='user', lazy=True, cascade='all, delete-orphan')
    sus_feedback = db.relationship('SUSFeedback', back_populates='user', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f"<User {self.username} ({self.email})>"


class UserStyle(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    style_name = db.Column(db.String(50), nullable=False)
    count = db.Column(db.Integer, default=1)

    def __repr__(self):
        return f"<UserStyle {self.style_name} x{self.count}>"


class ChatSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(64), unique=True, nullable=False, index=True)
    name = db.Column(db.String(100), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())

    messages  = db.relationship('ChatMessage', back_populates='session_obj', lazy=True, cascade="all, delete-orphan")
    favorites = db.relationship('FavoriteImage', back_populates='session', lazy=True, cascade="all, delete-orphan")
    ratings   = db.relationship('ImageRating', back_populates='session', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<ChatSession {self.uuid} for User {self.user_id}>"


class ChatMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    is_user = db.Column(db.Boolean, default=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    session_id = db.Column(db.String(64), db.ForeignKey('chat_session.uuid'), nullable=False, index=True)
    timestamp = db.Column(db.DateTime(timezone=True), server_default=func.now())
    image_url = db.Column(db.Text, nullable=True)
    source = db.Column(db.String(20), default='api')
    detected_style = db.Column(db.String(80), nullable=True)
    style_reasons = db.Column(db.Text, nullable=True)

    session_obj = db.relationship('ChatSession', back_populates='messages', primaryjoin="ChatMessage.session_id == ChatSession.uuid")

    def __repr__(self):
        return f"<ChatMessage by User {self.user_id} at {self.timestamp}>"


class FavoriteImage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    session_id = db.Column(db.String(64), db.ForeignKey('chat_session.uuid'), nullable=True, index=True)  # NEW
    image_url = db.Column(db.String(500), nullable=False, index=True)
    prompt = db.Column(db.Text, nullable=False)
    style_name = db.Column(db.String(100), nullable=True)
    timestamp = db.Column(db.DateTime(timezone=True), server_default=func.now())

    session = db.relationship('ChatSession', back_populates='favorites')

    __table_args__ = (
        db.UniqueConstraint('user_id', 'image_url', name='unique_favorite_per_user'),
    )

    def __repr__(self):
        return f"<FavoriteImage style={self.style_name} for User {self.user_id}>"


class ImageRating(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    session_id = db.Column(db.String(64), db.ForeignKey('chat_session.uuid'), nullable=True, index=True)  # NEW
    image_url = db.Column(db.String(500), nullable=False, index=True)
    prompt_relevance = db.Column(db.Integer, nullable=False)
    image_quality = db.Column(db.Integer, nullable=False)
    style_accuracy = db.Column(db.Integer, nullable=False)
    style_tag = db.Column(db.String(50), nullable=True)
    timestamp = db.Column(db.DateTime(timezone=True), server_default=func.now())

    session = db.relationship('ChatSession', back_populates='ratings')

    def __repr__(self):
        return f"<ImageRating {self.image_url} by User {self.user_id}>"


class StyleFeedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    image_url = db.Column(db.String(500), nullable=False, index=True)
    original_style = db.Column(db.String(100), nullable=False)
    corrected_style = db.Column(db.String(100), nullable=False)
    timestamp = db.Column(db.DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<StyleFeedback corrected from {self.original_style} to {self.corrected_style}>"


class PromptFeedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    prompt = db.Column(db.Text, nullable=False)
    feedback = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(50), default='general')
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


class SUSFeedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)

    q1_frequency = db.Column(db.Integer, nullable=False)
    q2_complexity = db.Column(db.Integer, nullable=False)
    q3_ease_of_use = db.Column(db.Integer, nullable=False)
    q4_tech_support = db.Column(db.Integer, nullable=False)
    q5_integration = db.Column(db.Integer, nullable=False)
    q6_inconsistency = db.Column(db.Integer, nullable=False)
    q7_learnability = db.Column(db.Integer, nullable=False)
    q8_awkwardness = db.Column(db.Integer, nullable=False)
    q9_confidence = db.Column(db.Integer, nullable=False)
    q10_learning_curve = db.Column(db.Integer, nullable=False)

    comments = db.Column(db.Text, nullable=True)
    user_type = db.Column(db.String(50), nullable=True)
    sus_score = db.Column(db.Float, nullable=False)
    timestamp = db.Column(db.DateTime(timezone=True), server_default=func.now())

    user = db.relationship('User', back_populates='sus_feedback', lazy=True)

    def __repr__(self):
        return f"<SUSFeedback by User {self.user_id} at {self.timestamp} - Score: {self.sus_score}>"

    @staticmethod
    def calculate_sus_score(q1, q2, q3, q4, q5, q6, q7, q8, q9, q10):
        odd_scores = [q1 - 1, q3 - 1, q5 - 1, q7 - 1, q9 - 1]
        even_scores = [5 - q2, 5 - q4, 5 - q6, 5 - q8, 5 - q10]
        total = sum(odd_scores + even_scores) * 2.5
        return total
