# Fly.io Deployment Guide

This guide walks you through deploying ChemPlant Dynamics to [Fly.io](https://fly.io) using the pre-built container image from GitHub Container Registry (GHCR).

## Why Fly.io?

- **Free tier**: 1 shared-cpu VM + 256 MB RAM, stays up 24/7
- **WebSocket support**: Works out of the box for the live 20 Hz data feed
- **Automatic HTTPS**: TLS certificate provisioned automatically
- **Global edge**: Runs on servers close to your users (recommended: `sin` for SE Asia)

---

## Prerequisites

1. **GitHub repository is set up** with:
   - GitHub Actions workflows pushed (`.github/workflows/deploy_fly.yml`)
   - Docker image built and pushed to GHCR (`docker-publish.yml` succeeded)

2. **Fly.io account**: Sign up at https://fly.io (free tier available)

---

## One-Time Setup

### Step 1: Install flyctl

**macOS / Linux:**
```bash
curl -L https://fly.io/install.sh | sh
```

**Windows:**
```powershell
iwr https://get.fly.io/psh | iex
```

### Step 2: Login to Fly.io

```bash
fly auth login
```

### Step 3: Create the app (do NOT deploy yet)

```bash
# From the project root directory:
fly launch --image ghcr.io/mhfzlhkl/chemplant-dynamics:latest --no-deploy
```

- Choose a name or accept the generated one (e.g., `chemplant-dynamics`)
- Select a region (recommended: `sin` for Singapore / SE Asia)
- Say **NO** to creating a Postgres database
- Say **NO** to creating an Upstash Redis database
- Say **NO** to deploying immediately

This creates a `fly.toml` in your project root.

### Step 4: Set the required secrets

```bash
# Session cookie signing key (required for storage to survive restarts)
fly secrets set STORAGE_SECRET=$(openssl rand -hex 32)
```

### Step 5: Create a Fly deploy token for GitHub Actions

```bash
fly tokens create deploy -n "GitHub Actions"
```

Copy the token output.

### Step 6: Add the token to GitHub

1. Open your repository on GitHub
2. Go to **Settings → Secrets and variables → Actions**
3. Click **New repository secret**
4. Name: `FLY_API_TOKEN`
5. Value: paste the token from Step 5

---

## Deploy

### Option A: Manual Deploy (one-time or testing)

```bash
fly deploy --image ghcr.io/mhfzlhkl/chemplant-dynamics:latest
```

### Option B: Automatic Deploy via GitHub Actions

After setting up the `FLY_API_TOKEN` secret, every push to `main` will automatically deploy the latest image to Fly.io.

Trigger it manually:
- Go to **Actions → Deploy to Fly.io → Run workflow**

---

## Verify Deployment

```bash
# Check app status
fly status

# Check logs
fly logs

# Open the app in browser
fly open
```

The app will be available at `https://<your-app-name>.fly.dev`.

---

## Health Check

The container exposes `/healthz` which Fly.io pings every 30 seconds. If the app becomes unhealthy, Fly automatically restarts it.

Test manually:
```bash
curl https://<your-app-name>.fly.dev/healthz
```

Expected response:
```json
{"status":"ok","build_time":"...","git_sha":"...","case_loaded":"none"}
```

---

## Update / Re-deploy

After pushing new code to `main`:

1. GitHub Actions rebuilds the Docker image (`docker-publish.yml`)
2. GitHub Actions deploys to Fly.io (`deploy_fly.yml`)

Or manually:
```bash
fly deploy --image ghcr.io/mhfzlhkl/chemplant-dynamics:latest
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `Image not found` | Wait for `docker-publish` workflow to complete on GitHub Actions |
| `Cannot connect to app` | Check `fly status` and `fly logs` |
| `Session resets on restart` | Ensure `STORAGE_SECRET` is set via `fly secrets` |
| `Out of memory` | Scale memory: `fly scale memory 512` |
| `App sleeps after inactivity` | Free tier VMs may be stopped when idle; `fly scale count 1` keeps one running |

---

## Free Tier Limits

- **1 shared-cpu VM**
- **256 MB RAM**
- **3 GB persistent storage**
- **160 GB outbound bandwidth/month**

If you need more, upgrade via `fly scale` or the Fly dashboard.

---

## Connecting GitHub Pages to Fly.io

The static landing page on GitHub Pages should link to the live control panel on Fly.io:

1. Set the `ON_AIR_PROD_URL` repository variable:
   ```
   https://<your-app-name>.fly.dev
   ```

2. This is used by `tools/export_static.py` to rewrite the case-card links in `docs/index.html`.

---

## Useful Commands

```bash
# View app info
fly info

# View releases
fly releases

# Restart app
fly restart

# Destroy app (careful!)
fly destroy chemplant-dynamics

# Scale up
fly scale count 1
fly scale memory 512
```
