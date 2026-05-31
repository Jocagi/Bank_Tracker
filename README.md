# Bank Tracker

**Bank Tracker** es una aplicación web desarrollada en **Flask** para gestionar, clasificar y visualizar movimientos bancarios de distintas cuentas (monetarias, de ahorro y tarjetas de crédito) de forma centralizada. Está pensada para uso personal o corporativo ligero, con base de datos SQLite y funcionalidades de carga automática desde archivos Excel, CSV y PDF.

---

## 📋 Características

- **Carga de archivos**  
  - Soporta Excel (`.xlsx`, `.xls`), CSV y PDF de múltiples bancos (GYT, BI, etc.)  
  - Detecta y extrae _metadata_ (titular, número de cuenta, tipo de cuenta, moneda, saldo inicial)  
  - Procesa tablas de movimientos en distintas posiciones y hasta la primera línea vacía  
  - Detección de duplicados por hash de archivo  

- **Modelo de datos**  
  - **Cuenta**: banco, tipo, número, titular, moneda  
  - **Archivo**: banco, tipo de cuenta, nombre de archivo, fecha de carga, hash  
  - **Movimiento**: fecha, descripción, lugar, documento, monto, moneda, tipo (débito/crédito), referencia al archivo y a la cuenta  
  - **Comercio** y **Categoría**: clasificación de movimientos  
  - **Regla**: expresiones (comodines `*`, exactas con prefijo `=`) para asignar/comprobar exclusión o inclusión  
  - **TipoCambio**: tipo de cambio por moneda para conversión a GTQ  

- **Clasificación automática**  
  - Sistema de reglas con expresiones regulares seguras  
  - Reglas de **exclusión** y **inclusión** por comercio  
  - Posibilidad de previsualizar y reclasificar masivamente  

- **Dashboard e informes**  
  - Tablas de totales (gastos por comercio, gastos por categoría, ingresos por comercio)  
  - Gráficas de pastel (`Chart.js`) y evolución mensual  
  - Filtros por fecha, categoría, comercio y tipo de contabilización  
  - Conversión a GTQ usando los tipos de cambio configurados  

- **Administración**  
  - Mantenimiento de comercios y categorías  
  - Mantenimiento de reglas  
  - Administración de archivos (eliminar carga y movimientos asociados)  
  - Gestión de tipos de cambio  

---

## 🚀 Tecnologías

- **Backend**: Python 3.9+, Flask, SQLAlchemy, Flask-Migrate  
- **Procesamiento de archivos**: pandas, openpyxl, pdfplumber  
- **Frontend**: Bootstrap 5, Select2, Chart.js, jQuery  
- **Base de datos**: SQLite (local, sin servidor)  

---

## ⚙️ Instalación y puesta en marcha

1. **Clonar repositorio**  
   ```bash
   git clone https://github.com/tu-usuario/bank-tracker.git
   cd bank-tracker
   ```

2. **Crear y activar entorno virtual**

   ```bash
   python -m venv venv
   source venv/bin/activate    # Linux / macOS
   venv\Scripts\activate       # Windows PowerShell
   ```

3. **Instalar dependencias**

   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. **Variables de entorno**
   Crear archivo `.env` (o exportar variables) con, al menos:

   ```
   FLASK_APP=main.py
   FLASK_ENV=development
   SECRET_KEY=tu_secreto_aqui
   DATABASE_BACKUP_PATH=instance/backups/movimientos_backup.db
   DATABASE_BACKUP_INTERVAL_HOURS=24
   ```

   `DATABASE_BACKUP_PATH` puede apuntar a un archivo o a una carpeta. Si apuntas a una carpeta, el sistema crea un archivo con fecha y hora dentro de ese directorio.

5. **Inicializar base de datos**

   ```bash
   flask db init
   flask db migrate -m "Primer esquema"
   flask db upgrade
   ```

6. **Ejecutar la aplicación**

   ```bash
   flask run
   ```

   Por defecto estará disponible en `http://127.0.0.1:5000/`.

---

## � Crear usuario admin inicial

En una instalación nueva necesitas crear al menos un usuario administrador para acceder a las pantallas de administración. Hay un script de ayuda:

```powershell
# Desde la raíz del proyecto (Windows PowerShell)
python .\scripts\create_admin.py --username admin
```

Si omites `--password`, el script te pedirá la contraseña por consola de forma segura.

El script intenta crear las tablas si las migraciones no se han ejecutado todavía (usa `flask db upgrade` si prefieres gestionar migraciones explícitas).

## Respaldos de base de datos

Si defines `DATABASE_BACKUP_PATH` en `.env`, la app crea un respaldo automático cada `DATABASE_BACKUP_INTERVAL_HOURS` horas mientras el servidor está en ejecución.

También puedes ejecutarlo manualmente desde la pantalla **Datos** como administrador o con:

```powershell
flask backup-database
```


## �📝 Uso básico

1. **Cargar archivo**

   * Ir a **Cargar Archivo**
   * Seleccionar tipo de archivo (por banco / formato)
   * Subir el archivo Excel/CSV/PDF

2. **Revisar movimientos**

   * Panel principal muestra últimos movimientos
   * Filtros por cuenta, fecha, descripción, comercio, categoría, tipo

3. **Clasificar comercios**

   * Definir reglas en **Comercios → Agregar/Editar**
   * Revisar movimientos “sin clasificar” y asignar manual o automáticamente

4. **Ver Dashboard**

   * Filtrar rangos de fecha y categoría
   * Consultar tablas de totales y ver gráficas interactivas

5. **Administrar tipos de cambio**

   * Ir a **Tipos de Cambio**
   * Agregar o editar valor de cada moneda en GTQ

---

## 📄 Licencia

Este proyecto está licenciado bajo los términos de la [MIT License](LICENSE).
