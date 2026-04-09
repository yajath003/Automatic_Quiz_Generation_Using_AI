from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_mail import Mail
from celery import Celery
from config import Config

db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()
mail = Mail()

def make_celery(app_name):
    # Return a basic celery instance. 
    # Config will be loaded in create_app using lowercase keys to avoid format mixing errors.
    return Celery(app_name)

celery = make_celery(__name__)

login_manager.login_view = 'auth.login'
login_manager.login_message_category = 'info'

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    mail.init_app(app)

    # Transform CELERY_ configuration to lowercase for Celery 5+
    # This prevents "ImproperlyConfigured: Cannot mix new setting names with old setting names"
    # we only update the celery object with transformed keys
    celery_conf = {
        key[7:].lower(): value
        for key, value in app.config.items()
        if key.startswith('CELERY_')
    }
    celery.conf.update(celery_conf)

    from app.auth import auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')

    from app.admin import admin_bp
    app.register_blueprint(admin_bp, url_prefix='/admin')

    from app.admin.admin_assignments import admin_assignments_bp
    app.register_blueprint(admin_assignments_bp, url_prefix='/admin/assignments')

    from app.user import user_bp
    app.register_blueprint(user_bp, url_prefix='/user')

    from app.ai_engine import ai_bp
    app.register_blueprint(ai_bp, url_prefix='/ai')

    from app.quiz import quiz_bp
    app.register_blueprint(quiz_bp, url_prefix='/quiz')

    from flask import render_template
    import json
    
    @app.template_filter('from_json')
    def from_json_filter(s):
        return json.loads(s)
        
    @app.route('/')
    def index():
        return render_template('index.html')

    return app




