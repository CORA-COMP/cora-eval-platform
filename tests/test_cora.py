"""CORA-COMP plugin: the six seams (ACTIVE_COMPETITION=cora)."""
import uuid

import pytest

pytestmark = pytest.mark.django_db


def _user():
    from comp_eval_platform.core.models import User

    return User.objects.create_user(email=f"{uuid.uuid4().hex[:8]}@x.test", password="pw", enabled=True)


def _category():
    from cora_comp.category import ensure_category

    return ensure_category()


def test_active_competition_is_cora():
    from comp_eval_platform.competitions import get_competition

    assert get_competition().name == "cora"


def test_validate_tool_requires_base_image():
    from django.core.exceptions import ValidationError

    from comp_eval_platform.competitions import get_competition
    from comp_eval_platform.core.models import Tool

    comp = get_competition()
    cat = _category()
    bad = Tool.objects.create(owner=_user(), category=cat, name="t", base_image="")
    with pytest.raises(ValidationError):
        comp.validate_submission(bad)
    ok = Tool.objects.create(owner=_user(), category=cat, name="t2", base_image="ubuntu:22.04")
    comp.validate_submission(ok)


def test_ensure_categories_seeds_the_single_category():
    """The submission forms call this so the category is selectable before any load."""
    from comp_eval_platform.competitions import get_competition
    from comp_eval_platform.core.models import Category

    from cora_comp.category import CATEGORY_NAME, RESULT_FIELDS

    assert not Category.objects.exists()
    get_competition().ensure_categories()
    get_competition().ensure_categories()  # idempotent
    assert list(Category.objects.values_list("name", flat=True)) == [CATEGORY_NAME]
    assert Category.objects.get(name=CATEGORY_NAME).result_fields == RESULT_FIELDS


def test_build_steps_graph():
    from comp_eval_platform.competitions import get_competition
    from comp_eval_platform.core.models import Benchmark, Task, Tool

    from cora_comp import kinds

    cat = _category()
    tool = Tool.objects.create(owner=_user(), category=cat, name="cora", base_image="cora:latest")
    Benchmark.objects.create(owner=_user(), category=cat, name="ACC", published=True)
    Benchmark.objects.create(owner=_user(), category=cat, name="Airplane", published=True)

    task = Task.objects.create(owner=tool.owner, tool=tool)
    get_competition().build_steps(task)

    assert list(task.step_set.order_by("order").values_list("kind", flat=True)) == [
        kinds.CREATE, "assign", kinds.INSTALL,
        kinds.RUN_BENCHMARK, kinds.RUN_BENCHMARK,
        "shutdown",
    ]


def test_build_steps_respects_selected_benchmarks():
    """A tool runs only the benchmarks it opted into (tool.extra['benchmarks'])."""
    from comp_eval_platform.competitions import get_competition
    from comp_eval_platform.core.models import Benchmark, Task, Tool

    from cora_comp import kinds

    cat = _category()
    acc = Benchmark.objects.create(owner=_user(), category=cat, name="ACC", published=True)
    Benchmark.objects.create(owner=_user(), category=cat, name="Airplane", published=True)
    tora = Benchmark.objects.create(owner=_user(), category=cat, name="TORA", published=True)

    tool = Tool.objects.create(owner=_user(), category=cat, name="cora", base_image="cora",
                               extra={"benchmarks": [str(acc.id), str(tora.id)]})
    task = Task.objects.create(owner=tool.owner, tool=tool)
    get_competition().build_steps(task)

    run_steps = task.step_set.filter(kind=kinds.RUN_BENCHMARK).order_by("order")
    assert [s.payload["benchmark_id"] for s in run_steps] == [str(acc.id), str(tora.id)]


def test_build_steps_benchmark_load():
    """A benchmark submission loads the whole catalog: no benchmark name, and a worker
    step carrying the repo/hash so the clone + CSV read can run there. With one category
    the step carries no category either — the loader ensures it."""
    from comp_eval_platform.competitions import get_competition
    from comp_eval_platform.core.models import Task

    from cora_comp import kinds

    task = Task.objects.create(owner=_user(), category=_category(),
                               extra={"repository": "https://x/r", "hash": "abc"})
    get_competition().build_steps(task)

    assert list(task.step_set.order_by("order").values_list("kind", flat=True)) == [
        kinds.CREATE, "assign", kinds.LOAD, "shutdown",
    ]
    load = task.step_set.get(kind=kinds.LOAD)
    assert load.payload == {"repository": "https://x/r", "hash": "abc"}


