"""Turn a benchmark run's normalized records into a step stats summary.

A run is judged only on whether each instance ran: timing is the harness's business, so
a tool reports one of three verdicts — it finished, the operation is unsupported (a
library with no GPU, say), or it failed. Any parsed run is "green"; the tally is what
distinguishes a good one.
"""
from __future__ import annotations

#: The buckets shown, in reading order.
VERDICTS = ["finished", "unsupported", "error"]

_FINISHED = {"finished"}
_UNSUPPORTED = {"unsupported"}


def _bucket(result: str) -> str:
    """Anything the tool did not report as finished or unsupported is an error — which
    also catches the harness's own verdicts (``timeout``, ``prepare_failed``)."""
    r = (result or "").strip().lower()
    if r in _FINISHED:
        return "finished"
    if r in _UNSUPPORTED:
        return "unsupported"
    return "error"


def summarize(records) -> dict | None:
    """A ``{summary, severity}`` payload for the step, or ``None`` when there is
    nothing to summarize (no records → malformed/empty file, so no green summary)."""
    if not records:
        return None
    verdicts = {v: 0 for v in VERDICTS}
    for rec in records:
        verdicts[_bucket(rec.result)] += 1
    return {
        "summary": {"instances": len(records), "verdicts": verdicts, "order": VERDICTS},
        "severity": "success",
    }
