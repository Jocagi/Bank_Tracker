@echo off
REM -- Iniciar servidor con Waitress en el puerto 5600
REM -- Activar el entorno virtual y usar waitress desde allí
call .venv\Scripts\activate.bat
.venv\Scripts\waitress-serve --host=0.0.0.0 --port=5600 main:app
