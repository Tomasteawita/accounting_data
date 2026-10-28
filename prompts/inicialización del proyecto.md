**Copia el siguiente texto y envíaselo a tu agente de IA:**

**Contexto y Rol:**
Actúa como un Arquitecto de Software Senior y experto en DevOps. Te encuentras en un repositorio completamente vacío. Tu objetivo es inicializar un proyecto de Django preparado para producción, contenido en Docker y optimizado para desplegarse en una instancia AWS EC2 (arquitectura ARM, t4g.small) con recursos limitados (2GB RAM). La arquitectura debe ser austera, segura y monolítica (Django + PostgreSQL + Nginx).
**Fase 1: Infraestructura y Entorno (Docker & .env)**
1. Crea el archivo `.env.example` con las variables de entorno necesarias para producción (DB_NAME, DB_USER, DB_PASSWORD, SECRET_KEY, DEBUG=False, ALLOWED_HOSTS).
2. Crea el archivo `Dockerfile` para Python (usa una imagen base ligera como `python:3.11-slim` o `alpine`). Configura la instalación de dependencias, el usuario no-root por seguridad y el comando de inicio usando `gunicorn`.
3. Crea el archivo `requirements.txt` incluyendo `Django`, `psycopg2-binary`, `gunicorn`, y `python-dotenv`.
4. Crea la configuración `nginx/nginx.conf` como proxy inverso. Debes incluir una directiva estricta de límite de carga (`client_max_body_size 5M;`) para proteger la memoria RAM del servidor contra subidas de archivos masivos, y configurar el ruteo de archivos estáticos.
5. Crea el archivo `docker-compose.yml` con tres servicios: `web` (Django), `db` (PostgreSQL 15) y `nginx`. Configura los volúmenes persistentes para la base de datos y los estáticos (`static_volume`), asegurando que Nginx y Gunicorn se comuniquen a través de una red interna, los volumes tienen que estar dentro de un directorio dentro del directorio raíz.


**Fase 2: Inicialización del Proyecto Django**
1. Genera la estructura base del proyecto Django llamado `accounting_data` y una aplicación inicial llamada `app`.
2. Configura `settings.py` para leer variables desde el `.env`, usar PostgreSQL como base de datos y definir las rutas de `STATIC_ROOT`.
3. Crea una vista inicial en `app/views.py` que renderice un *Home* vacío. Configura `urls.py` del proyecto y de la aplicación para que esta vista responda en la ruta raíz (`/`).


**Fase 3: Contexto y Reglas para el Futuro (System Skills)**
Crea un archivo llamado `docs/AI_FRONTEND_GUIDELINES.md` (o `.cursorrules` si corresponde). En este archivo, redacta las reglas innegociables que deberás seguir (tú y cualquier otra IA) al generar nuevas interfaces o templates en este proyecto:
* **Estética Visual**: Diseño minimalista, estoico y contable. El color de fondo predominante debe ser un blanco suavizado (ej. #F8F9FA o #F5F5F5, nunca blanco puro). Todos los demás elementos (tipografía, bordes, sombras, botones y contenedores) deben estructurarse estrictamente en una escala de grises y negros (ej. #1A1A1A para texto principal, #4D4D4D para texto secundario, #E0E0E0 para divisiones). Queda terminantemente prohibido el uso de colores saturados o ruido cromático.
* **Rendimiento:** Priorizar HTML/CSS puro y Vanilla JS (o HTMX) para evitar la sobrecarga de frameworks frontend pesados.
* **Ingesta de Datos:** Cualquier formulario que reciba archivos CSV o Excel debe procesar la información en memoria usando `pandas` y desechar el archivo inmediatamente para no consumir el almacenamiento EBS.
* **Tono del Copywriting:** Firme, analítico y directo.


**Restricción de Ejecución:**
Genera el código de todos estos archivos sin explicaciones innecesarias ni preámbulos. Presenta la estructura de directorios resultante y el contenido de cada archivo.