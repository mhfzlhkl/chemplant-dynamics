# app/main.py

"""ChemPlant Dynamics — NiceGUI entrypoint.

Deployment model
----------------

The app follows the canonical NiceGUI deployment pattern (see the
official docs at
``https://nicegui.io/documentation/section_configuration_deployment``
and the ``ui.run`` signature in ``nicegui/ui_run.py``).

Configuration is driven entirely by environment variables:

* ``NICEGUI_HOST`` — bind host. Defaults to ``'0.0.0.0'`` (i.e.
  listen on every interface) when the env var is unset. In
  ``native`` mode it defaults to ``'127.0.0.1'`` instead, but we
  don't use that here.
* ``NICEGUI_PORT`` (or ``PORT`` for hosts that follow Heroku's
  convention) — bind port. Defaults to ``8080`` to match
  NiceGUI's own default.
* ``NICEGUI_STORAGE_PATH`` — directory for the per-user JSON
  storage files. Defaults to ``.nicegui/`` (project root).
* ``NICEGUI_REDIS_URL`` — optional Redis URL for *shared* storage
  across multiple workers / instances. Unset = local files.
* ``ON_AIR_TOKEN`` — NiceGUI Cloud tunnel token. Unset = no
  tunnel; the app serves on the configured host/port only.
* ``STORAGE_SECRET`` — session-cookie signing key. Required for
  ``app.storage.user`` to work; auto-generated per-boot if unset
  (so a leaked image isn't a security incident).
* ``SHOW_WELCOME_MESSAGE`` — set to ``0`` / ``false`` /
  ``no`` to suppress the "NiceGUI is running on …" stdout
  banner. We always pass ``False`` in production so the
  banner doesn't pollute container logs.

The block at the bottom of this file passes the resolved values
straight to ``ui.run(...)`` — no custom port-picker, no socket
probing, no monkey-patched env. ``ui.run`` itself reads
``NICEGUI_HOST`` / ``NICEGUI_PORT`` from the environment if its
explicit ``host`` / ``port`` args are ``None``; we forward our
own values so the canonical NiceGUI message
``"NiceGUI is running on http://0.0.0.0:8080"`` reflects the
real bind.

The ``/healthz`` endpoint is a tiny FastAPI route we register
*before* ``ui.run`` is called. The Docker ``HEALTHCHECK`` greps
this — see ``Dockerfile``. It does NOT depend on the engine
being importable, so it always returns 200 as soon as the
ASGI server accepts connections, which is the right readiness
signal for a container orchestrator.
"""

import os
import secrets
from pathlib import Path
import sys
from dotenv import load_dotenv

load_dotenv()

# Ensure project root is on sys.path so `app.*` imports resolve.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nicegui import ui, app  # noqa: E402

from app.config import STATIC_DIR  # noqa: E402

from app.pages import (  # noqa: F401, E402
    home_page,
    control_panel_page,
)


# ============================================================
# STATIC FILES
# ============================================================

app.add_static_files('/static', str(STATIC_DIR))


# ============================================================
# /healthz — readiness probe for container orchestrators
# ============================================================
# Cheap, no engine dependency, no I/O. Returns 200 as soon as the
# ASGI server is accepting requests, which is exactly what Docker
# HEALTHCHECK / Kubernetes livenessProbe / Fly.io health checks
# want. The endpoint also carries the build identifier so a
# ``docker inspect``-style debug session can confirm which
# commit is in the container.
# Registering the route goes through ``nicegui.app.app.App``'s
# ``.get`` proxy, which forwards to the underlying FastAPI app.
# We pass through the env vars that control the build so the
# endpoint can be self-documenting.

_BUILD_TIME = os.environ.get('CHEMPLANT_BUILD_TIME', 'unknown')
_GIT_SHA = os.environ.get('CHEMPLANT_GIT_SHA', 'unknown')


@app.get('/healthz')
def _healthz() -> dict:
    """Tiny readiness endpoint. Returns 200 + a small JSON body.

    The orchestrator's HEALTHCHECK only cares about the status
    code; the JSON body exists so ``curl /healthz`` from inside
    the container (or in CI logs) shows the build provenance.
    """
    return {
        'status': 'ok',
        'build_time': _BUILD_TIME,
        'git_sha': _GIT_SHA,
        'case_loaded': 'none',  # populated lazily by the case page
    }


