@echo off
REM -- Iniciar servidor con Waitress en el puerto 5600
waitress-serve --host=0.0.0.0 --port=5600 main:app
