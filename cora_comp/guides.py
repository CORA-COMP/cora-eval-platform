"""The how-to copy for CORA-COMP's two submission pages.

Kept out of ``competition.py``, which is the seam wiring rather than prose. The shell
renders these; it knows nothing about instances.csv or our scripts. The toolkit pipeline
below stays in step with ``CoraCompetition.build_steps`` — the steps a submitter watches
on the detail page, under the same names.
"""
from comp_eval_platform.results import Guide

TOOL_SKELETON = "https://github.com/CORA-COMP/example_toolkit"
BENCHMARK_REPO = "https://github.com/CORA-COMP/benchmarks"

# A tool's results file for one instance: the verdict, plus any numbers it wants to
# report alongside it.
_RESULTS_FILE = """result,time_reachable,time_verification
verified,0.30,0.60"""

_INSTANCES_CSV = """benchmark;instance;repetition;params
interval;generateRandom-1d;100;{"dim": 1}
zonotope;matMul-500d;100;{"dim": 500}
zonotope;minkSum-1000d;100;{"dim": 1000}"""


def toolkit_guide() -> Guide:
    return Guide(
        intro="How a tool submission is installed and run. To submit one, or to look at "
              "submissions that already ran, use the submissions page.",
        pipeline=[
            {
                "title": "Create Submission",
                "details": [
                    "The submission is recorded with what you chose on the form: the repository "
                    "and commit, the Docker base image, and the benchmarks you run against. "
                    "Nothing runs on a worker yet, so this step passes immediately.",
                    "That record fixes everything the pipeline does afterwards, which is what makes "
                    "a run reproducible — the commit is resolved and stored even if you submitted a "
                    "branch rather than a hash.",
                ],
            },
            {
                "title": "Assign Worker",
                "details": [
                    "The task waits for a worker and attaches it — an AWS instance or a Docker "
                    "container, depending on how the deployment is configured. Every later step "
                    "reaches the worker over SSH either way.",
                    "This is the queueing stage you see before any repository work starts.",
                ],
            },
            {
                "title": "Install Tool",
                "details": [
                    "Your repository is cloned at the submitted commit into the base image you "
                    "named, and `install_tool.sh v1` runs to install the tool, its dependencies, "
                    "and to activate any licence.",
                    "Installs are retried rather than failed outright, since a network hiccup is "
                    "not a broken submission.",
                ],
            },
            {
                "title": "Run Benchmark",
                "details": [
                    "One step per selected benchmark, so a benchmark that fails does not take the "
                    "others with it. For each instance the worker runs `prepare_instance.sh v1 "
                    "<benchmark> <instance> <repetition> <params>` and then `run_instance.sh v1 "
                    "<benchmark> <instance> <repetition> <params> <result-file>` — every column of "
                    "the instance's `instances.csv` row, in file order, with the results file "
                    "appended.",
                    "The harness owns timing: it measures wall-clock time and enforces the "
                    "per-instance timeout (the `timeout` column in `instances.csv`, if the "
                    "benchmark set defines one; otherwise the run is uncapped). A nonzero exit from "
                    "`prepare_instance.sh` skips that instance.",
                    "Each instance's verdict and its measured time land in a `results.csv` you can "
                    "read on the submission page while it fills up.",
                ],
            },
            {
                "title": "Shutdown",
                "details": [
                    "The worker is terminated once every benchmark has run. The submission page "
                    "stays available afterwards, so the logs and results can be read later — but "
                    "the worker itself is gone.",
                ],
            },
        ],
        sections=[
            {
                "heading": "What Your Repository Must Contain",
                "blocks": [
                    {"type": "text", "text":
                        f"The [tool skeleton repository]({TOOL_SKELETON}) is the minimal layout the "
                        "submission system runs. Its scripts have their argument parsing in place "
                        "and `TODO`s where your logic goes, and they run end-to-end as-is (a 1 s "
                        "stand-in run that writes a valid `unknown` result), so you can use it as a "
                        "test tool before filling it in."},
                    {"type": "bullets", "items": [
                        "`install_tool.sh` — installs the tool, once per worker. Called as "
                        "`install_tool.sh v1`; the argument is the interface version.",
                        "`prepare_instance.sh` — called before each instance as `prepare_instance.sh "
                        "v1 <benchmark> <instance> <repetition> <params>`. A nonzero exit skips the "
                        "instance.",
                        "`run_instance.sh` — runs one instance as `run_instance.sh v1 <benchmark> "
                        "<instance> <repetition> <params> <result-file>` (`<result-file>` is always "
                        "the last argument) and writes its verdict to `<result-file>`.",
                    ]},
                    {"type": "note", "text":
                        "The arguments are the interface version followed by the instance's "
                        "`instances.csv` columns, in file order — so a column added to the catalog "
                        "arrives as a further argument, before `<result-file>`. `<params>` is a JSON "
                        "object; `<repetition>` is how often to repeat the operation within the run."},
                ],
            },
            {
                "heading": "Reporting Results",
                "blocks": [
                    {"type": "text", "text":
                        "`run_instance.sh` just writes its result into the result file it is handed "
                        "(its last argument) — a `result` column whose value is `verified`, "
                        "`falsified`, `unknown`, or `error`, as in the example below. Any further "
                        "columns you write are kept per instance alongside the verdict, so a tool "
                        "can report its own timing breakdown."},
                    {"type": "code", "code": _RESULTS_FILE},
                    {"type": "note", "text":
                        "The `time` a run is scored on is the harness wall-clock, not a "
                        "self-reported number — anything your tool reports rides along beside it."},
                ],
            },
        ],
    )


