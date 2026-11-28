# Accounting Data

Arquitectura monolítica en contenedores (**Django + PostgreSQL 15 + Gunicorn + Nginx**) optimizada para entornos de recursos limitados (AWS EC2 `t4g.small`, 2 GB RAM) y ejecución local persistente.

---

## Requisitos Previos

* **Docker** y **Docker Compose** (Docker Desktop en Windows/macOS o Docker Engine en Linux).
* Verificar que el puerto `80` esté libre en `localhost`.

---

## Paso a Paso para Ejecutar el Proyecto en `localhost`

### 1. Configurar las variables de entorno

Copia el archivo de ejemplo `.env.example` para crear tu archivo `.env` local:

**En PowerShell (Windows):**
```powershell
Copy-Item .env.example .env
```

**En Bash (Linux / macOS / Git Bash):**
```bash
cp .env.example .env
```

> **Nota:** Puedes editar el archivo `.env` para personalizar `SECRET_KEY` y `DB_PASSWORD`. Asegúrate de mantener `ALLOWED_HOSTS=localhost,127.0.0.1` y `DB_HOST=db`.

---

### 2. Verificar los directorios de volúmenes persistentes

Los datos de PostgreSQL y los archivos estáticos se almacenan dentro del directorio `./volumes/` en la raíz del proyecto. Asegúrate de que existan antes de levantar los contenedores:

**En PowerShell (Windows):**
```powershell
New-Item -ItemType Directory -Force -Path .\volumes\postgres_data, .\volumes\static_volume
```

**En Bash (Linux / macOS):**
```bash
mkdir -p ./volumes/postgres_data ./volumes/static_volume
```

---

### 3. Construir y levantar el proyecto en segundo plano (Modo Persistente)

Ejecuta Docker Compose con la bandera `-d` (*detached mode*). Como los servicios tienen configurada la política `restart: unless-stopped`, el proyecto se mantendrá corriendo continuamente en `localhost` en segundo plano e incluso se reiniciará automáticamente si reinicias Docker o el equipo:

```bash
docker compose up -d --build
```

Al iniciar, el contenedor `web` ejecutará automáticamente:
1. Espera activa (`healthcheck`) hasta que PostgreSQL (`db`) esté listo para recibir conexiones.
2. `python manage.py migrate --noinput` para aplicar las migraciones en la base de datos.
3. `python manage.py collectstatic --noinput` para compilar los archivos estáticos en `./volumes/static_volume`.
4. Arranque del servidor de aplicaciones **Gunicorn** detrás del proxy inverso **Nginx**.

---

### 4. Verificar que el servicio está activo

1. Comprueba el estado de los contenedores:
   ```bash
   docker compose ps
   ```
   Los tres servicios (`accounting_db`, `accounting_web` y `accounting_nginx`) deben figurar como `Up` / `running`.

2. Abre tu navegador e ingresa a:
   * **Aplicación principal:** [http://localhost](http://localhost)
   * **Panel de administración:** [http://localhost/admin/](http://localhost/admin/)

---

## Comandos Útiles de Operación y Mantenimiento

* **Ver logs en tiempo real de todos los servicios:**
  ```bash
  docker compose logs -f
  ```

* **Ver logs únicamente de Django/Gunicorn:**
  ```bash
  docker compose logs -f web
  ```

* **Crear un superusuario para el panel de administración (`/admin`):**
  ```bash
  docker compose exec web python manage.py createsuperuser
  ```

* **Ejecutar nuevas migraciones manualmente:**
  ```bash
  docker compose exec web python manage.py makemigrations
  docker compose exec web python manage.py migrate
  ```

* **Reiniciar los servicios tras cambios en el código:**
  ```bash
  docker compose up -d --build
  ```

* **Detener los contenedores (conservando los datos en `./volumes/`):**
  ```bash
  docker compose down
  ```

## Desarrollo y despliegue a prodcción
  ```bash
  git checkout -b feature_rama_nueva
  git add .
  git commit -m "comentario descriptivo"
  git push -u origin feature_rama_nueva
  ```
Los PRs son SI O SI de feature_rama_nueva -> development -> main, luego conectarse al directorio remoto
```bash
# Una vez conectado al directorio remoto
cd nombre_repositorio
git pull origin main
docker compose up -d --build
  ```
