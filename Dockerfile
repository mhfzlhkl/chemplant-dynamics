# ─────────────────────────────────────────────────────────────
# ChemPlant Dynamics — production Dockerfile
# ─────────────────────────────────────────────────────────────
#
# Two-stage build that produces a slim runtime image containing
# just the Python runtime, the pre-built wheels, and the
# ChemPlant source. No compiler, no apt cache, no .git history.
#
# Build context: the app_root/ directory (the one that holds
# requirements.txt and app/). Pair with the .dockerignore in
# the same directory so the build context stays small.
#
# Image size: ~450 MB compressed. numpy + scipy pull most of
# that in via their manylinux wheels; the rest is the Python
# stdlib and NiceGUI's static assets.
#
# Run: docker run -p 8080:8080 \
#              ghcr.io/<owner>/<repo>:<tag>
# Run behind a host-supplied port (Fly / Render / Railway):
#   docker run -p 8080:8080 -e PORT=8080 \
#              ghcr.io/<owner>/<repo>:<tag>
# The entrypoint maps $PORT → $NICEGUI_PORT automatically —
# see tools/docker_start.py.
#
# HEALTHCHECK uses the in-app /healthz route. We do not probe
# a real UI page because the home page is heavy (loads the
# full inlined CSS bundle + Google Fonts) and the engine pages
# are slower still under cold cache. /healthz is a constant-
# time endpoint that returns 200 the moment the ASGI server
# is accepting requests, which is the right readiness signal
# for a container orchestrator. See
# https://nicegui.io/documentation/section_configuration_deployment
# for the canonical NiceGUI deploy pattern.

# ── Stage 1: build wheels ──────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# build-essential + gcc are only needed for the rare sdist-only
# dependency; the major libs (numpy, scipy) ship manylinux
# wheels from PyPI and never invoke the compiler. We install
# them so future dependency changes don't break the build.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./

# Install into /install with --no-cache-dir so the layer
# stays small. The trailing slash on /install in the runtime
# stage is intentional — it copies the directory *contents*
# (lib/, bin/) into /usr/local so the packages are picked up
# by the system Python on PATH.
RUN pip install --no-cache-dir --prefix=/install \
        -r requirements.txt

# ── Stage 2: runtime ───────────────────────────────────────
FROM python:3.12-slim AS runtime

# Build-time args the workflow passes in. They become
# env vars at runtime so /healthz can report the exact
# commit + build time inside the container.
ARG BUILD_TIME=unknown
ARG GIT_SHA=unknown

# Canonical NiceGUI env vars. See app/main.py for the full
# list and the official docs link. We default to a sane
# production profile: no auto-reload, no browser tab,
# 'warning' uvicorn level, UTC timezone.
#
# PORT is intentionally NOT defaulted — the orchestrator
# (Fly / Render / Railway / Heroku) injects it. The
# entrypoint maps $PORT → $NICEGUI_PORT so NiceGUI sees it.
ENV TZ=UTC \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    NICEGUI_HOST=0.0.0.0 \
    NICEGUI_PORT=8080 \
    SHOW_WELCOME_MESSAGE=false \
    NICEGUI_LOG_LEVEL=warning \
    BUILD_TIME=${BUILD_TIME} \
    GIT_SHA=${GIT_SHA}

WORKDIR /app

# Copy the pre-built site-packages. The trailing slash on
# /install/lib/python3.12/site-packages is intentional — it
# copies the directory *contents* into the destination
# directory so the resulting tree looks like a normal Python
# install (importable from the default sys.path).
COPY --from=builder /install/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /install/bin /usr/local/bin

# Source. Copied AFTER the deps so source-only changes don't
# bust the (much slower) dependency layer.
COPY app/        ./app/
COPY cases/      ./cases/
COPY core/       ./core/
COPY engine/     ./engine/
COPY gateway/    ./gateway/
COPY models/     ./models/
COPY scripts/    ./scripts/
COPY systems/    ./systems/
COPY tools/      ./tools/
COPY README.md   ./README.md
COPY requirements.txt ./requirements.txt

# The app binds to NICEGUI_PORT (default 8080) on NICEGUI_HOST
# (default 0.0.0.0). EXPOSE is informational — `docker run -p`
# doesn't need it — but it documents intent for anyone reading
# the Dockerfile.
EXPOSE 8080

# The HEALTHCHECK curls /healthz, a 200-only endpoint the
# app registers before ui.run is called (see app/main.py).
# The /healthz body is also useful for `docker logs` debugging
# but the container orchestrator only inspects the status code.
#
# Why no --start-period? NiceGUI's underlying uvicorn binds
# its socket in a single syscall; if we can curl /healthz
# at all, the server is ready. A 5s interval + 3 retries =
# 15s to declare the container unhealthy, which is fast
# enough for orchestrators to roll a replacement.
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${NICEGUI_PORT}/healthz" >/dev/null || exit 1

# Exec form so SIGTERM is delivered to the Python process
# (shell form would forward to /bin/sh which doesn't
# propagate signals reliably on slim images). The entrypoint
# script does $PORT → $NICEGUI_PORT mapping, then imports
# app.main, which calls ui.run(...) and blocks until SIGTERM.
ENTRYPOINT ["python", "-m", "tools.docker_start"]
