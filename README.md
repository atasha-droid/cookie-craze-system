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

Running locally
- See top-level README instructions. Use the project subfolder as the Django project root when running manage.py commands.

Logs & troubleshooting
- Views include simple print/JsonResponse helpers (e.g. [`debug_form_data`](cookie_project/cookie_app/views.py)) that help inspect POST payloads and CSRF behavior.
- If static assets or templates don't reflect changes, clear browser cache and ensure runserver is running in DEBUG mode.

This file supplements the repository root README with paths focused on the Django project internals.
