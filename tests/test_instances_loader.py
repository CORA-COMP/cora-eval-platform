"""Loading the benchmarks from the central instances.csv."""
import uuid

import pytest
from django.core.exceptions import ValidationError

pytestmark = pytest.mark.django_db

BENCHMARKS_CSV = """benchmark,instance,timeout
Unicycle,reach,300
ACC,safe-distance,300
TORA,remain,300
TORA,reach-tanh,300
TORA,reach-sigmoid,300
Airplane,continuous,600
VCAS,worst-19.5,300
VCAS,worst-22.5,300
"""


def _user():
    from comp_eval_platform.core.models import User

    return User.objects.create_user(email=f"{uuid.uuid4().hex[:8]}@x.test", password="pw", enabled=True)


def test_parse_groups_rows_by_benchmark():
    from cora_comp.benchmarks import group_by_benchmark, parse_instances_csv

    header, rows = parse_instances_csv(BENCHMARKS_CSV)
    assert header == ["benchmark", "instance", "timeout"]
    assert len(rows) == 8
    groups = group_by_benchmark(rows)
    assert len(groups) == 5
    assert len(groups["TORA"]) == 3
    assert list(groups)[0] == "Unicycle"  # first-seen order preserved
    assert [r["instance"] for r in groups["TORA"]] == ["remain", "reach-tanh", "reach-sigmoid"]


def test_parse_requires_benchmark_and_instance_columns():
    from cora_comp.benchmarks import parse_instances_csv

    with pytest.raises(ValidationError):
        parse_instances_csv("benchmark,foo\nACC,x\n")
    with pytest.raises(ValidationError):
        parse_instances_csv("")


def test_parse_rejects_ragged_rows():
    from cora_comp.benchmarks import parse_instances_csv

    with pytest.raises(ValidationError):
        parse_instances_csv("benchmark,instance\nACC,x,extra\n")


def test_load_creates_benchmarks_and_ordered_instances():
    from comp_eval_platform.core.models import Instance

    from cora_comp.benchmarks import load_benchmarks_from_csv
    from cora_comp.category import CATEGORY_NAME

    benchmarks = load_benchmarks_from_csv(
        repository="https://github.com/CORA-COMP/example_benchmark",
        ref="abc123", owner=_user(), csv_text=BENCHMARKS_CSV,
    )
    assert len(benchmarks) == 5
    by_name = {b.name: b for b in benchmarks}

    tora = by_name["TORA"]
    assert tora.category.name == CATEGORY_NAME and tora.published is True
    assert tora.hash == "abc123"
    assert tora.repository.endswith("example_benchmark")
    # Ordered header carried on the benchmark (jsonb-order-safe).
    assert tora.extra["columns"] == ["benchmark", "instance", "timeout"]

    insts = list(Instance.objects.filter(benchmark=tora).order_by("order"))
    assert [i.name for i in insts] == ["remain", "reach-tanh", "reach-sigmoid"]
    assert insts[0].spec == {"benchmark": "TORA", "instance": "remain", "timeout": "300"}
    # Positional args the harness passes, reconstructed via the ordered header.
    assert [insts[0].spec[c] for c in tora.extra["columns"]] == ["TORA", "remain", "300"]


def test_timeout_column_is_optional():
    from comp_eval_platform.core.models import Instance

    from cora_comp.benchmarks import load_benchmarks_from_csv

    (bench,) = load_benchmarks_from_csv(repository="r", ref="h", owner=_user(),
                                        csv_text="benchmark,instance\nX,y\n")
    assert Instance.objects.get(benchmark=bench).spec.get("timeout") is None
    assert bench.extra["columns"] == ["benchmark", "instance"]


def test_reload_replaces_instances_and_prunes_dropped_benchmarks():
    """Re-loading mirrors the CSV: instances are replaced and a dropped benchmark goes."""
    from comp_eval_platform.core.models import Benchmark, Instance

    from cora_comp.benchmarks import load_benchmarks_from_csv

    owner = _user()
    load_benchmarks_from_csv(repository="r", ref="v1", owner=owner,
                             csv_text="benchmark,instance\nACC,a\nACC,b\nTORA,t1\n")
    assert set(Benchmark.objects.values_list("name", flat=True)) == {"ACC", "TORA"}

    load_benchmarks_from_csv(repository="r", ref="v2", owner=owner,
                             csv_text="benchmark,instance\nACC,a\n")
    assert set(Benchmark.objects.values_list("name", flat=True)) == {"ACC"}
    acc = Benchmark.objects.get(name="ACC")
    assert acc.hash == "v2"
    assert [i.name for i in Instance.objects.filter(benchmark=acc)] == ["a"]


def test_competition_rejects_a_foreign_category():
    from comp_eval_platform.competitions import get_competition

    with pytest.raises(ValidationError):
        get_competition().load_benchmarks(
            category_name="AINNCS", repository="r", ref="h", owner=_user(),
        )
