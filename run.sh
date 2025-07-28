:: 0. Crear un entorno virtual
python -m venv venv

:: 1. Activar el entorno virtual
venv\Scripts\activate.bat

:: 2. Instalar dependencias
pip install -r requirements.txt

:: 3. Definir variables de entorno
set FLASK_APP=main:app
set FLASK_ENV=development
set SECRET_KEY=tu_clave_secreta
set DATABASE_URL=sqlite:///movimientos.db

:: 4. Inicializar migraciones
python -m flask --app main:app db init

:: 5. Crear la migración inicial
python -m flask --app main:app db migrate -m "Initial migration"

:: 6. Aplicar la migración
python -m flask --app main:app db upgrade

:: 7. Ejecutar la aplicación
python -m flask --app main:app run