def test_load_handler_loads_benchmarks_from_node(monkeypatch):
    """The load step reads instances.csv back off the node and records the exact sha."""
    import comp_eval_platform.compute.shell as shell
    from comp_eval_platform.core.models import Benchmark, Task, TaskStep

    from cora_comp import kinds
    from cora_comp import steps as cora_steps

    task = Task.objects.create(owner=_user(), category=_category(),
                               extra={"repository": "r", "hash": ""})
    step = TaskStep.objects.create(task=task, kind=kinds.LOAD, order=0,
                                   payload={"repository": "r", "hash": ""})

    monkeypatch.setattr(cora_steps, "_node_ip", lambda t: "1.2.3.4")
    monkeypatch.setattr(shell, "node_exec",
                        lambda ip, cmd, **k: ("benchmark;instance;repetition;params\n"
                                              'zonotope;matMul-1d;100;{"dim": 1}\n')
                        if "cat " in cmd else "deadbeef")

    step.handler.on_marked_done()

    b = Benchmark.objects.get(name="zonotope")
    assert b.published and b.hash == "deadbeef"  # sha from the node, not the empty submitted hash


def test_run_handler_parses_and_stores_results(monkeypatch):
    """The run step reads the node's harness results.csv back and stores per-instance
    Results, keeping the tool's self-reported columns as extra."""
    import comp_eval_platform.compute.shell as shell
    from comp_eval_platform.core.models import Benchmark, Instance, Result, Task, TaskStep, Tool
    from comp_eval_platform.core.steps import StepHandler

    from cora_comp import kinds

    cat = _category()
    tool = Tool.objects.create(owner=_user(), category=cat, name="cora", base_image="cora")
    b = Benchmark.objects.create(owner=_user(), category=cat, name="ACC", published=True)
    Instance.objects.create(benchmark=b, name="acc_1", spec={}, order=0)
    task = Task.objects.create(owner=tool.owner, tool=tool)
    step = TaskStep.objects.create(task=task, kind=kinds.RUN_BENCHMARK, order=0,
                                   payload={"benchmark_id": str(b.id)})

    # collect_results (core) reads the node over self.node_ip; give it one.
    monkeypatch.setattr(StepHandler, "node_ip", property(lambda self: "1.2.3.4"))
    monkeypatch.setattr(shell, "node_exec", lambda ip, cmd, **k:
                        "benchmark,instance,time_verification,prepare_time,result,time\n"
                        "ACC,acc_1,0.42,0.01,finished,0.85\n")

    step.handler.on_marked_done()

    r = Result.objects.get(task=task, benchmark=b)
    assert r.result == "finished" and r.time == 0.85
    assert r.instance.name == "acc_1"
    assert r.extra.get("time_verification") == 0.42  # tool's own breakdown kept as extra

    # A well-formed run freezes a green stats summary tallying the verdicts.
    step.refresh_from_db()
    assert step.payload["severity"] == "success"
    assert step.payload["summary"]["verdicts"] == {"finished": 1, "unsupported": 0, "error": 0}


def test_parse_results_keeps_harness_time_and_tool_extras(tmp_path):
    """`time` is the harness wall-clock; every other unmodeled column rides along."""
    from comp_eval_platform.competitions import get_competition
    from comp_eval_platform.core.models import Task, Tool

    tool = Tool.objects.create(owner=_user(), category=_category(), name="t", base_image="i")
    task = Task.objects.create(owner=tool.owner, tool=tool)
    (tmp_path / "results.csv").write_text(
        "benchmark,instance,time_reachable,time_verification,prepare_time,result,time\n"
        "ACC,acc_1,0.3,0.6,0.05,finished,0.85\n"
    )
    (rec,) = get_competition().parse_results(task, str(tmp_path))
    assert rec.instance == "acc_1" and rec.result == "finished"
    assert rec.time == 0.85  # harness wall-clock, not a self-reported number
    assert rec.extra == {"time_reachable": 0.3, "time_verification": 0.6, "prepare_time": 0.05}


