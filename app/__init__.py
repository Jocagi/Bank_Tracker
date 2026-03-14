from flask import Flask
from flask import flash, redirect, request, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from werkzeug.exceptions import RequestEntityTooLarge

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
login_manager.login_view = 'main.login'

def create_app():
    app = Flask(__name__)
    app.config.from_object("app.config.Config")

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

    @app.errorhandler(RequestEntityTooLarge)
    def handle_request_entity_too_large(_error):
        max_size = app.config.get('MAX_CONTENT_LENGTH', 0)
        max_mb = max_size / (1024 * 1024) if max_size else 0
        if max_mb:
            flash(
                f'La carga excede el limite permitido ({max_mb:.0f} MB). '
                f'Divide el lote o aumenta MAX_CONTENT_LENGTH.',
                'warning'
            )
        else:
            flash('La carga excede el limite permitido.', 'warning')

        # Intentar regresar a upload; fallback al referrer o inicio.
        try:
            return redirect(url_for('main.upload'))
        except Exception:
            return redirect(request.referrer or url_for('main.index'))

    return app
