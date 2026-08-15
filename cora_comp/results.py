"""Turn a benchmark run's node output into normalized per-instance records.

The node harness writes one ``results.csv`` per benchmark with a stable prefix
(``benchmark``, ``instance``) and suffix (``prepare_time``, ``result``, ``time``);
between them sit whatever extra columns the tool self-reported, which differ per tool
and are unknown to us. So the parser is column-name driven rather than fixed: ``time``
is the harness wall-clock (canonical) and everything left over rides along as ``extra``,
numeric where it parses as a number. ARCH needs a per-category parser registry for this;
with one category, the generic reader is the whole seam.
"""
import csv
import os

from comp_eval_platform.results import ResultRecord

RESULTS_FILE = "results.csv"

#: Columns the record models directly; every other column becomes ``extra``.
_KNOWN_COLUMNS = {"benchmark", "instance", "result", "time"}


def _number(value):
    """``value`` as a float, or the trimmed string when it is not numeric."""
    text = (value or "").strip()
    try:
        return float(text)
    except ValueError:
        return text


def _float_or_none(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_results(artifacts_dir: str) -> list:
    """Read ``artifacts_dir/results.csv`` into ``ResultRecord``s. A missing file yields
    no records, which the caller reads as a run that produced nothing to store."""
    path = os.path.join(artifacts_dir, RESULTS_FILE)
    if not os.path.exists(path):
        return []
    with open(path, newline="") as fh:
        return [_record(row) for row in csv.DictReader(fh)]


def _record(row: dict) -> ResultRecord:
    extra = {k: _number(v) for k, v in row.items()
             if k is not None and k not in _KNOWN_COLUMNS}
    return ResultRecord(
        instance=(row.get("instance") or "").strip(),
        result=(row.get("result") or "").strip(),
        time=_float_or_none(row.get("time")),
        extra=extra,
    )
