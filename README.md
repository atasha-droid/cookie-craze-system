# Cookie Craze (inner project README)

This folder contains the Django project for Cookie Craze.

Helpful files
- Django entrypoint: [cookie_project/manage.py](cookie_project/manage.py)
- Django settings: [cookie_project/cookie_project/settings.py](cookie_project/cookie_project/settings.py)
- App package: [cookie_project/cookie_app/](cookie_project/cookie_app/)
  - App config: [`CookieAppConfig`](cookie_project/cookie_app/apps.py)
  - URL routing: [cookie_project/cookie_app/urls.py](cookie_project/cookie_app/urls.py)
  - Views: [cookie_project/cookie_app/views.py](cookie_project/cookie_app/views.py) (contains debug helpers like [`debug_form_data`](cookie_project/cookie_app/views.py))
  - Models: [cookie_project/cookie_app/models.py](cookie_project/cookie_app/models.py)
  - Utilities: [cookie_project/cookie_app/utils.py](cookie_project/cookie_app/utils.py) (contains [`generate_receipt_data`](cookie_project/cookie_app/utils.py), [`generate_daily_report`](cookie_project/cookie_app/utils.py))
  - Management commands: [cookie_project/cookie_app/management/commands/](cookie_project/cookie_app/management/commands/)
- Templates: [cookie_project/templates/](cookie_project/templates/) — dashboards, admin, staff, void modal, etc.
- Static assets: [cookie_project/static/](cookie_project/static/) — CSS (including Bootstrap), JS bundles, images, manifest.

Developer tips
- When adding template changes, keep styles consistent with existing variables in [cookie_project/static/css/style.css](cookie_project/static/css/style.css) and theme tokens in [cookie_project/templates/base.html](cookie_project/templates/base.html).
- Use existing debug routes in [cookie_project/cookie_app/urls.py](cookie_project/cookie_app/urls.py) while developing (e.g. `debug-form-data`).
- To import signals automatically, review [`CookieAppConfig.ready()`](cookie_project/cookie_app/apps.py).

## Running locally

From the `cookie_project` folder (this folder):

1. (Optional) Create and activate a virtual environment.
2. Install Python dependencies:

    ```bash
    pip install -r requirements.txt
    ```

3. Create a `.env` file next to `manage.py` with at least:

    ```env
    SECRET_KEY=your-local-secret-key
    DEBUG=True
    ALLOWED_HOSTS=localhost,127.0.0.1
    ```

    If these are not set locally, sensible defaults from `settings.py` are used (SQLite database, debug on).

4. Apply migrations and run the development server:

    ```bash
    python manage.py migrate
    python manage.py runserver
    ```

## Environment variables

The project reads several settings from environment variables:

- `SECRET_KEY` – required for production, auto-generated on Render via `render.yaml`.
- `DEBUG` – `True` for local development, `False` on Render.
- `ALLOWED_HOSTS` – comma-separated list of hosts, e.g. `cookie-craze-system.onrender.com,localhost,127.0.0.1`.
- `DATABASE_URL` – optional locally; on Render this is provided automatically by the attached PostgreSQL database. If not set, SQLite is used.

## Deploying to Render

Deployment is handled from the **repository root** via:

- `render.yaml` – defines the Render web service.
- `build.sh` – installs requirements and runs database migrations.
- `Procfile` / `gunicorn cookie_project.wsgi:application` – production WSGI entrypoint.
- `runtime.txt` – pins the Python version used by Render.

High-level steps:

1. Commit and push changes to GitHub.
2. In Render, create or update a Python Web Service that points to this repo.
3. Configure environment variables in the Render dashboard (`SECRET_KEY`, `ALLOWED_HOSTS`, link a PostgreSQL database so `DATABASE_URL` is set).
4. Trigger a deploy (or push new commits) and Render will run `build.sh` and start Gunicorn using the config above.

Logs & troubleshooting
- Views include simple print/JsonResponse helpers (e.g. [`debug_form_data`](cookie_project/cookie_app/views.py)) that help inspect POST payloads and CSRF behavior.
- If static assets or templates don't reflect changes, clear browser cache and ensure `DEBUG=True` for local development.

This file supplements the repository root README with paths and workflows focused on the Django project internals.
