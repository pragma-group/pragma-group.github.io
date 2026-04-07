# pragma-group.github.io

Static site for the [PRAGMA Group](https://github.com/pragma-group/main) —
Public Review and Advisory Group for Mailing Analysis.

The root of this site is a complete mirror of the
[WG21 (ISO C++ Standards Committee)](https://www.open-std.org/jtc1/sc22/wg21/)
website, browsable at
[pragma-group.github.io/jtc1/sc22/wg21/](https://pragma-group.github.io/jtc1/sc22/wg21/).

Production may also be served under the same nginx host as
[paperflow.org](https://paperflow.org/) (for example at `/pragma/`); see **Deployment** below.

---

## What is here

- **`jtc1/sc22/wg21/`** — Full WG21 paper archive (1989–present): HTML, PDF, PS,
  and supporting files. Links are rewritten to relative paths for offline browsing.
- **`icons/`**, **`pics/`** — Page-requisite assets (Apache directory icons, ISO/IEC logos).
- **`index.html`** — Redirects to the WG21 index page.

## How it is maintained

**Deploy:** [.github/workflows/deploy-rsync.yml](.github/workflows/deploy-rsync.yml) rsyncs the site to production when `main` changes (see **Deployment** above).

A [GitHub Actions workflow](.github/workflows/update-mirror.yml) triggered by
manual dispatch runs an incremental crawl of `www.open-std.org`, skips
already-published immutable papers, and pushes only the changed files.
Immutable papers (those under a dated `YYYY/` subdirectory or matching the
`p####r#` / `n####` naming pattern) are never re-fetched once downloaded.

The crawler and link-rewriter scripts live in
[`.github/workflows/assets/`](.github/workflows/assets/).
See the [script README](.github/workflows/assets/README.md) for full usage
and design documentation.

## Why this mirror exists

PRAGMA evaluates WG21 proposals against disclosed principles and publishes
advisory assessments each mailing cycle. The mirror provides a stable,
self-contained reference for the agentic analysis pipeline and ensures paper
content remains accessible independent of upstream availability.

All governance and process documents for the group are in
[pragma-group/main](https://github.com/pragma-group/main).

---

## Deployment

The static site is deployed with **rsync over SSH** to a directory on the production server (no `git` on the host). This repository uses the **same secret and variable names** as the Paperflow monorepo ([paperflow.org](https://paperflow.org/), tree `paperflow/`) so one set of credentials can be reused across repos on the same server.

### GitHub Actions

Workflow: [.github/workflows/deploy-rsync.yml](.github/workflows/deploy-rsync.yml).

**Triggers** (same sequencing as the former GitHub Pages workflow):

- **push** to `main`, with **`pragma/pragma-outputs.csv` ignored** — so a CSV-only push does not deploy here.
- **`workflow_run`** after a successful **Inject PRAGMA Column** run — covers the CSV-only path (inject commits HTML, then deploy runs).
- **`workflow_dispatch`** — run deploy from the Actions tab (CI-only; no local rsync script in this repo).

Automation uses the GitHub Actions **`production`** [Environment](https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment) so you can require manual approval before rsync if desired. Restrict deployment branches to **`main`** if you use that feature.

| Type | Name | Purpose |
|------|------|---------|
| Secret | `SSH_HOST` | Server hostname or IP |
| Secret | `SSH_USER` | SSH login (dedicated keypair for CI recommended) |
| Secret | `SSH_PRIVATE_KEY` | Private key (OpenSSH PEM), full `BEGIN`/`END` block |
| Variable | `DEPLOY_PATH` | Remote directory that is the **site root** for this mirror (see below) |

**`DEPLOY_PATH`:** Set this to the absolute path nginx serves for the public URL. For example, if the site is exposed at `https://paperflow.org/pragma/`, sync the repo root into a directory such as `/var/www/html/paperflow/site/pragma` and map that path in nginx (example below).

The workflow runs **`rsync -avz --checksum`** to `${DEPLOY_PATH}/` for the public site only: **`icons/`**, **`jtc1/`**, **`pics/`** (each with **`--delete`** on that subtree), and **`index.html`**. **`--checksum`** means unchanged content is skipped even if modification times differ; other repository paths (for example **`pragma/`**, **`.github/`**) are not deployed.

**After switching off GitHub Pages:** In this repository, open **Settings → Pages** and set the source to **None** (or disable Pages) so the old Pages deployment is not used.

### Server setup

1. **SSH** — Add the CI public key to `~/.ssh/authorized_keys` for `SSH_USER`.
2. **Directory** — The deploy workflow runs **`mkdir -p`** on `DEPLOY_PATH` before rsync so intermediate segments (e.g. **`site/pragma`**) are created if missing. Ensure `SSH_USER` can create that path under the parent and that the nginx user can read the deployed tree. For permission patterns (including avoiding `403` when ownership changes), see **`paperflow/doc/deploy-environments.md`** in the Paperflow monorepo (same host; sections 3–5).
3. **nginx** — The mirror uses **root-relative** URLs (`/jtc1/...`, `/pics/...`, etc.). Under `https://paperflow.org/pragma/`, the browser would otherwise request those paths at the **host root**, so nginx must **`sub_filter`** HTML/CSS responses to prefix `/pragma` on those links. **Binary files** (PDF, images, archives) are not filtered—only `text/html` and `text/css`.

Canonical vhost snippet for `paperflow.org` is kept in the Paperflow deployment tree as **`paperflow.nginx`** (same block as production); the copy below must stay in sync when you change filters:

```nginx
    location = /pragma {
        return 301 /pragma/;
    }

    location /pragma/ {
        alias /var/www/html/paperflow/site/pragma/;
        index index.html;
        autoindex off;
        gzip off;
        sub_filter_types text/html text/css;
        sub_filter_once off;
        sub_filter 'href="/jtc1/'  'href="/pragma/jtc1/';
        sub_filter 'src="/jtc1/'   'src="/pragma/jtc1/';
        sub_filter 'href="/pics/'  'href="/pragma/pics/';
        sub_filter 'src="/pics/'   'src="/pragma/pics/';
        sub_filter 'href="/icons/' 'href="/pragma/icons/';
        sub_filter 'src="/icons/'  'src="/pragma/icons/';
        sub_filter 'href="/JTC1/'  'href="/pragma/JTC1/';
        sub_filter 'src="/JTC1/'   'src="/pragma/JTC1/';
        sub_filter 'url(/jtc1/'  'url(/pragma/jtc1/';
        sub_filter 'url(/pics/'   'url(/pragma/pics/';
        sub_filter 'url(/icons/'  'url(/pragma/icons/';
        sub_filter 'url(/JTC1/'   'url(/pragma/JTC1/';
        sub_filter 'url("/jtc1/'  'url("/pragma/jtc1/';
        sub_filter 'url("/pics/'   'url("/pragma/pics/';
        sub_filter 'url("/icons/'  'url("/pragma/icons/';
        sub_filter 'url("/JTC1/'   'url("/pragma/JTC1/';
        # meta refresh: content="0; url=/jtc1/..." (must not match external ?url=/... except our prefixes)
        sub_filter 'url=/jtc1/'  'url=/pragma/jtc1/';
        sub_filter 'url=/pics/'  'url=/pragma/pics/';
        sub_filter 'url=/icons/' 'url=/pragma/icons/';
        sub_filter 'url=/JTC1/'  'url=/pragma/JTC1/';
        sub_filter 'URL=/jtc1/'  'URL=/pragma/jtc1/';
        sub_filter 'URL=/pics/'  'URL=/pragma/pics/';
        sub_filter 'URL=/icons/' 'URL=/pragma/icons/';
        sub_filter 'URL=/JTC1/'  'URL=/pragma/JTC1/';
    }
```

If `DEPLOY_PATH` differs, set `alias` to that path (trailing slash as shown). If new root-relative prefixes appear in mirrored HTML/CSS (including `meta http-equiv="refresh"` with `url=/…` in `content`), add matching `sub_filter` lines. **`gzip off`** in this block avoids subtle `sub_filter` + compression issues; retest before re-enabling gzip here.

**MIME:** nginx maps extensions via `mime.types`; if a rare type under `jtc1/sc22` downloads with the wrong `Content-Type`, add a `types { }` override in this `location` or extend the global map.

To deploy outside CI, use **Actions → Deploy (rsync) → Run workflow** or copy the `mkdir` / `rsync` commands from [.github/workflows/deploy-rsync.yml](.github/workflows/deploy-rsync.yml).
