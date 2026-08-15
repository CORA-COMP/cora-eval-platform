"""Step kinds this variant contributes (core provides 'assign' and 'shutdown')."""

CREATE = "cora_create"
INSTALL = "cora_install"  # clone tool into its base image, run install + license
RUN_BENCHMARK = "run_benchmark"  # counted by Task.effective_timeout_hours
LOAD = "cora_load"  # clone the central benchmarks repo on the node, load its instances.csv
