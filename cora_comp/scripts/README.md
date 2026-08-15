# CORA-COMP node scripts

- `cora/` — backend-side SSH wrappers fired by the step handlers (`_ping("cora", …)`).
  Each SSHes into `ubuntu@<node>`, does its work, and POSTs back to
  `${ROOT_URL}/update/<task_id>/success|failure`.
  - `load_benchmark.sh` — clone the central benchmarks repo (its `instances.csv` is read
    back and fanned into benchmarks).
  - `run_benchmark.sh` — ship `harness.py`, clone the benchmarks repo, run the benchmark's
    instances, write `results_<benchmark_id>.csv`.
- `harness.py` — the node-side per-instance harness (stdlib). Loops a benchmark's instances,
  running the tool's `prepare_instance.sh` / `run_instance.sh` (`<version> <benchmark>
  <instance> …`), owning timing + the optional per-instance timeout, and assembling
  `results.csv`.

Installing a tool (`node/install_tool.sh`) and bootstrapping a node
(`docker/bootstrap_node.sh`) are generic, so they come from core.
