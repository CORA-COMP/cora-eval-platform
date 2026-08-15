"""CORA-COMP's single category.

Core groups benchmarks by category and builds both submission forms around that
axis (``Competition.uses_categories``). CORA-COMP has exactly one category, so the
axis collapses to the constant below: every benchmark and every tool lands in it,
the tool interface carries no category argument, and the scoreboard has no category
column. Keeping the row (rather than switching the variant to core's "one benchmark
per submission" shape) is what lets one submission load a whole ``instances.csv``.
"""

#: The one category every CORA-COMP benchmark and tool belongs to.
CATEGORY_NAME = "CORA"

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
