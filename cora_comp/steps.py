"""CORA-COMP step handlers: fire a node script, the node curls back
``/update/<task_id>/…``, and the handler reads the artifacts off the node when the
step is marked done."""
import re

from comp_eval_platform.compute.shell import _ping
from comp_eval_platform.core.steps import StepHandler, register_step_handler

from . import kinds

#: Tool-interface version passed as the first arg to a tool's scripts. A tool may pin
#: one via ``tool.extra["version"]``; else the current default.
INTERFACE_VERSION = "v1"

#: Subdirectory of ``scripts/`` holding this variant's node wrappers.
SCRIPT_DIR = "cora"

#: What a name and a value in ``tool.extra["env"]`` may look like. The exports are pasted
#: into the script generated on the node, so only inert characters get through.
_ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_ENV_VALUE = re.compile(r"[A-Za-z0-9_.:,/=+-]*\Z")


def _node_ip(task):
    node = task.node
    return node.ip if node is not None else None


def _version(tool) -> str:
    return ((tool.extra if tool else {}) or {}).get("version") or INTERFACE_VERSION


def _tool_env(tool) -> str:
    """``tool.extra["env"]`` as shell exports for the tool's per-instance scripts.

    The seam for entering one tool twice in configurations it defines itself — which
    knob and what it means are the tool's business — as two catalog entries whose results
    sit side by side instead of overwriting each other. Anything that is not a plain
    name/value pair is dropped rather than escaped.
    """
    env = ((tool.extra if tool else {}) or {}).get("env") or {}
    return " ".join(f"export {k}={v};" for k, v in sorted(env.items())
                    if _ENV_NAME.match(str(k)) and _ENV_VALUE.match(str(v)))


@register_step_handler
class CoraCreateHandler(StepHandler):
    kind = kinds.CREATE

    def execute(self):
        self.task.step_succeeded(check_status=False)

    def status_check(self):
        return


@register_step_handler
class CoraInstallHandler(StepHandler):
    """Clone the tool onto the node and run its ``install_tool.sh <version>``."""

    kind = kinds.INSTALL
    node_log_path = "logs/install.log"  # install_tool.sh tees the run here

    def execute(self):
        ip = _node_ip(self.task)
        if ip is None:
            self.task.step_failed(check_status=False)
            return
        tool = self.task.tool
        # Generic install (clone tool + run its install_tool.sh) is a core script; the
        # tool is cloned to /home/ubuntu/tool, where run_benchmark.sh looks for it.
        _ping("node", "install_tool.sh", {
            "benchmark_ip": ip,
            "task_id": str(self.task.id),
            "repository": tool.repository,
            "hash": tool.hash or "",
            "script_dir": tool.script_dir or ".",
            "version": _version(tool),
            "run_as_root": str(self.step.run_as_root).lower(),
            "tool_dir": "tool",
        })

    def retry_until_success(self) -> bool:
        return True  # installs are flaky (network); retry rather than fail the task


@register_step_handler
class CoraLoadHandler(StepHandler):
    """Load the benchmarks from the central repo. The node clones the repo at the
    submitted ref (room to grow into more than a CSV read); on completion we pull its
    ``instances.csv`` back and fan it into benchmarks."""

    kind = kinds.LOAD
    node_log_path = "logs/load.log"  # load_benchmark.sh tees the clone here

    def execute(self):
        ip = _node_ip(self.task)
        if ip is None:
            self.task.step_failed(check_status=False)
            return
        _ping(SCRIPT_DIR, "load_benchmark.sh", {
            "benchmark_ip": ip,
            "task_id": str(self.task.id),
            "repository": self.step.payload.get("repository", ""),
            "hash": self.step.payload.get("hash", ""),
        })

    def retry_until_success(self) -> bool:
        return True  # clones are flaky (network); retry rather than fail the task

    def on_marked_done(self):
        """Read the cloned ``instances.csv`` off the node and load it. The node is still
        up (shutdown runs next). Records the exact commit for reproducibility when the
        submission gave no hash."""
        from comp_eval_platform.compute.shell import node_exec

        from .benchmarks import CLONE_DIR, INSTANCES_FILE, load_benchmarks_from_csv

        ip = _node_ip(self.task)
        if ip is None:
            return
        csv_text = node_exec(ip, f"cat {CLONE_DIR}/{INSTANCES_FILE} 2>/dev/null")
        if not csv_text.strip():
            self._append_log(f"no {INSTANCES_FILE} found on the node; nothing loaded")
            return
        sha = node_exec(ip, f"git -C {CLONE_DIR} rev-parse HEAD 2>/dev/null").strip()
        benchmarks = load_benchmarks_from_csv(
            repository=self.step.payload.get("repository", ""),
            ref=sha or self.step.payload.get("hash", ""), owner=self.task.owner,
            csv_text=csv_text,
        )
        self._append_log(f"loaded {len(benchmarks)} benchmark(s)")

    def _append_log(self, line: str):
        self.step.set_log(((self.step.logs or "") + f"\n[load] {line}").strip())


