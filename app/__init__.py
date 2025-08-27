# app/__init__.py

import os
import logging
import time
from functools import wraps
from flask import Flask, render_template
from flask_login import LoginManager
from flask_cors import CORS
from flask_migrate import Migrate
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_mail import Mail
from .models import db
from flask_wtf import CSRFProtect

logger = logging.getLogger(__name__)
csrf = CSRFProtect()

# Rate limiter setup (configurable storage)
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100 per hour"],
    storage_uri=os.getenv("LIMITER_STORAGE_URI", "memory://")
)

migrate = Migrate()
mail = Mail()

DB_NAME = "database.db"

def create_app():
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))

    # Template and static folders
    TEMPLATE_FOLDER = os.path.join(BASE_DIR, 'templates')
    STATIC_FOLDER = os.path.join(BASE_DIR, 'static')
    os.makedirs(TEMPLATE_FOLDER, exist_ok=True)
    os.makedirs(STATIC_FOLDER, exist_ok=True)

    # Storage folder for database (default)
    STORAGE_FOLDER = os.path.abspath(os.path.join(BASE_DIR, "..", "storage"))
    os.makedirs(STORAGE_FOLDER, exist_ok=True)
    default_db_path = os.path.join(STORAGE_FOLDER, DB_NAME)

    # Allow environment variable override
    DB_PATH = os.getenv('DATABASE_PATH', default_db_path)

    app = Flask(
        __name__,
        template_folder=TEMPLATE_FOLDER,
        static_folder=STATIC_FOLDER
    )

    # CORS origins configurable
    origins = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5000,http://127.0.0.1:5000"
    ).split(",")
    CORS(app, supports_credentials=True, resources={r"/*": {"origins": origins}})

    # Secret key (must be set in env)
    secret = os.getenv("SECRET_KEY")
    if not secret:
        raise RuntimeError("SECRET_KEY must be set")
    app.config['SECRET_KEY'] = secret

    # Configure app settings
    app.config.update(
        SQLALCHEMY_DATABASE_URI=f'sqlite:///{DB_PATH}',
        SQLALCHEMY_TRACK_MODIFICATIONS=False,

        # Flask-Mail configuration
        MAIL_SERVER=os.getenv('MAIL_SERVER'),
        MAIL_PORT=int(os.getenv('MAIL_PORT', 587)),
        MAIL_USE_TLS=os.getenv('MAIL_USE_TLS', 'True').lower() == 'true',
        MAIL_USERNAME=os.getenv('MAIL_USERNAME'),
        MAIL_PASSWORD=os.getenv('MAIL_PASSWORD'),
        MAIL_DEFAULT_SENDER=os.getenv('MAIL_DEFAULT_SENDER'),

        # Secure cookies (production)
        SESSION_COOKIE_SECURE=True,
        REMEMBER_COOKIE_SECURE=True,
        SESSION_COOKIE_HTTPONLY=True,
        REMEMBER_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',

        # Backend Service Configuration
        COLAB_ENDPOINT=os.getenv('COLAB_ENDPOINT'),
        BACKEND_TIMEOUT=int(os.getenv('BACKEND_TIMEOUT', 60)),
        USE_LOCAL_BERT=os.getenv('USE_LOCAL_BERT', 'False').lower() == 'true',
        OFFLINE_MODE=os.getenv('OFFLINE_MODE', 'False').lower() == 'true'
    )

    csrf.init_app(app)
    db.init_app(app)
    migrate.init_app(app, db)
    limiter.init_app(app)
    mail.init_app(app)

    # Setup Flask-Login
    login_manager = LoginManager()
    login_manager.login_view = 'auth.login'
    login_manager.init_app(app)

    from .models import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Register blueprints
    from .views import views
    from .auth import auth
    from .chat import chat
    from .routes import api
    from .admin import admin

    app.register_blueprint(views, url_prefix='/')
    app.register_blueprint(auth, url_prefix='/auth')
    app.register_blueprint(chat, url_prefix='/chat')
    app.register_blueprint(api, url_prefix='/api')
    app.register_blueprint(admin, url_prefix='/admin')

    # Auto-create database tables if they don't exist
    with app.app_context():
        db.create_all()

    # Error Handlers
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return render_template('errors/500.html'), 500

    @app.template_filter('datetime')
    def format_datetime(value, format='%Y-%m-%d %H:%M:%S'):
        if value is None:
            return ""
        return value.strftime(format)

    # Attach backend service
    try:
        from .services.backend_service import BackendService
        app.backend_service = BackendService(app)
    except Exception as e:
        logger.warning(f"BackendService init failed (probably offline mode): {e}")

    return app


# Optional timing decorator (unchanged)
def monitor_response_time(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            end_time = time.time()
            duration = end_time - start_time
            logger.info(f"Operation '{func.__name__}' completed in {duration:.2f} seconds")
            return result
        except Exception as e:
            end_time = time.time()
            duration = end_time - start_time
            logger.error(f"Operation '{func.__name__}' failed after {duration:.2f} seconds: {str(e)}")
            raise
    return wrapper
