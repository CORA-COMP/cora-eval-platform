"""Loading the benchmarks from the central instances.csv."""
import uuid

import pytest
from django.core.exceptions import ValidationError

pytestmark = pytest.mark.django_db

# The shape of the real catalog (github.com/CORA-COMP/benchmarks): semicolon-separated,
# with an unquoted JSON `params` column.
BENCHMARKS_CSV = """benchmark;instance;repetition;params
interval;generateRandom-1d;100;{"dim": 1}
interval;matMul-1d;100;{"dim": 1}
interval;matMul-500d;100;{"dim": 500}
zonotope;generateRandom-1d;100;{"dim": 1}
zonotope;minkSum-1d;100;{"dim": 1}
zonotope;minkSum-500d;100;{"dim": 500}
zonotope;minkSum-1000d;100;{"dim": 1000}
"""


def _user():
    from comp_eval_platform.core.models import User

    return User.objects.create_user(email=f"{uuid.uuid4().hex[:8]}@x.test", password="pw", enabled=True)


def test_parse_groups_rows_by_benchmark():
    from cora_comp.benchmarks import group_by_benchmark, parse_instances_csv

    header, rows = parse_instances_csv(BENCHMARKS_CSV)
    assert header == ["benchmark", "instance", "repetition", "params"]
    assert len(rows) == 7
    groups = group_by_benchmark(rows)
    assert list(groups) == ["interval", "zonotope"]  # first-seen order preserved
    assert len(groups["interval"]) == 3
    assert [r["instance"] for r in groups["interval"]] == [
        "generateRandom-1d", "matMul-1d", "matMul-500d",
    ]


def test_parse_keeps_the_json_params_column_intact():
    """`params` is unquoted JSON in a semicolon-separated file: the commas inside it must
    not split the row, and the value must survive verbatim for the tool to json-parse."""
    import json

    from cora_comp.benchmarks import parse_instances_csv

    _, rows = parse_instances_csv(
        'benchmark;instance;repetition;params\n'
        'zonotope;matMul-2d;100;{"dim": 2, "seed": 7}\n'
    )
    assert rows[0]["params"] == '{"dim": 2, "seed": 7}'
    assert json.loads(rows[0]["params"]) == {"dim": 2, "seed": 7}


def test_parse_requires_benchmark_and_instance_columns():
    from cora_comp.benchmarks import parse_instances_csv

    with pytest.raises(ValidationError):
        parse_instances_csv("benchmark;foo\nzonotope;x\n")
    with pytest.raises(ValidationError):
        parse_instances_csv("")


def test_parse_rejects_ragged_rows():
    from cora_comp.benchmarks import parse_instances_csv

    with pytest.raises(ValidationError):
        parse_instances_csv("benchmark;instance\nzonotope;x;extra\n")


def test_load_assigns_the_display_group():
    """The group is derived from the benchmark's name, so the catalog alone decides it."""
    from cora_comp.benchmarks import load_benchmarks_from_csv

    csv_text = BENCHMARKS_CSV + 'zonotope-batched;minkSum-1d-b8;100;{"dim": 1}\ntest;startup-1d;1;{}\n'
    benchmarks = load_benchmarks_from_csv(
        repository="https://x/r", ref="abc123", owner=_user(), csv_text=csv_text,
    )
    assert {b.name: b.extra["group"] for b in benchmarks} == {
        "interval": "sets", "zonotope": "sets",
        "zonotope-batched": "sets-batched", "test": "test",
    }


def test_load_creates_benchmarks_and_ordered_instances():
    from comp_eval_platform.core.models import Instance

    from cora_comp.benchmarks import load_benchmarks_from_csv
    from cora_comp.category import CATEGORY_NAME

    benchmarks = load_benchmarks_from_csv(
        repository="https://github.com/CORA-COMP/benchmarks",
        ref="abc123", owner=_user(), csv_text=BENCHMARKS_CSV,
    )
    assert len(benchmarks) == 2
    by_name = {b.name: b for b in benchmarks}

    zonotope = by_name["zonotope"]
    assert zonotope.category.name == CATEGORY_NAME and zonotope.published is True
    assert zonotope.hash == "abc123"
    assert zonotope.repository.endswith("benchmarks")
    # Ordered header carried on the benchmark (jsonb-order-safe).
    assert zonotope.extra["columns"] == ["benchmark", "instance", "repetition", "params"]

    insts = list(Instance.objects.filter(benchmark=zonotope).order_by("order"))
    assert [i.name for i in insts] == [
        "generateRandom-1d", "minkSum-1d", "minkSum-500d", "minkSum-1000d",
    ]
    assert insts[0].spec == {"benchmark": "zonotope", "instance": "generateRandom-1d",
                             "repetition": "100", "params": '{"dim": 1}'}
    # Positional args the harness passes, reconstructed via the ordered header.
    assert [insts[0].spec[c] for c in zonotope.extra["columns"]] == [
        "zonotope", "generateRandom-1d", "100", '{"dim": 1}',
    ]


def test_timeout_column_is_optional():
    from comp_eval_platform.core.models import Instance

    from cora_comp.benchmarks import load_benchmarks_from_csv

    (bench,) = load_benchmarks_from_csv(repository="r", ref="h", owner=_user(),
                                        csv_text="benchmark;instance\nzonotope;y\n")
    assert Instance.objects.get(benchmark=bench).spec.get("timeout") is None
    assert bench.extra["columns"] == ["benchmark", "instance"]


def test_reload_replaces_instances_and_prunes_dropped_benchmarks():
    """Re-loading mirrors the CSV: instances are replaced and a dropped benchmark goes."""
    from comp_eval_platform.core.models import Benchmark, Instance

    from cora_comp.benchmarks import load_benchmarks_from_csv

    owner = _user()
    load_benchmarks_from_csv(
        repository="r", ref="v1", owner=owner,
        csv_text="benchmark;instance\nzonotope;a\nzonotope;b\ninterval;t1\n")
    assert set(Benchmark.objects.values_list("name", flat=True)) == {"zonotope", "interval"}

    load_benchmarks_from_csv(repository="r", ref="v2", owner=owner,
                             csv_text="benchmark;instance\nzonotope;a\n")
    assert set(Benchmark.objects.values_list("name", flat=True)) == {"zonotope"}
    zonotope = Benchmark.objects.get(name="zonotope")
    assert zonotope.hash == "v2"
    assert [i.name for i in Instance.objects.filter(benchmark=zonotope)] == ["a"]


def test_competition_rejects_a_foreign_category():
    from comp_eval_platform.competitions import get_competition

    with pytest.raises(ValidationError):
        get_competition().load_benchmarks(
            category_name="AINNCS", repository="r", ref="h", owner=_user(),
        )
