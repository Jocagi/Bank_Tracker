from app import create_app
import logging

app = create_app()

# Enable logging to see errors
logging.basicConfig(level=logging.DEBUG)


def _run_startup_backup():
    backup_path = app.config.get('DATABASE_BACKUP_PATH', '').strip()
    if not backup_path:
        return

    from app.utils.database_backup import backup_database

    with app.app_context():
        created_path = backup_database(app)
        app.logger.info('Respaldo de arranque creado en %s', created_path)


_run_startup_backup()

if __name__ == "__main__":
    app.run(use_debugger=True)
