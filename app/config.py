import os

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev")
    SQLALCHEMY_DATABASE_URI = "sqlite:///movimientos.db"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), '..', 'uploads')
    # Limite maximo del request (archivos + form data). Default: 256 MB.
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH", str(256 * 1024 * 1024)))
    # Limite de memoria para campos multipart no-archivo (Werkzeug). Default: 20 MB.
    MAX_FORM_MEMORY_SIZE = int(os.environ.get("MAX_FORM_MEMORY_SIZE", str(20 * 1024 * 1024)))
    # Numero maximo de partes multipart (campos + archivos). Default: 5000.
    MAX_FORM_PARTS = int(os.environ.get("MAX_FORM_PARTS", "5000"))