def test_parse_results_without_a_file_is_empty(tmp_path):
    from comp_eval_platform.competitions import get_competition
    from comp_eval_platform.core.models import Task, Tool

    tool = Tool.objects.create(owner=_user(), category=_category(), name="t", base_image="i")
    task = Task.objects.create(owner=tool.owner, tool=tool)
    assert get_competition().parse_results(task, str(tmp_path)) == []


def test_summarize_buckets_verdicts():
    from comp_eval_platform.results import ResultRecord

    from cora_comp.summary import summarize

    # The harness's own verdicts (timeout, prepare_failed) fall in with error, as does
    # anything outside the tool's three-value vocabulary.
    recs = [ResultRecord(instance=n, result=r, time=None) for n, r in
            [("a", "finished"), ("b", "unsupported"), ("c", "error"),
             ("d", "finished"), ("e", "timeout"), ("f", "prepare_failed")]]
    out = summarize(recs)
    assert out["severity"] == "success"
    assert out["summary"]["verdicts"] == {"finished": 2, "unsupported": 1, "error": 3}
    assert out["summary"]["order"] == ["finished", "unsupported", "error"]
    assert summarize([]) is None  # malformed/empty → no green summary


def test_score_ranks_tools_without_a_category_column():
    from comp_eval_platform.competitions import get_competition
    from comp_eval_platform.core.models import Benchmark, Result, Task, Tool, Track

    u = _user()
    cat = _category()
    tool = Tool.objects.create(owner=u, category=cat, name="cora", base_image="cora")
    bench = Benchmark.objects.create(owner=u, category=cat, name="ACC", published=True)
    task = Task.objects.create(owner=u, tool=tool)
    # Only `finished` counts; the time of every instance still adds up.
    for result, t in [("finished", 1.0), ("unsupported", 2.0), ("prepare_failed", 0.5)]:
        Result.objects.create(task=task, tool=tool, benchmark=bench, category=cat,
                              result=result, time=t)

    track = Track.objects.create(name="main")
    track.benchmarks.add(bench)

    board = get_competition().score(track)
    assert board.columns == ["tool", "finished", "time"]
    assert board.rows == [{"tool": "cora", "finished": 1, "time": 3.5}]


def test_overview_labels_benchmark_task_by_category():
    """A benchmark-set task shows its category (not a name) + repo on the overview."""
    from comp_eval_platform.core.models import Task
    from comp_eval_platform.core.serializers import TaskListSerializer

    from cora_comp.category import CATEGORY_NAME

    task = Task.objects.create(owner=_user(), category=_category(),
                               extra={"repository": "https://x/r"})
    data = TaskListSerializer(task).data
    assert data["name"] == CATEGORY_NAME
    assert data["repository"] == "https://x/r"


def test_guides_cover_both_submission_pages():
    """The shell asks for these two by name and falls back to neutral copy without them,
    which would quietly drop every CORA-specific instruction from the info pages."""
    from comp_eval_platform.competitions import get_competition

    guides = get_competition().presentation().guides
    assert set(guides) == {"toolkit", "benchmark"}
    for g in guides.values():
        assert g.intro and g.pipeline and g.sections
        assert all(s["title"] and s["details"] for s in g.pipeline)


def test_guides_link_the_github_repos():
    """The guides point submitters at the tool skeleton and the benchmark catalog on
    GitHub, not at zip assets."""
    from comp_eval_platform.competitions import get_competition

    prose = repr(get_competition().presentation().guides)
    assert "https://github.com/CORA-COMP/example_toolkit" in prose
    assert "https://github.com/CORA-COMP/benchmarks" in prose


def test_branding_assets_resolve():
    """The hero + favicon the presentation names must exist under assets_dir, or the
    shell renders a broken image."""
    from comp_eval_platform.competitions import get_competition

    comp = get_competition()
    branding = comp.presentation().branding
    for url in (branding.hero_image, branding.favicon):
        name = url.rsplit("/", 1)[-1]
        assert comp.asset_path(name), f"{name} missing from {comp.assets_dir()}"
    assert comp.asset_path("../secrets") is None  # no traversal out of the assets dir