def benchmark_guide() -> Guide:
    return Guide(
        intro="How the benchmarks are provided. CORA-COMP uses one repository for the whole "
              "competition — not one per benchmark — with a single `instances.csv` over all of them.",
        pipeline=[
            {
                "title": "Create Submission",
                "details": [
                    "The submission is recorded from what you enter on the form: the benchmarks "
                    "repository and a commit hash. There is no per-benchmark name — one submission "
                    "covers the whole set. Nothing runs on a worker yet, so this step passes "
                    "immediately.",
                ],
            },
            {
                "title": "Assign Worker",
                "details": [
                    "The task waits for a worker and attaches it — an AWS instance or a Docker "
                    "container, depending on the deployment. Loading runs on a worker (so it can "
                    "later do more than read a file), reached over SSH like every other step.",
                ],
            },
            {
                "title": "Load Benchmarks",
                "details": [
                    "The worker clones the repository at the submitted commit and its "
                    "`instances.csv` is read back — the one file that lists every benchmark and "
                    "instance. The rows are fanned out into one benchmark per distinct `benchmark` "
                    "value, each owning its instances.",
                    "Loading is a full overwrite: benchmarks dropped from the CSV are removed and "
                    "the rest are replaced, so the set always mirrors the repository at that commit. "
                    "Each submission is its own entry on the overview.",
                ],
            },
            {
                "title": "Shutdown",
                "details": [
                    "The worker is released. The loaded benchmarks are now published — selectable "
                    "when a tool is submitted, and groupable into evaluation tracks by organizers.",
                ],
            },
        ],
        sections=[
            {
                "heading": "What Your Repository Must Contain",
                "blocks": [
                    {"type": "text", "text":
                        f"The [benchmarks repository]({BENCHMARK_REPO}) is what the loader reads. At "
                        "its core is `instances.csv`, one row per instance, with `benchmark` and "
                        "`instance` as the first two columns:"},
                    {"type": "code", "code": _INSTANCES_CSV},
                    {"type": "bullets", "items": [
                        "`benchmark` — groups instances into a benchmark, the unit a tool selects.",
                        "`instance` — the case within that benchmark.",
                        "`repetition` — how often the tool repeats the operation inside the "
                        "instance, so one measurement averages over repeats.",
                        "`params` — a JSON object with the operation's arguments.",
                        "`timeout` (optional column) — a per-instance wall-clock cap in seconds, "
                        "enforced by the harness. Omit the column to leave instances uncapped.",
                        "Every column is passed, in file order, to the tool's "
                        "`prepare_instance.sh` / `run_instance.sh`.",
                    ]},
                    {"type": "note", "text":
                        "The file is semicolon-separated, since `params` is JSON and contains "
                        "commas; fields are left unquoted, so no value may contain a semicolon. It "
                        "is generated from the benchmark/operation/dimension tables in "
                        "`scripts/generate_instances.py` rather than hand-edited."},
                ],
            },
        ],
    )
