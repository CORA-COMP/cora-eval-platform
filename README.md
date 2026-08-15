# CORA-COMP

The submission and evaluation platform for **CORA-COMP**, the competition on reachability
analysis and formal verification of continuous and hybrid systems. Submit a tool or a
benchmark set; the platform provisions a worker, runs it, collects logs, and scores the
results. Built on the shared
[core evaluation platform](https://github.com/TUMcps/core-eval-platform).

## Requirements

- Docker + Docker Compose (Docker Desktop on macOS/Windows).
- Git.

## Getting started

```bash
git clone --recurse-submodules https://github.com/CORA-COMP/cora-eval-platform.git
cd cora-eval-platform && docker compose up --build
```

- Frontend: <http://localhost:5175>
- Public URL (optional): `docker compose logs cloudflared | grep trycloudflare`

The **first account you sign up becomes the admin**; later signups start disabled until an
admin enables them.

To try a submission:

- Benchmarks: <https://github.com/CORA-COMP/benchmarks> — the catalog, submitted as a whole
- Tool: <https://github.com/CORA-COMP/example_toolkit> — a runnable skeleton to start from

## Contributing

Developing the platform (tests, updating the core engine, architecture) is covered in
[CONTRIBUTING.md](CONTRIBUTING.md).
