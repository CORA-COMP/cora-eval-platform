"""The CORA-COMP variant: the six seams.

A tool defines a Docker base image; the engine clones the tool into it, runs
install/license, then runs each benchmark's instances via a per-instance script.
Benchmarks come from one central repository's ``instances.csv``, as in ARCH — but
everything here lives in a single category, so parsing and scoring are one code path
and the tool interface carries no category argument.
"""
import os

from django.core.exceptions import ValidationError

from comp_eval_platform.competitions import Competition
from comp_eval_platform.core.models.execution import SHUTDOWN_KIND
from comp_eval_platform.results import Branding, Landing, Presentation, Scoreboard

from . import kinds
from .guides import benchmark_guide, toolkit_guide
from .results import parse_results

#: The one verdict that counts when scoring a track. Everything else — ``unsupported``,
#: ``error``, and the harness's own ``timeout``/``prepare_failed`` — did not run.
FINISHED = "finished"


class CoraCompetition(Competition):
    name = "cora"
    display_name = "CORA-COMP"
    # A single category, but still core's category shape: it is what routes a benchmark
    # submission to the "one repo, many benchmarks" load path (see category.py).
    uses_categories = True

    # (1) Submission spec + validation ------------------------------------
    def validate_submission(self, submission) -> None:
        from comp_eval_platform.core.models import Tool

        if isinstance(submission, Tool):
            if not submission.base_image:
                raise ValidationError("A CORA-COMP tool must define a Docker base image.")
        else:  # Benchmark
            if not submission.instances.exists():
                raise ValidationError("A CORA-COMP benchmark must define at least one instance.")

    def ensure_categories(self) -> None:
        """Seed the single category so it is selectable on the submission forms before
        any load. Idempotent."""
        from .category import ensure_category

        ensure_category()

    def load_benchmarks(self, *, category_name, repository, ref, owner) -> list:
        """Fan the central ``instances.csv`` (at ``repository@ref``) into one Benchmark
        per distinct benchmark, each owning its instances. ``category_name`` is accepted
        for the core seam's signature and must be this competition's one category."""
        from .benchmarks import load_benchmarks_from_repo
        from .category import CATEGORY_NAME

        if category_name not in (None, "", CATEGORY_NAME):
            raise ValidationError(
                f"Unknown category {category_name!r}; CORA-COMP has only {CATEGORY_NAME!r}."
            )
        return load_benchmarks_from_repo(repository=repository, ref=ref, owner=owner)

    # (2) Step-graph builder ----------------------------------------------
    def build_steps(self, task) -> list:
        from comp_eval_platform.core.models import Benchmark, TaskStep

        order = 0

        def add(kind, *, run_as_root=True, **payload):
            nonlocal order
            step = TaskStep.objects.create(
                task=task, kind=kind, order=order, run_as_root=run_as_root, payload=payload,
            )
            order += 1
            return step

        steps = []
        if task.tool is not None:
            steps += [add(kinds.CREATE), add("assign"), add(kinds.INSTALL)]
            benchmarks = Benchmark.objects.filter(
                category=task.tool.category, published=True,
            )
            # A tool enters the subset of benchmarks it opted into
            # (tool.extra["benchmarks"] = list of ids); absent selection = enter all.
            selected = task.tool.extra.get("benchmarks")
            if selected:
                benchmarks = benchmarks.filter(id__in=selected)
            for b in benchmarks.order_by("name"):
                steps.append(add(kinds.RUN_BENCHMARK, benchmark_id=str(b.id)))
            steps.append(add(SHUTDOWN_KIND))
        else:
            # A benchmark submission loads the whole catalog from one central repo. The
            # clone + read happens on a worker (it may grow to do more than parse a CSV),
            # then LOAD fans instances.csv into benchmarks. The step carries no category:
            # there is only one, and the loader ensures it.
            extra = task.extra or {}
            steps += [add(kinds.CREATE), add("assign"),
                      add(kinds.LOAD, repository=extra.get("repository", ""),
                          hash=extra.get("hash", "")),
                      add(SHUTDOWN_KIND)]
        return steps

    # (3) Node scripts + I/O contract -------------------------------------
    def script_root(self) -> str:
        return os.path.join(os.path.dirname(__file__), "scripts")

    def assets_dir(self) -> str:
        return os.path.join(os.path.dirname(__file__), "assets")

    # (4) Result parsing → normalized records ------------------------------
    def parse_results(self, run, artifacts_dir: str) -> list:
        return parse_results(artifacts_dir)

    # (5) Scoring ----------------------------------------------------------
    def score(self, track) -> Scoreboard:
        """Per tool: instances finished, and total time over the track's benchmarks. With
        one category there is no category column to break the ranking down by."""
        from collections import defaultdict

        from comp_eval_platform.core.models import Result

        benchmark_ids = track.benchmarks.values_list("id", flat=True)
        agg = defaultdict(lambda: {"finished": 0, "time": 0.0})
        for r in Result.objects.filter(benchmark_id__in=benchmark_ids).select_related("tool"):
            row = agg[r.tool.name]
            row["tool"] = r.tool.name
            if (r.result or "").strip().lower() == FINISHED:
                row["finished"] += 1
            row["time"] += r.time or 0.0
        return Scoreboard(
            columns=["tool", "finished", "time"],
            rows=sorted(agg.values(), key=lambda x: (-x["finished"], x["time"])),
        )

    # (6) Presentation / export -------------------------------------------
    def presentation(self) -> Presentation:
        return Presentation(
            result_columns=["instance", "result", "time"],
            submission_fields=[{"name": "base_image", "type": "text"}],
            score_columns=["tool", "finished", "time"],
            branding=Branding(
                # Gradient's leading color, so all primary accents match the navbar.
                primary_color="#dc2626",
                # Red -> blue navbar gradient (both ends kept deep enough for legible
                # white nav text).
                navbar_gradient="linear-gradient(135deg, #dc2626 0%, #2563eb 100%)",
                # Outlined buttons pick up the gradient's trailing blue.
                accent_color="#2563eb",
                hero_image="/api/competition/assets/logo.svg",
                hero_max_width=200,  # near-square mark; a tighter cap than a wide wordmark needs
                # The PNG rasterization of favicon.svg (its source), since browser tabs
                # render a PNG favicon more reliably than an SVG one.
                favicon="/api/competition/assets/favicon.png",
            ),
            landing=Landing(
                tagline="CORA-COMP is a friendly competition to compare the performance of "
                        "different libraries on continuous set representation.",
                links=[
                    {"label": "CORA", "url": "https://tumcps.github.io/CORA/"},
                    {"label": "GitHub", "url": "https://github.com/CORA-COMP"},
                ],
                contacts=["tobias.ladner@tum.de"],
            ),
            guides={"toolkit": toolkit_guide(), "benchmark": benchmark_guide()},
        )
