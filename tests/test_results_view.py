"""The results view: what the page gets handed, and who may ask for it."""
import json
import uuid

import pytest

pytestmark = pytest.mark.django_db


def _fixture():
    """A tiny catalog with two benchmarks and one tool that ran every instance."""
    from comp_eval_platform.core.models import (
        Benchmark, Category, Instance, Result, Task, Tool, User,
    )

    user = User.objects.create_user(
        email=f"{uuid.uuid4().hex[:8]}@x.test", password="pw", enabled=True)
    category = Category.objects.create(name="CORA")
    tool = Tool.objects.create(category=category, name="CORA", base_image="img")
    task = Task.objects.create(owner=user, tool=tool)

    rows = [
        ("test", "startup-1d-cpu", "startup", "finished", 0.05, 0.01),
        ("zonotope", "matMul-5d-cpu", "matMul", "finished", 0.30, 0.02),
        ("zonotope", "minkSum-5d-cpu", "minkSum", "finished", 0.20, 0.03),
        ("zonotope", "matMul-5d-gpu", "matMul", "unsupported", 0.05, 0.01),
        ("interval", "convHull-5d-cpu", "convHull", "finished", 0.40, 0.02),
    ]
    benchmarks = {}
    for name, instance_name, operation, verdict, time, prepare in rows:
        benchmark = benchmarks.get(name)
        if benchmark is None:
            benchmark = Benchmark.objects.create(
                category=category, name=name, published=True)
            benchmarks[name] = benchmark
        instance = Instance.objects.create(
            benchmark=benchmark, name=instance_name,
            spec={"benchmark": name, "instance": instance_name, "repetition": "100",
                  "params": json.dumps({"operation": operation, "dim": 5, "device": "cpu"})},
        )
        Result.objects.create(
            task=task, tool=tool, benchmark=benchmark, instance=instance,
            category=category, result=verdict, time=time,
            extra={"prepare_time": prepare},
        )
    return user, tool, category, task


def test_facet_options_come_from_the_loaded_catalog():
    """The selectors offer whatever the loaded instances.csv actually contains — not a
    hardcoded list — so a new benchmark or operation appears without a code change."""
    from cora_comp.plots import facet_options

    _fixture()
    options = {f["key"]: f["options"] for f in facet_options()}
    assert options["benchmark"] == ["interval", "test", "zonotope"]
    assert options["operation"] == ["convHull", "matMul", "minkSum", "startup"]


def test_measurements_carry_the_verdict_times_and_facets():
    from cora_comp.plots import measurements

    _fixture()
    rows = {(r["benchmark"], r["instance"]): r for r in measurements()}
    matmul = rows[("zonotope", "matMul-5d-cpu")]
    assert matmul["result"] == "finished"
    assert matmul["time"] == 0.30
    assert matmul["prepare_time"] == 0.02
    assert matmul["facets"] == {"benchmark": "zonotope", "operation": "matMul"}
    # An unsupported instance is still reported; the page decides what to plot.
    assert rows[("zonotope", "matMul-5d-gpu")]["result"] == "unsupported"


def test_a_rerun_replaces_its_predecessor():
    """Re-running a tool must not plot the same instance twice."""
    from comp_eval_platform.core.models import Benchmark, Instance, Result, Task
    from cora_comp.plots import measurements

    user, tool, category, _ = _fixture()
    benchmark = Benchmark.objects.get(name="zonotope")
    instance = Instance.objects.get(benchmark=benchmark, name="matMul-5d-cpu")
    Result.objects.create(
        task=Task.objects.create(owner=user, tool=tool), tool=tool, benchmark=benchmark,
        instance=instance, category=category, result="finished", time=0.11,
        extra={"prepare_time": 0.01},
    )
    rows = [r for r in measurements()
            if (r["benchmark"], r["instance"]) == ("zonotope", "matMul-5d-cpu")]
    assert len(rows) == 1
    assert rows[0]["time"] == 0.11


def test_operation_falls_back_to_the_instance_name():
    """A catalog loaded before params carried the operation still groups correctly."""
    from cora_comp.plots import facet_values

    assert facet_values("zonotope", "matMul-500d-cpu", {"params": ""})["operation"] == "matMul"
    assert facet_values("zonotope", "matMul-500d-cpu", {})["operation"] == "matMul"


def test_the_data_endpoint_needs_a_logged_in_user(client):
    _fixture()
    assert client.get("/api/cora/results/data/").status_code == 403


def test_the_data_endpoint_serves_the_payload(client):
    user, *_ = _fixture()
    client.force_login(user)
    payload = client.get("/api/cora/results/data/").json()
    assert payload["tools"] == ["CORA"]
    assert len(payload["measurements"]) == 5
    assert [f["key"] for f in payload["facets"]] == ["benchmark", "operation"]


def test_the_page_renders(client):
    assert client.get("/api/cora/results/").status_code == 200
