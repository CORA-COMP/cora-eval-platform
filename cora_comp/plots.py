"""The data behind the results view: every measured instance, plus what to filter it by.

Everything is sent to the browser in one payload rather than re-queried per filter — the
catalog is a few hundred instances per tool, and the cactus plot has to recompute on every
selector change and on the prepare-time toggle. The arithmetic (baseline subtraction,
sorting, the cumulative sum) is therefore the page's, not ours; this module only decides
*which* rows exist and *how* they are labelled.

Facets come from the loaded ``instances.csv``, not from a hardcoded list, so a benchmark or
operation added to the catalog shows up in the selectors without a code change here.
"""
import json
from collections import OrderedDict

#: The dimensions the results view filters on. ``benchmark`` is the row's own column;
#: the rest are read out of its params JSON. Selecting "all" on the device facet is what
#: puts cpu and gpu measurements in one plot.
FACETS = [
    {"key": "benchmark", "label": "Benchmark"},
    {"key": "operation", "label": "Operation"},
    {"key": "device", "label": "Device"},
]

PARAMS_COLUMN = "params"
OPERATION_KEY = "operation"
DEVICE_KEY = "device"
PREPARE_TIME_KEY = "prepare_time"

#: Recognized in an instance name, for catalogs whose params predate the field.
DEVICE_NAMES = ("cpu", "gpu")


def facet_values(benchmark_name: str, instance_name: str, spec: dict) -> dict:
    """One instance's value for each facet. Older catalogs carry a fact only in the
    instance name (``matMul-500d-cpu``), so each facet falls back to reading it."""
    params = _params(spec)
    parts = (instance_name or "").split("-")
    device = params.get(DEVICE_KEY) or (parts[-1] if parts[-1] in DEVICE_NAMES else "")
    return {
        "benchmark": benchmark_name,
        "operation": str(params.get(OPERATION_KEY) or parts[0]),
        "device": str(device),
    }


def _params(spec: dict) -> dict:
    """The instance's params as a dict; anything unparseable is no params at all."""
    raw = (spec or {}).get(PARAMS_COLUMN)
    if not raw:
        return {}
    try:
        value = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _float_or_none(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def facet_options() -> list:
    """The selector options, taken from the loaded catalog: every value that occurs in
    any instance of any benchmark, sorted. The view prepends "all".

    The benchmark facet also carries ``groups``, so the selector shows the catalog's
    own split (test / sets / their batched twins) rather than one flat list.
    """
    from comp_eval_platform.core.models import Instance

    seen = {facet["key"]: set() for facet in FACETS}
    rows = Instance.objects.select_related("benchmark").values_list(
        "benchmark__name", "name", "spec",
    )
    for benchmark_name, instance_name, spec in rows:
        for key, value in facet_values(benchmark_name, instance_name, spec).items():
            if value:
                seen[key].add(value)
    options = [{**facet, "options": sorted(seen[facet["key"]])} for facet in FACETS]
    for facet in options:
        if facet["key"] == "benchmark":
            facet["groups"] = _benchmark_groups(facet["options"])
    return options


def _benchmark_groups(names) -> list:
    """``[{"label", "options"}]`` over the given benchmark names, in group order,
    skipping groups the catalog has nothing in."""
    from .category import GROUPS, group_for

    grouped = [
        {"label": label, "options": [n for n in names if group_for(n) == label]}
        for label in GROUPS
    ]
    return [g for g in grouped if g["options"]]


def measurements() -> list:
    """One row per measured instance: the verdict, the harness wall-clock, the untimed
    prepare, and the facet values to filter on.

    A tool that is re-run produces a second Result for the same instance; only the newest
    is kept, so a re-run replaces its predecessor instead of being plotted beside it.
    """
    from comp_eval_platform.core.models import Result

    latest = OrderedDict()
    results = (Result.objects
               .select_related("tool", "benchmark", "instance")
               .order_by("created_at"))
    for r in results:
        instance_name = r.instance.name if r.instance else ""
        if not instance_name:
            continue  # a benchmark-level aggregate row, not a measurement
        spec = r.instance.spec if r.instance else {}
        # Later rows overwrite earlier ones: the queryset is ordered oldest first.
        latest[(r.tool.name, r.benchmark.name, instance_name)] = {
            "tool": r.tool.name,
            "benchmark": r.benchmark.name,
            "instance": instance_name,
            "result": (r.result or "").strip().lower(),
            "time": _float_or_none(r.time),
            "prepare_time": _float_or_none((r.extra or {}).get(PREPARE_TIME_KEY)),
            "facets": facet_values(r.benchmark.name, instance_name, spec),
        }
    return list(latest.values())


def running_tools() -> list:
    """The tools with a run in flight — queued or executing. The page marks them live and
    polls while any is, so a run in progress draws itself instance by instance."""
    from comp_eval_platform.core.models import Task
    from comp_eval_platform.core.models.execution import TERMINAL_OUTCOMES

    names = (Task.objects
             .filter(tool__isnull=False)
             .exclude(outcome__in=TERMINAL_OUTCOMES)
             .values_list("tool__name", flat=True))
    return sorted(set(names))


def plot_payload() -> dict:
    rows = measurements()
    running = running_tools()
    return {
        "facets": facet_options(),
        # A tool that is running but has produced nothing yet still belongs in the list,
        # so the summary can show it as live rather than not at all.
        "tools": sorted({row["tool"] for row in rows} | set(running)),
        "running": running,
        "measurements": rows,
    }