@register_step_handler
class CoraRunBenchmarkHandler(StepHandler):
    """Run one benchmark's instances with the installed tool. The node-side harness loops
    the benchmark's instances (prepare/run_instance, timing each), writing a results.csv
    keyed by benchmark id (benchmark names may have spaces). On completion the results
    are read back, parsed, and stored."""

    kind = kinds.RUN_BENCHMARK

    def _benchmark(self):
        from comp_eval_platform.core.models import Benchmark

        return Benchmark.objects.filter(id=self.step.payload.get("benchmark_id")).first()

    @property
    def node_log_path(self):
        """run_benchmark.sh tees each benchmark's run to its own log (keyed by id)."""
        b = self._benchmark()
        return f"logs/run_{b.id}.log" if b else None

    def execute(self):
        ip = _node_ip(self.task)
        if ip is None:
            self.task.step_failed(check_status=False)
            return
        b = self._benchmark()
        if b is None:
            self.task.step_succeeded(check_status=False)
            return
        tool = self.task.tool
        _ping(SCRIPT_DIR, "run_benchmark.sh", {
            "benchmark_ip": ip,
            "task_id": str(self.task.id),
            "benchmark_id": str(b.id),
            "benchmark_name": b.name,
            "version": _version(tool),
            "script_dir": (tool.script_dir if tool else ".") or ".",
            "repository": b.repository,
            "hash": b.hash or "",
            "tool_env": _tool_env(tool),
        })

    def while_active(self):
        """Stream the node log + partial results so the UI shows rows and a processed
        count as instances land (the harness writes a header row)."""
        super().while_active()
        b = self._benchmark()
        if b is not None:
            self.refresh_run_progress(f"/home/ubuntu/logs/results_{b.id}.csv", b, has_header=True)

    def can_abort_benchmark(self) -> bool:
        return True

    def _kill_run(self):
        """Stop the node-side run tree. run_benchmark.sh records the tmux pane's process
        group; a SIGTERM to it brings down the pane and the harness, and harness.py's own
        handler reaps the instance it was running (a detached group of its own), so nothing
        keeps burning CPU while the next benchmark runs."""
        from comp_eval_platform.compute.shell import node_exec

        ip = _node_ip(self.task)
        b = self._benchmark()
        if ip is None or b is None:
            return
        node_exec(ip, f"kill -TERM -- -$(cat /home/ubuntu/run_{b.id}.pgid) 2>/dev/null; "
                      f"tmux kill-session -t run_{b.id} 2>/dev/null; true")

    def abort_benchmark(self):
        """Stop this benchmark and move on to the next, recording it as aborted (its
        partial results are finalized first)."""
        self._kill_run()
        self.task.step_aborted()

    def on_marked_done(self):
        """Fetch the node's results.csv, parse it, and persist Result rows."""
        import shutil

        from comp_eval_platform.competitions import get_competition
        from comp_eval_platform.core.models import Instance, Result

        b = self._benchmark()
        if b is None:
            return
        # Result collection (fetch results.csv → temp dir) is generic core behavior.
        artifacts = self.collect_results(f"/home/ubuntu/logs/results_{b.id}.csv")
        if artifacts is None:
            return
        try:
            records = get_competition().parse_results(self.task, artifacts)
            instances = {i.name: i for i in Instance.objects.filter(benchmark=b)}
            Result.store(self.task, self.task.tool, b, b.category, records,
                         instances_by_name=instances)
            self._freeze_summary(records)
        finally:
            shutil.rmtree(artifacts, ignore_errors=True)

    def _freeze_summary(self, records):
        """Tally the run's verdicts onto the step so the details page shows a green
        stats overview (there is no counterexample validator yet)."""
        from .summary import summarize

        summary = summarize(records)
        if not summary:
            return
        self.merge_payload(**summary)
