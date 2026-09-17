"""Turn a benchmark run's normalized records into a step stats summary.

A run is judged only on whether each instance ran: a tool reports one of three verdicts
— it finished, the operation is unsupported (a library with no GPU, say), or it failed —
and the harness adds ``timeout``. Any parsed run is "green"; the tally is what
distinguishes a good one.
"""
from __future__ import annotations

#: The buckets shown, in reading order.
VERDICTS = ["finished", "unsupported", "error", "timeout"]


def _bucket(result: str) -> str:
    """The verdict's own bucket; anything else — including the harness's
    ``prepare_failed`` — is an error."""
    r = (result or "").strip().lower()
    return r if r in VERDICTS else "error"


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
