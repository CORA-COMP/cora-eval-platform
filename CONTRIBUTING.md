# Contributing

This repo is the **CORA-COMP variant** of the
[core evaluation platform](https://github.com/TUMcps/core-eval-platform): the `cora_comp`
plugin app plus its deploy config. A tool defines a Docker base image; the engine clones
the tool in, installs it, then runs each benchmark's instances. All the heavy lifting lives
in core; this repo holds the CORA-specific seams, step handlers, and node scripts.

## Shape of the variant

- **Benchmarks come from one repository.** Its `instances.csv` lists every benchmark and
  instance; a submission names `(repository, hash)` and the loader fans the CSV into one
  `Benchmark` per distinct `benchmark` value (`cora_comp/benchmarks.py`). Re-loading is a
  full overwrite, so the catalog mirrors the repo at that commit.
- **There is a single category** (`cora_comp/category.py`). Core groups benchmarks by
  category and that grouping is what routes a benchmark submission to the "one repo, many
  benchmarks" path, so the row still exists — but nothing dispatches on it: result parsing
  is one code path, the scoreboard has no category column, and the tool scripts take no
  category argument. This is where the variant diverges from ARCH-COMP, which needs a
  per-category registry.
- **The node harness owns timing** (`cora_comp/scripts/harness.py`). A tool self-reports
  only its verdict; wall-clock time and the optional per-instance `timeout` are enforced by
  the harness.

## The core submodule

The core engine is vendored as a git submodule at `./core`, pinned to a specific commit for
reproducible dev and deploy. A recursive clone brings it along; if you already have a
checkout without it:

```bash
git submodule update --init
```

The compose stack mounts `./core` (backend) and `./core/frontend` (Vite), so a normal
`docker compose up --build` runs against the pinned core with hot reload.

### Updating the pinned core

Move the pin with the helper shipped in core, then commit the change:

```bash
core/scripts/bump-core.sh          # latest core main
core/scripts/bump-core.sh dev      # ...or a branch, tag, or commit
git commit -m "chore: bump core"   # records the new pin
```

When a change spans both repos, merge the core change first, then bump this repo's pin to it.

## Tests

```bash
docker run --rm -v "$PWD/core:/core" -v "$PWD:/cora" -w /cora python:3.11-slim \
  sh -c "pip install -q -e '/core[dev]' -e /cora && pytest"
```
