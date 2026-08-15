"""CORA-COMP as a plugin for comp-eval-platform.

The whole variant is one Competition subclass + step handlers + node scripts. It
takes ARCH's benchmark model — one central repository whose ``instances.csv`` lists
every benchmark and instance — but has a single category (``contSet``), so there is no
per-category registry and no category argument in the tool interface. Within it the
catalog is shown in groups, which core renders from ``Benchmark.extra["group"]``.
"""
