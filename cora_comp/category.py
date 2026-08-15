"""CORA-COMP's single category, and the groups its benchmarks fall into.

Core groups benchmarks by category and builds both submission forms around that
axis (``Competition.uses_categories``). CORA-COMP has exactly one category, so the
axis collapses to the constant below: every benchmark and every tool lands in it,
the tool interface carries no category argument, and the scoreboard has no category
column. Keeping the row (rather than switching the variant to core's "one benchmark
per submission" shape) is what lets one submission load a whole ``instances.csv``.

Within the category the catalog splits into groups — the interface's own overhead,
the set representations, and their batched twins. A group is a display axis only
(core's ``Benchmark.extra["group"]``), derived from the benchmark's name, so the
catalog alone decides it and no submitter types it.
"""

#: The one category every CORA-COMP benchmark and tool belongs to.
CATEGORY_NAME = "contSet"

#: The groups the category's benchmarks are shown in, in display order.
TEST_GROUP = "test"
SET_GROUP = "sets"
BATCHED_GROUP = "sets-batched"
GROUPS = [TEST_GROUP, SET_GROUP, BATCHED_GROUP]

#: Suffix that marks a benchmark as the batched twin of a set representation.
BATCHED_SUFFIX = "-batched"

#: Normalized result columns the UI shows for it (presentation hint). A tool may
#: self-report further columns; those ride along per instance as ``Result.extra``.
RESULT_FIELDS = ["result", "time"]


def ensure_category():
    """Get-or-create the single ``Category`` row, seeding its result columns. Idempotent."""
    from comp_eval_platform.core.models import Category

    category, _ = Category.objects.get_or_create(
        name=CATEGORY_NAME, defaults={"result_fields": list(RESULT_FIELDS)},
    )
    return category


def group_for(benchmark_name: str) -> str:
    """The group a benchmark is shown in, from its name."""
    if benchmark_name == TEST_GROUP:
        return TEST_GROUP
    return BATCHED_GROUP if benchmark_name.endswith(BATCHED_SUFFIX) else SET_GROUP


def group_order(benchmark_name: str) -> int:
    """Sort key placing a benchmark's group in display order."""
    return GROUPS.index(group_for(benchmark_name))
