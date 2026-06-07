# ChemPlant Dynamics

## Purpose

Simulation runtime and NiceGUI UI for chemical plant dynamics with
multi-case support. The engine (`core/`, `engine/`, `gateway/`,
`cases/`, `systems/`, `models/`) is **case-agnostic**; the UI
(`app/`) is built around a single **parent–child broadcast hub**
that fans engine values out to every consumer in the same tick.

## Run

```bash
# from app_root/
python -m app.main
```

The bind host/port default to `0.0.0.0:8080`; override with
`NICEGUI_HOST` and `NICEGUI_PORT` (or just `$PORT` — the
Heroku / Fly / Render / Railway convention). See the
[**Env-var reference**](#env-var-reference) below for the full
list.

Then open `http://localhost:8080/control-panel/<case>`:

- `/control-panel/sthr` — Stirred Tank Heater
- `/control-panel/biodiesel` — Biodiesel Reactor
- `/control-panel` — redirects to the first registered case.
- `/healthz` — readiness endpoint (returns 200 + JSON with
  build metadata). Useful for Docker `HEALTHCHECK`,
  Kubernetes livenessProbe, and Fly.io health checks.

## Deploy

Two deploy targets share the same source tree:

1. **NiceGUI server (local + `on_air` tunnel).** The full app,
   including the live control panel. Used for development and
   for the interactive demo behind the static landing page.
2. **GitHub Pages (static landing page).** The home page only
   is exported to `docs/index.html` and published via
   `.github/workflows/deploy_pages.yml`. The case-card links
   point at the on_air tunnel URL (set via the `ON_AIR_PROD_URL`
   repository variable) so the visitor lands on a live
   control panel.

### Local

```bash
python -m app.main
# open http://localhost:8080/
```

### `on_air` tunnel

```bash
ON_AIR_TOKEN=<your-token> python -m app.main
# the script prints the on_air URL on startup
```

### Static export (GitHub Pages)

```bash
ON_AIR_PROD_URL=https://on-air.nicegui.io/<token> \
    python -m tools.export_static
# → docs/index.html + docs/assets/...
# The deploy_pages workflow runs the same command on every
# push to main.
```

#### Full GitHub Pages deploy walkthrough

The repo ships with a ready-to-use Actions workflow at
[.github/workflows/deploy_pages.yml](.github/workflows/deploy_pages.yml).
On every push to `main` (and on manual `workflow_dispatch`) the
workflow renders the home page to `docs/` and publishes it to
GitHub Pages. You only need to do three one-time things:

1. **Enable GitHub Pages in the repository settings.**
   Open *Settings → Pages* and under *Source* pick
   **GitHub Actions**. The workflow uses the official
   `actions/deploy-pages` action so no extra configuration
   is needed once Pages is enabled.

2. **Allow Actions to write to Pages.**
   Same *Settings → Pages* page — under *Permissions* pick
   **Read and write permissions** for the `GITHUB_TOKEN` and
   turn on **Allow GitHub Actions to create and approve
   pull requests**. (The workflow already requests the
   `pages: write` and `id-token: write` permissions
   explicitly, but the org-wide setting still has to allow
   it.)

3. **Set the `ON_AIR_PROD_URL` repository variable.**
   Go to *Settings → Secrets and variables → Actions →
   Variables → New repository variable* and create:

   | Name             | Value                                  |
   |------------------|----------------------------------------|
   | `ON_AIR_PROD_URL`| `https://on-air.nicegui.io/<your-token>` |

   The value is the full base URL of your NiceGUI `on_air`
   tunnel — *without* a trailing slash and *without* the
   `/control-panel/<case>` suffix; the export script
   appends those paths when it rewrites the case-card
   links. Get the URL by running the app with
   `ON_AIR_TOKEN=<your-token> python -m app.main` and
   copying the URL the script prints at startup.

   The variable is plain text (not a secret) because
   `on_air` URLs are intentionally public. If you'd rather
   keep it private, store it as a *Secret* and change the
   workflow's `vars.ON_AIR_PROD_URL` reference to
   `secrets.ON_AIR_PROD_URL`.

That's it. Push to `main` and the workflow will:

1. Check out the repo.
2. Install just the dependencies the exporter needs
   (the workflow intentionally avoids `numpy` / `scipy` /
   `control` / `drawsvg` / `pandas` — the exporter only
   imports `app.assets` and `app.pages.home_page`).
3. Run `python -m tools.export_static` with the
   `ON_AIR_PROD_URL` variable injected.
4. Upload `docs/` as the GitHub Pages artifact.
5. Publish it via the official Pages deploy action.

The site will be available at
`https://<owner>.github.io/<repo>/` within a minute of the
workflow completing. Subsequent pushes replace the
artifact in place — there's no versioning, just the
current static export.

#### Local preview of the static export

```bash
# from app_root/
ON_AIR_PROD_URL=https://on-air.nicegui.io/<token> \
    python -m tools.export_static
cd docs
python -m http.server 8000
# open http://localhost:8000/
```

`docs/index.html` is fully self-contained (CSS is inlined
via `app.assets.collect_css`); the only external requests
are the Google Fonts `<link>` and the static assets copied
to `docs/assets/`.

#### What is *not* deployed to GitHub Pages

GitHub Pages is a static host. The control-panel pages
(`/control-panel/sthr` and `/control-panel/biodiesel`)
need a live NiceGUI process — the static export only
includes the home page. The case-card buttons on the
static home page deep-link into the `on_air` tunnel URL
configured via `ON_AIR_PROD_URL`, so a visitor always
ends up on a live control panel.

If you'd rather host the control panel alongside the
landing page *and* drop the NiceGUI Cloud dependency
entirely (so the only GitHub-owned artifact is the
container image itself), see the
[**Pure GitHub deploy (no NiceGUI token)**](#pure-github-deploy-no-nicegui-token)
section below.

## Pure GitHub deploy (no NiceGUI token)

If you'd like the entire stack — source, CI, **and** the running
container — to live on GitHub-owned infrastructure with **no
NiceGUI Cloud account**, this section walks through that path.
Three artifacts make it work; all three ship in this repo:

1. [`Dockerfile`](Dockerfile) — multi-stage build that produces
   a ~450 MB image containing just the Python runtime and the
   ChemPlant source tree.
2. [`.github/workflows/docker-publish.yml`](.github/workflows/docker-publish.yml) —
   builds the image for `linux/amd64` + `linux/arm64` and pushes
   it to **GitHub Container Registry (GHCR)** on every push to
   `main` and on every semver tag (`vX.Y.Z`). No PAT needed — the
   workflow uses the repo's `GITHUB_TOKEN`.
3. [`.dockerignore`](.dockerignore) — keeps the build context
   lean (skips `.venv`, `.nicegui/`, `tests/`, `docs/`, etc.).

Once the image is in GHCR you run it on any Docker host. Three
free tiers work well:

| Host        | Free tier                    | Notes                                        |
|-------------|------------------------------|----------------------------------------------|
| Fly.io      | 1 shared-cpu VM, 256 MB RAM  | Stays up 24/7, supports WebSockets           |
| Render.com  | 1 web service, spins down    | 15 min idle → cold start; OK for low traffic |
| Railway.app | $5/month credit              | Plenty for this small app                    |

All three read the same `ghcr.io/<owner>/<repo>:latest` tag.

### One-time setup

1. **Make the package public (optional).** After the first
   workflow run, open the package page on GitHub
   (`https://github.com/users/<owner>/packages/container/<repo>`)
   and change the visibility to *public* if you want anonymous
   pulls. Leaving it *private* still works — the deploy host
   will authenticate with a `GITHUB_TOKEN` (see step 3).

2. **Set the `ON_AIR_PROD_URL` repository variable** (only if
   you also want to publish the static GitHub Pages landing
   page that links into this image). The same variable as in
   the previous section. If you only want the container, skip
   this step.

3. **(For private images) create a deploy token.** Fly.io /
   Render / Railway each need a way to pull the image. Create
   a fine-grained PAT with `read:packages` scope (or use the
   `GITHUB_TOKEN` from a deploy action) and paste it into the
   host's "registry credentials" field. For Fly.io specifically,
   the `flyctl deploy` command reads from the local Docker
   config so a one-time `echo $TOKEN | docker login ghcr.io -u
   <owner> --password-stdin` is enough.

### Pull and run locally (sanity check)

```bash
docker pull ghcr.io/<owner>/<repo>:latest
docker run --rm -p 8080:8080 ghcr.io/<owner>/<repo>:latest
# open http://localhost:8080/

# or, behind a host-supplied port (the canonical PaaS pattern):
docker run --rm -p 9090:9090 -e PORT=9090 \
    ghcr.io/<owner>/<repo>:latest
```

The container binds to `0.0.0.0:8080` by default (or whatever
`$NICEGUI_PORT` / `$PORT` you set). Liveness is checked via
`GET /healthz` — a 200-only endpoint the app registers before
`ui.run` is called. The Docker `HEALTHCHECK` in the Dockerfile
greps that route.

```bash
# In another terminal, while the container runs:
docker exec <container> curl -s http://127.0.0.1:8080/healthz
# {"status":"ok","build_time":"...","git_sha":"...","case_loaded":"none"}
```

### Deploy to Fly.io (recommended free tier)

```bash
# one-time
curl -L https://fly.io/install.sh | sh
fly auth signup   # or `fly auth login` if you already have an account

# in a fresh checkout of the repo
fly launch --image ghcr.io/<owner>/<repo>:latest --no-deploy
# accept the defaults; Fly will create a `fly.toml` for you.

# point Fly at the GHCR image explicitly
fly deploy --image ghcr.io/<owner>/<repo>:latest
fly open   # opens https://<your-app>.fly.dev/
```

Fly auto-injects `$PORT=8080` and a `$STORAGE_SECRET` of its
own. The container's entrypoint forwards `$PORT → $NICEGUI_PORT`
and `app/main.py`'s `_resolve_storage_secret` picks up
`$STORAGE_SECRET` automatically, so Fly's secret manager
keeps sessions alive across container restarts. WebSockets
(used by the live data feed at 20 Hz) work out of the box.

### Deploy to Render.com

1. New → Web Service → *Deploy an existing image*.
2. Image URL: `ghcr.io/<owner>/<repo>:latest`.
3. Port: `8080`. Health check path: `/healthz` (the endpoint
   the app itself registers — see
   [app/main.py](app/main.py)). Render will poll it every 30 s
   and roll the service if it stops returning 200.
4. Add the GHCR credential as a *Secret* (Render reads it as
   `GITHUB_TOKEN` / `GITHUB_USERNAME`).
5. Click *Create Web Service*. Render pulls the image and
   starts it on `https://<your-app>.onrender.com/`.

### Deploy to Railway

1. New Project → *Deploy from Docker Image*.
2. Image: `ghcr.io/<owner>/<repo>:latest`.
3. In *Variables*, set `STORAGE_SECRET=<random 32+ chars>` so
   sessions survive container restarts. Railway auto-injects
   `$PORT` (the entrypoint maps it to `$NICEGUI_PORT` for you).
4. Click *Deploy*. Railway auto-assigns a public URL.

### What the Dockerfile actually does

A two-stage build that keeps the runtime image small:

* **Stage 1 (`builder`)** — `python:3.12-slim` with
  `build-essential` + `gcc`; installs every line of
  `requirements.txt` into `/install/` via
  `pip install --prefix=/install`.
* **Stage 2 (`runtime`)** — a *new* `python:3.12-slim` base
  with no compiler; copies the pre-built `site-packages`
  from stage 1, then copies the app source.
* **Build args** — `BUILD_TIME` and `GIT_SHA` are passed by
  the workflow at build time and become env vars in the
  image. The `/healthz` endpoint surfaces them so a
  `curl /healthz` from inside a running container tells you
  the exact commit that's serving traffic.
* **Entrypoint** — `python -m tools.docker_start` does two
  things: it copies the orchestrator's `$PORT` to
  `$NICEGUI_PORT` (so Fly / Render / Railway / Heroku all
  work without code changes), and it imports `app.main`,
  which itself calls `ui.run(...)` at module scope. Calling
  `ui.run()` again from the entrypoint would bind a *second*
  server on a different port and the original would never
  receive SIGTERM, so we deliberately import-and-block.
* **`/healthz`** — the app registers a tiny FastAPI route
  via `app.get('/healthz')` *before* `ui.run` is called.
  Returns 200 + a small JSON body (build time, git sha,
  case loaded). The `HEALTHCHECK` in the Dockerfile greps
  this — see
  [the official NiceGUI deploy docs](https://nicegui.io/documentation/section_configuration_deployment)
  for the canonical pattern.
* **Multi-arch** — the workflow builds for `linux/amd64`
  and `linux/arm64` in a single `docker buildx` invocation,
  so Apple-Silicon hosts (Render / Fly free tier VMs) can
  pull the right variant natively.

### Env-var reference

The app is configured entirely by environment variables, all
of which are documented in [app/main.py](app/main.py). Quick
reference:

| Env var                     | Default       | Set by orchestrator? | Purpose |
|-----------------------------|---------------|----------------------|---------|
| `NICEGUI_HOST`              | `0.0.0.0`     | no                   | bind host |
| `NICEGUI_PORT`              | `8080`        | set by entrypoint    | bind port |
| `PORT`                      | (none)        | yes (Fly/Render/Railway/Heroku) | copied to `NICEGUI_PORT` by entrypoint |
| `STORAGE_SECRET`            | random per boot | set in `fly secrets` / Render env / Railway vars | session cookie signing key |
| `ON_AIR_TOKEN`              | (none)        | no                   | enables NiceGUI Cloud tunnel; leave unset for "pure GitHub" deploy |
| `SHOW_WELCOME_MESSAGE`      | `true` outside containers, `false` in containers | no | controls the `NiceGUI is running on …` banner |
| `NICEGUI_LOG_LEVEL`         | `warning`     | no                   | uvicorn log level |
| `NICEGUI_STORAGE_PATH`      | `.nicegui/`   | no                   | per-user JSON storage directory |
| `NICEGUI_REDIS_URL`         | (none)        | no                   | optional Redis for shared storage across workers |
| `CHEMPLANT_BUILD_TIME`      | `unknown`     | set by Dockerfile `ARG` | shown in `/healthz` body |
| `CHEMPLANT_GIT_SHA`         | `unknown`     | set by Dockerfile `ARG` | shown in `/healthz` body |

### What you'll never need from NiceGUI

With the GHCR image in place:

* No `ON_AIR_TOKEN` required to run the app (the env var
  becomes a *no-op* when running outside the `on_air`
  tunnel).
* No external Cloud account of any kind — the source, the
  image, the CI, and (via Fly/Render/Railway) the running
  container are all on GitHub-owned or GitHub-adjacent
  infrastructure.
* No `STORAGE_SECRET` leak risk — `app.storage.user` still
  uses the in-process secret store, but the container
  defaults to a *random* `STORAGE_SECRET` per boot if the
  env var is unset, so a leaked image isn't a security
  incident. (Set `STORAGE_SECRET` to a fixed value in
  production if you want sessions to survive container
  restarts.)

## Performance & Stability (on_air)

Live data and UI feedback are optimized for the high-RTT
`on_air` cloud tunnel. Locally you won't notice; over the
tunnel these patterns eliminate the visible jank the previous
implementation suffered from.

### 1. Client-side live-state cache

Every engine tick (20 Hz), the server pushes a single
`ui.run_javascript` call with the full delta + formatted values
into a JS-side store:

```
window.__chemPlantState = {
  values: {"tic100_pv": "150.0", ...},
  raw:    {"tic100_pv": 150.0123, ...},
  tick:   87,
  simTime, status, mode
}
```

A `requestAnimationFrame` loop on the client writes the
formatted values into the SVG `<text>` elements. Net effect:
**one** round trip per tick, not N+M. The legacy per-child
`run_javascript` path is preserved as a fallback when the JS
store is absent (e.g. tests).

* Module: `app/ui/bridge_store.py`
* Client script: `app/static/js/chemplant_state.js`
* Hub integration: `app/hub/signal_hub.py:_tick` (the
  `dispatch(pl)` call after the per-child fan-out).

### 2. Per-browser persistence

A throttled (every 5th tick) mirror of the snapshot to
`app.storage.user['hub_snapshot:<case>']` means a page reload
re-paints the last-known values within ~200 ms — no zero
flash on the SVG/faceplate/modal.

`SignalHub.start()` re-reads the persisted snapshot and seeds
the in-memory snapshot with the keys the bridge hasn't
overwritten yet.

### 3. Sub-16 ms button feedback

Drawer items, the Runtime Manager toggle, and the Run/Stop/
Reset/Real-Time buttons all carry the `btn-feedback` CSS
class. The pressed state lights up via the browser's
`:active` pseudo-class plus a `pointerdown`/`pointerup` JS
listener — no Python round trip.

* Module: `app/ui/button_feedback.py`
* CSS: `app/static/css/button_feedback.css`

### 4. Skeleton section mounts

The four control-panel sections (Overview, P&ID, Performance
Monitoring, Data Logger) mount their heavy content (echart
panels, SVG renderer, data logger table) on the *next* tick
after the user clicks. The visible panel flips immediately and
shows a shimmer-animated skeleton in the section's shape, so
click-to-paint is sub-16 ms even when the section is heavy.

* Module: `app/ui/section_loader.py`
* Skeleton primitive: `app/ui/loading.py`
* CSS: `app/static/css/app_skeleton.css`

### 5. Eager Runtime Manager build

The Floating Runtime Manager dialog body, drag script, and
resize observer are constructed at page-load time (closed).
The first toggle is a pure visibility flip.

## Main Structure

```
app_root/
├── requirements.txt
├── cases/                       # ── engine: case-specific configs / sessions
│   ├── common/                  #   shared base classes, time utils
│   ├── sthr/                    #   STHR case config + STHRSimulationSession
│   └── biodiesel/               #   biodiesel case config + BiodieselSimulationSession
├── core/
│   └── appdb.py                 #   in-memory historian; no case-specific imports
├── engine/
│   └── runtime/                 #   SimulationEngine, clock, interfaces (case-agnostic)
├── gateway/
│   ├── bridge.py                #   Bridge facade
│   ├── bridge_class.py          #   Bridge implementation (case-agnostic; case_name argument)
│   ├── bridge_support.py        #   BridgeState, BridgeRecord, safe_float
│   └── config_registry.py       #   dynamic case discovery
├── models/                      # plant / controller / sensor / actuator models
├── scripts/
├── systems/
│   ├── builders/                # closed-loop builders per case
│   └── configs/                 # parameter sets per case
├── tests/                       # engine + hub + case tests
│   ├── engine/ clsys/ olsys/ biodiesel/ appdb/ examples/
│   └── hub/                     # parent–child hub unit + integration tests
└── app/                         # ── UI (NiceGUI)
    ├── main.py                  # `python -m app.main` entrypoint
    ├── config.py                # SVG display defaults
    ├── sthr_drawing.py          # STHR P&ID SVG construction
    ├── biodiesel_drawing.py     # biodiesel P&ID SVG construction
    ├── components/              # FaceplatePanel, PidNavbar, FloatingRuntimeManager, …
    ├── layouts/                 # page shells (header / drawer / footer)
    ├── pages/
    │   ├── home_page.py
    │   ├── control_panel_page.py        # /control-panel/<case> router
    │   ├── runtime_manager_page.py      # body used by FloatingRuntimeManager
    │   ├── _runtime_manager_helpers.py
    │   └── _svg_animation_helpers.py
    ├── hub/                              # ── parent + infrastructure
    │   ├── controller_registry.py        # ControllerSpec + ControllerRegistry (single source of truth)
    │   ├── signal_hub.py                 # SignalHub (parent), Subscriber, TickMeta
    │   ├── engine_control.py             # 1-line passthrough to bridge (run/stop/reset/…)
    │   ├── local_store.py                # LocalStore (pure-UI fallback)
    │   ├── input_focus_tracker.py        # guard so per-tick refresh doesn't clobber typing
    │   ├── data_logger.py                # full per-scope ui.log streamer + CSV/JSON export
    │   ├── perf_monitor.py               # echart-panel renderer (3 scope cards)
    │   └── children/
    │       ├── svg_child.py              # writes SVG <text> via one batched JS call
    │       ├── faceplate_child.py        # repaints FaceplatePanel each tick
    │       ├── modal_child.py            # HubStoreAdapter + open-modal refresh
    │       └── modals/                   # rewritten controller modals
    │           ├── placement.py          # MANUAL_ANCHORS + _SmartPlacementMixin
    │           ├── base.py               # ControllerModal (tunable)
    │           ├── readonly.py           # ReadOnlyControllerModal (indicator)
    │           ├── sthr.py               # 7 STHR subclasses
    │           └── biodiesel.py          # ValvePositionModal + 15 biodiesel subclasses
    └── pid/                              # ── per-case wiring for the hub
        ├── sthr/                         #   (STHR_REGISTRY + build_sthr_hub + render_sthr_pid_svg)
        │   ├── registry.py
        │   ├── hub_factory.py            #   owns _STHR_BRIDGE_REGISTRY + shutdown hook
        │   └── view.py
        └── biodiesel/                    #   parallel set for biodiesel
            ├── registry.py
            ├── hub_factory.py            #   owns _BIODIESEL_BRIDGE_REGISTRY + shutdown hook
            └── view.py
```

## Architecture — Parent–Child Broadcast Hub

```
              ENGINE (1× Bridge._records — single producer)
                 │
                 ▼  (drain ONCE per tick — SignalHub is the only caller)
       ┌────────────────────────────────────────────────────────────┐
       │              SignalHub  (PARENT)                           │
       │  - snapshot[modal_key] = float        (single source)      │
       │  - registry: ControllerRegistry       (single map)         │
       │  - subscribers: List[Subscriber]                           │
       │  - 1× ui.timer @ 50 ms → _tick():                          │
       │      drain → fold → delta_keys + snapshot → notify all     │
       │  - request_write(modal_key, value)  ← child push upstream  │
       │  - engine_control: EngineControl    ← passthrough to bridge│
       └────────────────────────────────────────────────────────────┘
              │              │              │              │
              ▼              ▼              ▼              ▼
         SvgChild       FaceplateChild   ModalChild   data_logger /
         on_tick(...)   on_tick(...)     on_tick(...)  perf_monitor
         + .control     + .control       + .control    (own ui.timer
                                                        reading bridge)
```

### Three control paths, separated by design

1. **Engine-level control** — Run / Stop / Reset / Real-Time /
   Mode global. Calls `hub.engine_control.<method>()`, which is a
   one-line passthrough to `bridge.start()` / `bridge.pause()` /
   `bridge.reset()` / `bridge.apply_runtime_configuration(...)`.
   Subscribers react via the next tick — buttons do NOT fan out
   themselves.
2. **Engine-side data writes** — SP / OP / Kc / tuning / per-loop
   mode. Calls `hub.request_write(modal_key, value)`. The hub
   resolves the engine tag via `ControllerRegistry`, writes once
   via `bridge.set_input_value`, and updates the snapshot. The
   engine's echo arrives on the next tick and reaches every child
   uniformly.
3. **Child-local control** — column toggle, signal selection,
   faceplate open/close, force-repaint. Lives on each child's
   `.control` object; never touches `hub` or `bridge`.

| Action                                       | Path                                                                         | Where in code                                                                            |
|----------------------------------------------|------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------|
| Run / Stop / Reset / Real-Time / Mode global | `hub.engine_control.run()` (etc.)                                            | [app/hub/engine_control.py](app/hub/engine_control.py)                                    |
| SP / OP / Kc / tuning / per-loop mode write  | `hub.request_write(modal_key, value)`                                        | [app/hub/signal_hub.py](app/hub/signal_hub.py)                                            |
| Open / close / size faceplate, register modal | `faceplate.control.open_for(tag)` / `.close()` / `.set_drawer(d)` / `.register_modal(m)` | [app/hub/children/faceplate_child.py](app/hub/children/faceplate_child.py) |
| Modal numeric edit commit (from drawer)      | `modal.control.commit(modal_key, value)` → `hub.request_write` (same channel) | [app/hub/children/modal_child.py](app/hub/children/modal_child.py)                       |
| Force SVG repaint (e.g. after seed reload)   | `svg.control.flush_all()`                                                    | [app/hub/children/svg_child.py](app/hub/children/svg_child.py)                            |

### Why parent–child?

The previous (now-deleted) layer had **three independent timers
each calling `bridge.drain_records()`** (200 ms in the live flusher,
50 ms in the data logger, 50 ms in the performance monitor).
`Queue.get_nowait` is destructive, so the consumers raced for
records. Per-tag metadata (engine_tag / modal_key / svg_id / unit /
decimals / range) was also duplicated in five modules — a drift
hazard.

The hub stack collapses both problems:

- **One drain point.** Only `SignalHub._tick` calls
  `bridge.drain_records()`. Children NEVER touch the queue.
  (`data_logger.py` and `perf_monitor.py` are the two exceptions —
  they're ports of the original renderers and own their own timers
  reading `bridge._step_log`, not `bridge.drain_records`.)
- **One canonical map.** `ControllerRegistry` (per case) replaces
  every per-tag map.
- **One master timer for the live UI.** A single `ui.timer` at
  50 ms runs in the hub. Children attach as subscribers and react
  in `on_tick`.

## SVG value update workflow (engine → SVG text)

How a number computed inside the engine ends up rendered in the
P&ID SVG, with the exact function name on every hop. Every
controller card in the SVG has a `<text>` element with id
`"<controller_id>-value"`
(see [app/components/sthr_component.py:1308](app/components/sthr_component.py#L1308)
and [app/components/sthr_component.py:760](app/components/sthr_component.py#L760));
the [SvgChild](app/hub/children/svg_child.py) targets that element
by id.

```
                    ┌────────────────────────────────────────────────┐
                    │           ENGINE (case-agnostic)               │
 cases.<case>.session.<Session>.step(external_inputs=…)              │
                    │   └─ produces last_inputs / last_states /      │
                    │      last_outputs (dicts keyed by engine tag,  │
                    │      e.g. 'STHR.T', 'TC-100.M', 'TV-100.M').   │
                    └───────────────────┬────────────────────────────┘
                                        │
                                        ▼
        gateway.bridge_class.Bridge._run_one_step(...)
            • calls session.step(...)
            • builds a BridgeRecord(kind='step', inputs=…,
              states=…, outputs=…, mode=…, time_min=…)
            • self._records.put(record)          (thread-safe queue)
                                        │
                                        ▼
        gateway.bridge_class.Bridge.drain_records(max_records)
            • drained by the hub poll, returns a list[BridgeRecord]
                                        │
                                        ▼  (every 50 ms, ui.timer in SignalHub)
        app.hub.signal_hub.SignalHub._tick
            ├─ self._bridge.drain_records(200)
            │     └─ for each record:
            │        SignalHub._apply_records(records)
            │          • for engine_tag, modal_key in registry.output_to_pv():
            │              outputs > states > inputs wins,
            │              folded into snapshot[modal_key]
            │          • input echo (input_field_to_override)
            │              fills modal_keys still missing
            │          • status_keys ← mode_name_to_code(record.mode)
            │          • derived_pairs copy values (e.g. fi102_pv ← fi101_pv)
            │
            └─ for child in subscribers: child.on_tick(delta_keys, snapshot, meta)
                                        │
                                        ▼
              ┌─────────────────────┬──────────────────────┐
              ▼                     ▼                      ▼
  SvgChild.on_tick         FaceplateChild.on_tick   ModalChild.on_tick
   • filter to keys with    • repaint bargraphs +    • iterate open
     svg_id                   numeric labels           dialogs
   • format via              • _sync_input_from_     • call modal.refresh
     registry.format()         store (guarded by       _modal_values
   • one batched              focus tracker)
     ui.run_javascript
                                        │
                                        ▼
                     SVG <text id="tic-100-value">  ← updated
                     SVG <text id="fi-100-value">   ← updated
                                     …
```

Per-case wiring (the only thing a new case must declare):

| What                                    | Where it lives                                                                        | Function / attribute                                          |
|-----------------------------------------|---------------------------------------------------------------------------------------|---------------------------------------------------------------|
| ControllerSpec list (1 per signal)      | [app/pid/&lt;case&gt;/registry.py](app/pid/sthr/registry.py)                          | `_SPECS` → `ControllerRegistry(_SPECS)`                       |
| Per-browser bridge + hub factory        | [app/pid/&lt;case&gt;/hub_factory.py](app/pid/sthr/hub_factory.py)                    | `build_<case>_hub()`                                          |
| Renders the P&ID SVG + wires modals     | [app/pid/&lt;case&gt;/view.py](app/pid/sthr/view.py)                                  | `render_<case>_pid_svg(hub)`                                  |
| Route registration                      | [app/pages/control_panel_page.py](app/pages/control_panel_page.py)                    | `_CASE_HANDLERS[<case>] = CaseHandlers(...)`                  |
| Tick cadence                            | [app/hub/signal_hub.py](app/hub/signal_hub.py)                                        | `SignalHub.__init__(..., tick_s=0.05)`                        |
| Post-reset snapshot reseed              | [app/hub/signal_hub.py](app/hub/signal_hub.py)                                        | `SignalHub.reset_snapshot_to_seed()`                          |
| Input-focus guard (don't clobber typing) | [app/hub/input_focus_tracker.py](app/hub/input_focus_tracker.py)                      | `attach_focus_tracker(field)` / `is_user_editing(field)`      |

### Performance notes

- The diff gate in `SignalHub._tick` emits a `delta_keys` set —
  children only re-render the keys that actually changed. The SVG
  child batches every delta into one `ui.run_javascript` call per
  tick (one DOM update pass per 50 ms tick, not one per controller).
- `output_to_pv()` resolution prefers `outputs` over `states` over
  `inputs`, so a dual-purpose tag (e.g. TIC-100's `op` which is
  both the controller output `TC-100.M` and the actuator input
  `TV-100.M`) always reflects the engine's most authoritative
  value. The registry orders the dual-purpose specs so the writable
  entry wins in the engine-tag index — mirrors the legacy
  "input override wins" rule.

## Adding a new case

1. Create the engine side:
   - `cases/<newcase>/config.py` (mirror the structure of
     `cases/sthr/config.py`).
   - `cases/<newcase>/session.py` (subclass `BaseSimulationSession`).
   - `systems/builders/<newcase>_builder.py`.
   - `systems/configs/<newcase>_config.py`.
2. Add the UI side:
   - `app/pid/<newcase>/registry.py` — declare every signal as a
     `ControllerSpec` and wrap them in a `ControllerRegistry`.
   - `app/pid/<newcase>/hub_factory.py` — per-browser bridge
     registry + `build_<newcase>_hub()` factory; install a
     shutdown hook for that case's bridges.
   - `app/pid/<newcase>/view.py` — render the P&ID SVG; wire
     every controller modal to a `HubStoreAdapter(hub)`.
   - If new modal types are needed (rare — STHR/biodiesel cover
     all known shapes), add them under
     `app/hub/children/modals/<newcase>.py`.
3. Register the case in
   `app/pages/control_panel_page.py` by adding a `<newcase>` entry
   to `_CASE_HANDLERS`.

The engine and `core/` stay untouched. Existing cases keep working
unchanged.

## Tests

```bash
# from app_root/
python -m pytest tests/hub/        # 36 hub unit + integration tests
python -m pytest tests/            # everything (engine + case + hub)
```

## Per-case invariants

| Invariant                                    | Mechanism                                                                 |
|----------------------------------------------|---------------------------------------------------------------------------|
| One bridge per browser per case              | `_<CASE>_BRIDGE_REGISTRY` dict in each `hub_factory.py`                   |
| No cross-case state                          | Each case has its own registry + shutdown hook + factory; nothing shared  |
| Shutdown hook                                | `app.on_shutdown(_shutdown_bridges)` at hub_factory module import         |
| One drain point per page                     | Only `SignalHub._tick` calls `bridge.drain_records()`                     |
| One canonical snapshot per page              | `SignalHub._snapshot` (lock-protected)                                    |
| Single source of truth for per-tag metadata  | `ControllerRegistry` in each case's `registry.py`                         |

## Notes

- `gateway/bridge_class.py` is the bridge implementation. It is
  case-agnostic — it accepts any `case_name` and dispatches via
  the case config registry.
- `core/appdb.py` no longer imports any specific case. Timeseries
  backend parameters are pushed by the bridge via
  `set_active_case_config()` on `bind_profile()`.
- `app/hub/local_store.py` is the pure-UI fallback. The
  hub-backed `HubStoreAdapter` (in `modal_child.py`) implements the
  same `get`/`set`/`all` interface so the modals don't care which
  store they're talking to.
- `app/hub/data_logger.py` and `app/hub/perf_monitor.py` run their
  own 50 ms `ui.timer` reading `bridge._step_log` and
  `bridge.drain_records()` respectively. They were ported from the
  legacy renderers and kept their existing behaviour for column
  picking, CSV/JSON export, and replay buffering.
- Known pre-existing test issues (not introduced by the
  hub refactor):
  - `tests/engine/test_sthr_mixed_modes.py` expects
    `"STHR.W" in off_in` but the builder returns
    `['STHR.F', 'STHR.Ti']`.
  - `tests/biodiesel/test_biodiesel_session.py` has two tests
    expecting off-mode input lists that the builder no longer
    returns.
  These are test-assertion / builder-behavior mismatches, not
  regressions.

## Known structural gaps

- **Biodiesel P&ID SVG** has placeholder elements for some indicator
  cards (auxiliary `tic_mv_flow`, `tic_coolant_temp`, `lic_mv_flow`
  registry entries map to engine tags but have no SVG card yet).
- **LI-100 (tank level)**: the STHR plant model has no level state
  (only T and Ts), so the level indicator stays at the SVG's baked
  value of 120 ft³ until a level state is added to the plant model.
