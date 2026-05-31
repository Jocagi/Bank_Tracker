import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path

from flask import current_app

_scheduler_started = False
_scheduler_lock = threading.Lock()


def _get_application(app=None):
    if app is not None:
        return app
    return current_app._get_current_object()


def _resolve_source_database_path(application):
    from .. import db

    engine_url = db.engine.url
    if engine_url.drivername != 'sqlite':
        raise RuntimeError('El respaldo automático solo soporta bases SQLite.')

    database_path = engine_url.database
    if not database_path:
        raise RuntimeError('No se pudo determinar la ruta de la base de datos.')

    return Path(database_path)


def _resolve_backup_target_path(application, source_path):
    backup_setting = (application.config.get('DATABASE_BACKUP_PATH') or '').strip()
    if not backup_setting:
        raise ValueError('Configura DATABASE_BACKUP_PATH en el .env.')

    raw_target = Path(backup_setting).expanduser()
    target_text = str(backup_setting)
    if raw_target.exists() and raw_target.is_dir() or target_text.endswith(('\\', '/')):
        raw_target.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_name = f'{source_path.stem}_{timestamp}{source_path.suffix or ".db"}'
        return raw_target / backup_name

    raw_target.parent.mkdir(parents=True, exist_ok=True)
    return raw_target


def backup_database(app=None):
    application = _get_application(app)
    source_path = _resolve_source_database_path(application)
    if not source_path.exists():
        raise FileNotFoundError(f'No existe la base de datos en {source_path}')

    target_path = _resolve_backup_target_path(application, source_path)
    if target_path.resolve() == source_path.resolve():
        raise ValueError('La ruta de respaldo no puede ser la misma que la base de datos de origen.')

    if target_path.exists() and target_path.is_file():
        target_path.unlink()

    with sqlite3.connect(str(source_path)) as source_conn:
        with sqlite3.connect(str(target_path)) as target_conn:
            source_conn.backup(target_conn)

    return target_path


def _backup_loop(application, interval_seconds):
    while True:
        time.sleep(interval_seconds)
        try:
            with application.app_context():
                backup_path = backup_database(application)
                application.logger.info('Respaldo automatico creado en %s', backup_path)
        except Exception as exc:
            application.logger.exception('No se pudo crear el respaldo automatico: %s', exc)


def start_backup_scheduler(app):
    global _scheduler_started

    backup_path = (app.config.get('DATABASE_BACKUP_PATH') or '').strip()
    interval_hours = float(app.config.get('DATABASE_BACKUP_INTERVAL_HOURS') or 24)
    if not backup_path or interval_hours <= 0:
        return

    with _scheduler_lock:
        if _scheduler_started:
            return
        _scheduler_started = True

    interval_seconds = int(interval_hours * 3600)
    worker = threading.Thread(
        target=_backup_loop,
        args=(app, interval_seconds),
        name='database-backup-scheduler',
        daemon=True,
    )
    worker.start()