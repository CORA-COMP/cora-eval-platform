# Production deployment

Two machines: the **website** (Postgres, backend, frontend) and the **worker** (runs one
Docker container per submission). The live setup is `cpsvm5.cit.tum.de` (website, in
`/opt/cora-eval-platform`) and `tars.cps.cit.tum.de` (worker, in `~/cora-eval-platform`).

```
browser ──https──▶ host proxy (ARCH's Caddy) ──▶ web (Caddy: frontend, /api, /update) ──▶ backend
backend ──ssh -L──▶ worker:127.0.0.1:9001   worker service (starts job containers)
backend ──ssh -J worker──▶ job container 172.29.x.x   per-step scripts
job container ──ROOT_URL──▶ /update callbacks
```

The worker service has no authentication and controls Docker, so it only listens on the
worker's loopback; the website reaches it and the job network through SSH as a worker
account.

## Worker

```bash
git clone --recurse-submodules https://github.com/CORA-COMP/cora-eval-platform.git
cd cora-eval-platform
docker compose -p cora-comp -f deploy/production/compose.worker.yml up -d --build
```

Authorize the website's `id_worker.pub` (below) in the worker account's
`~/.ssh/authorized_keys`, limited to forwarding:

```
restrict,port-forwarding ssh-ed25519 AAAA… cora-comp-web
```

## Website

```bash
git clone --recurse-submodules https://github.com/CORA-COMP/cora-eval-platform.git /opt/cora-eval-platform
cd /opt/cora-eval-platform/deploy/production
cp .env.example .env                 # fill in secrets: openssl rand -hex 24
mkdir -m 700 ssh && cp ssh_config.example ssh/config
ssh-keygen -t ed25519 -N '' -f ssh/id_worker
ssh-keyscan tars.cps.cit.tum.de > ssh/known_hosts
cd ../.. && docker-compose -p cora-comp -f deploy/production/compose.web.yml up -d --build
```

The site is served on `WEB_PORT` (5175); until the public name resolves, set `ROOT_URL`
to `http://cpsvm5.cit.tum.de:5175`. For the public name, add a site to the host
proxy's Caddyfile (`/opt/arch/submission-system/docker/prod/caddyfile`) and reload it
(`docker exec arch-caddy caddy reload --config /etc/caddy/Caddyfile`):

```
cora.repeatability.cps.cit.tum.de {
    tls arch-comp@in.tum.de
    reverse_proxy cora-web:80
}
```

Then set `ROOT_URL` in `.env` to the public URL and recreate the backend.

The first account to sign up becomes the admin. In Admin → Settings, turn on the
scheduler and submissions. The Django admin is only on the website machine's loopback:
`ssh -L 8002:127.0.0.1:8002 cpsvm5.cit.tum.de`, then <http://localhost:8002/admin/>.

## Updating

```bash
git pull && git submodule update --init
docker-compose -p cora-comp -f deploy/production/compose.web.yml up -d --build   # website
docker compose -p cora-comp -f deploy/production/compose.worker.yml up -d --build  # worker
```

The website rebuilds the frontend on every `up`. Restart the backend (`restart backend`)
to pick up Python changes, and `web` to pick up a changed `Caddyfile`.
