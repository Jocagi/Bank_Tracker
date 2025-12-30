from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_wtf import CSRFProtect

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
login_manager.login_view = 'main.login'

def create_app():
    app = Flask(__name__)
    app.config.from_object("app.config.Config")

    # CSRF protection for all form POSTs
    csrf = CSRFProtect()
    csrf.init_app(app)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    # Importar los modelos para que estén registrados
    from . import models

    # Registra blueprints
    from .routes import bp as main_bp
    app.register_blueprint(main_bp)

    # user loader (deferred import para evitar ciclos)
    from .models import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    return app