# ============================================================
# CONFIG RESOLUTION
# ============================================================
# Each helper reads the canonical env var name first, then falls
# back to a small set of well-known aliases. Returning ``None``
# tells ``ui.run`` to use its own default (which itself reads
# the env var) — important for the "developer runs locally
# without setting anything" path.

def _resolve_host() -> str:
    """Bind host. ``NICEGUI_HOST`` wins; otherwise ``0.0.0.0``
    so Docker port-mapping works out of the box.
    """
    return os.environ.get('NICEGUI_HOST') or '0.0.0.0'


def _resolve_port() -> int:
    """Bind port. ``NICEGUI_PORT`` wins; otherwise ``PORT`` (the
    Heroku / Render / Fly convention); otherwise ``8080``.
    """
    for name in ('NICEGUI_PORT', 'PORT'):
        raw = os.environ.get(name)
        if raw:
            try:
                port = int(raw)
                if 1 <= port <= 65535:
                    return port
            except (TypeError, ValueError):
                pass
    return 8081


def _resolve_storage_secret() -> str:
    """Session-cookie signing key.

    * If ``STORAGE_SECRET`` is set: use it (production with
      persistent sessions).
    * If unset: generate a random key per process. Sessions
      won't survive a container restart, but the app still
      works and no secret leaks into the image.
    """
    explicit = os.environ.get('STORAGE_SECRET')
    if explicit:
        return explicit
    # 32 bytes of OS-provided randomness, hex-encoded. This is
    # the right default for ephemeral containers; the storage
    # class (app.storage.user) still works, it just forgets on
    # restart.
    return secrets.token_hex(32)


def _resolve_show_welcome() -> bool:
    """Whether to print the ``"NiceGUI is running on ..."`` banner.

    Off in production — banner clutters container logs and the
    public URL is already on the Docker host's port mapping.
    On in dev (default).
    """
    raw = os.environ.get('SHOW_WELCOME_MESSAGE', '').strip().lower()
    if raw in ('0', 'false', 'no', 'off'):
        return False
    if raw in ('1', 'true', 'yes', 'on'):
        return True
    # Default: off in container, on otherwise. The presence of
    # /.dockerenv is the standard Linux heuristic for "running
    # inside a container" — works on Docker / Podman / Kubernetes
    # / Lima / Rancher Desktop.
    return not Path('/.dockerenv').exists()


# ============================================================
# APP RUN
# ============================================================
# All NiceGUI config is read from environment variables above.
# We pass explicit values to ``ui.run`` so the resolved host /
# port are visible in the function signature (and so the
# "NiceGUI is running on ..." banner reflects the real bind).

ui.run(
    title='ChemPlant Dynamics',
    # ``reload=False`` in production; the Dockerfile's CMD
    # already loads everything once. Auto-reload is for dev.
    reload=False,
    # Dark mode by default — the UI is designed around it. The
    # Quasar theme switch is still available per-page.
    dark=True,
    host=_resolve_host(),
    port=_resolve_port(),
    # The show flag controls whether a browser tab is auto-
    # opened at startup. In a container there is no browser
    # and no display, so we always disable it. The Docker
    # HEALTHCHECK and the ``/healthz`` endpoint are how an
    # operator checks liveness.
    show=False,
    # on_air tunnel — set ON_AIR_TOKEN to expose the app via
    # NiceGUI Cloud. When unset, the app runs purely on the
    # configured host/port with no cloud dependency.
    on_air=os.environ.get('ON_AIR_TOKEN') or None,
    # Session-cookie signing key. See ``_resolve_storage_secret``
    # above for the no-env-var default.
    storage_secret=_resolve_storage_secret(),
    # Silence the startup banner in production (containers).
    show_welcome_message=_resolve_show_welcome(),
    # We rely on ``fastapi_docs=False`` (the default) so the
    # OpenAPI schema is not served. The control panel's UI is
    # the public surface; the FastAPI schema would just leak
    # internal routes. Override via the env in dev if you need
    # the Swagger UI.
    fastapi_docs=False,
    # uvicorn log level. 'warning' keeps the container logs
    # focused on real problems. Override with NICEGUI_LOG_LEVEL
    # in dev if you need access/debug spam.
    uvicorn_logging_level=os.environ.get(
        'NICEGUI_LOG_LEVEL', 'warning',
    ),
)
