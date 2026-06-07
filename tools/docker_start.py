"""tools.docker_start — production container entrypoint.

This module is intentionally tiny. It does three things:

1. **Forward the orchestrator's port to NiceGUI's canonical
   env var.** Fly.io / Render / Railway / Heroku all set
   ``$PORT`` for the process to bind; NiceGUI looks at
   ``$NICEGUI_PORT``. Mapping the two means the container
   Just Works on any of those hosts without code changes.
2. **Set build-time metadata** (``CHEMPLANT_BUILD_TIME``,
   ``CHEMPLANT_GIT_SHA``) from build args the Dockerfile
   passes in. The ``/healthz`` endpoint surfaces them so
   ``curl /healthz`` from inside the container reveals the
   exact commit that is running.
3. **Import ``app.main``** — which itself calls
   ``ui.run(...)`` at module scope (see [app/main.py](app/main.py)),
   the canonical NiceGUI entrypoint. We do NOT call
   ``ui.run()`` again ourselves; doing so would bind a
   *second* server on a different port and the original
   would never receive SIGTERM.

No readiness probe, no socket polling, no sentinel file. The
container is "ready" as soon as NiceGUI's underlying
``uvicorn`` server accepts a request, and the Docker
``HEALTHCHECK`` in the Dockerfile greps ``/healthz`` which
returns 200 the moment the ASGI loop is up. See the official
[NiceGUI deployment docs](https://nicegui.io/documentation/section_configuration_deployment)
for the recommended pattern.
"""

from __future__ import annotations

import importlib
import os
import sys


# Canonical env-var mapping. We translate the *host* env vars
# (which every PaaS sets) to NiceGUI's expected names BEFORE
# importing app.main — NiceGUI reads them at the moment
# ``ui.run`` is called and there's no second chance.
#
# Mapping order:
#   1. $PORT        (Heroku / Render / Fly / Railway default)
#   2. $NICEGUI_PORT (already-set override wins)
#   3. fall through — app/main.py will default to 8080
_HOST_PORT_NAMES = ('PORT',)
_NICEGUI_PORT_NAME = 'NICEGUI_PORT'


def _forward_port() -> None:
    """If the host set ``$PORT`` but not ``$NICEGUI_PORT``,
    copy the value across. ``$NICEGUI_PORT`` always wins so
    a deployment that wants a fixed port can pin it.
    """
    if os.environ.get(_NICEGUI_PORT_NAME):
        return  # explicit override — leave alone
    for name in _HOST_PORT_NAMES:
        host_port = os.environ.get(name)
        if host_port:
            os.environ[_NICEGUI_PORT_NAME] = host_port
            return


def _apply_build_metadata() -> None:
    """Surface build-time metadata so ``/healthz`` can show it.

    The Dockerfile passes ``--build-arg`` values which the
    image then exposes as env vars via ``ENV``. We forward
    them under the names the app reads (``CHEMPLANT_BUILD_TIME``,
    ``CHEMPLANT_GIT_SHA``). If the user runs the image without
    those build args the values stay as the app's defaults
    ('unknown').
    """
    # The Dockerfile's build args land as env vars named
    # ``BUILD_TIME`` and ``GIT_SHA`` so the env block stays
    # short. The app expects ``CHEMPLANT_*`` so we copy them
    # across.
    for src, dst in (
        ('BUILD_TIME', 'CHEMPLANT_BUILD_TIME'),
        ('GIT_SHA', 'CHEMPLANT_GIT_SHA'),
    ):
        if src in os.environ and dst not in os.environ:
            os.environ[dst] = os.environ[src]


def main() -> int:
    _forward_port()
    _apply_build_metadata()
    try:
        # ``import app.main`` triggers ``ui.run(...)`` at module
        # scope, which blocks the main thread until SIGTERM.
        # This is the production entry point and matches
        # ``python -m app.main`` exactly.
        importlib.import_module('app.main')  # noqa: F401
    except KeyboardInterrupt:
        return 0
    except SystemExit as exc:
        # NiceGUI calls ``sys.exit(0)`` on a clean shutdown.
        return int(exc.code or 0)
    except Exception as exc:  # pragma: no cover - import path errors
        print(f'[docker_start] failed to import app.main: {exc!r}',
              file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':  # pragma: no cover
    raise SystemExit(main())
