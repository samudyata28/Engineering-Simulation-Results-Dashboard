"""Assessment and comparison maths. Pure functions, no I/O."""
from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass, field

from ..config import Criteria

STATUS_PASS = "pass"
STATUS_FAIL = "fail"
STATUS_INCOMPLETE = "incomplete"  # no violation seen, but samples don't cover the whole range
STATUS_NOT_ASSESSABLE = "not_assessable"  # no samples inside the range at all


@dataclass
class Warning_:
    code: str
    severity: str  # info | warning
    message: str

    def as_dict(self) -> dict:
        return {"code": self.code, "severity": self.severity, "message": self.message}


@dataclass
class Assessment:
    status: str
    samples_in_range: int
    peak_magnitude: float | None
    peak_frequency: float | None
    margin: float | None
    marginal: bool
    overall_peak_magnitude: float
    overall_peak_frequency: float
    warnings: list[Warning_] = field(default_factory=list)


def _argmax(values: list[float]) -> int:
    """Index of the maximum; ties resolve to the lowest frequency (first occurrence)."""
    best = 0
    for i, v in enumerate(values):
        if v > values[best]:
            best = i
    return best


def assess(freqs: list[float], mags: list[float], c: Criteria) -> Assessment:
    """Apply the review rule: max magnitude over f_min <= f <= f_max must be <= limit."""
    if not freqs or len(freqs) != len(mags):
        raise ValueError("freqs and mags must be non-empty and equal length")

    oi = _argmax(mags)
    idx = [i for i, f in enumerate(freqs) if c.f_min <= f <= c.f_max]  # both ends inclusive
    warns: list[Warning_] = []
    u = c.unit

    if freqs[0] > c.f_min:
        warns.append(Warning_("LOW_START", "info",
                              f"First sample is at {freqs[0]:g} Hz; {c.f_min:g}–{freqs[0]:g} Hz is not covered by the data."))

    if not idx:
        warns.append(Warning_("NO_SAMPLES_IN_RANGE", "warning",
                              f"No samples between {c.f_min:g} and {c.f_max:g} Hz; the criterion cannot be evaluated."))
        return Assessment(STATUS_NOT_ASSESSABLE, 0, None, None, None, False, mags[oi], freqs[oi], warns)

    rm = [mags[i] for i in idx]
    k = _argmax(rm)
    peak_i = idx[k]
    peak, pf = mags[peak_i], freqs[peak_i]
    margin = c.limit - peak
    covers = freqs[-1] >= c.f_max

    if peak > c.limit:
        status = STATUS_FAIL
    elif not covers:
        status = STATUS_INCOMPLETE
    else:
        status = STATUS_PASS

    if not covers:
        warns.append(Warning_("RANGE_INCOMPLETE", "warning",
                              f"Data ends at {freqs[-1]:g} Hz, before the {c.f_max:g} Hz end of the assessment range."
                              + (" No violation observed in the available data, but the result is inconclusive." if status != STATUS_FAIL else "")))

    marginal = status == STATUS_PASS and margin < c.marginal_fraction * c.limit
    if marginal:
        lo = freqs[peak_i - 1] if peak_i > 0 else None
        hi = freqs[peak_i + 1] if peak_i < len(freqs) - 1 else None
        gaps = [abs(pf - x) for x in (lo, hi) if x is not None]
        gap_txt = f" Samples next to the peak are {min(gaps):g}–{max(gaps):g} Hz away," if gaps else ""
        warns.append(Warning_("MARGINAL", "warning",
                              f"Passes by only {margin:.2f} {u} ({margin / c.limit:.1%} of the limit)."
                              f"{gap_txt} so a narrow resonance between samples could exceed {c.limit:g} {u}."))

    if len(idx) >= 2 and k in (0, len(rm) - 1) and rm[k] > min(rm):
        edge = "start" if k == 0 else "end"
        warns.append(Warning_("PEAK_AT_RANGE_EDGE", "warning",
                              f"The in-range peak is at the {edge} of the assessed samples; the response may continue to rise outside the range."))

    if len(idx) < 5:
        warns.append(Warning_("SPARSE_IN_RANGE", "warning",
                              f"Only {len(idx)} sample(s) inside the assessment range; peak location is poorly resolved."))

    return Assessment(status, len(idx), peak, pf, margin, marginal, mags[oi], freqs[oi], warns)


# ----------------------------------------------------------------- comparison

def interp(xs: list[float], ys: list[float], x: float) -> float:
    """Linear interpolation; ``x`` must lie within [xs[0], xs[-1]]."""
    i = bisect_left(xs, x)
    if i < len(xs) and xs[i] == x:
        return ys[i]
    x0, x1, y0, y1 = xs[i - 1], xs[i], ys[i - 1], ys[i]
    return y0 + (y1 - y0) * (x - x0) / (x1 - x0)


def delta_curve(fa: list[float], ma: list[float], fb: list[float], mb: list[float]) -> list[dict]:
    """target - base on the union of both frequency grids, over their overlap.

    Revisions are sampled on different grids (e.g. the peak sample is at 37.6 Hz
    in rev1 but 37.8 Hz in rev2), so a pointwise subtraction needs interpolation.
    Linear interpolation across a sharp resonance is approximate: callers label
    this series as interpolated.
    """
    lo, hi = max(fa[0], fb[0]), min(fa[-1], fb[-1])
    if lo > hi:
        return []
    grid = sorted({f for f in fa + fb if lo <= f <= hi})
    return [
        {"frequency": f, "base": (a := interp(fa, ma, f)), "target": (b := interp(fb, mb, f)), "delta": b - a}
        for f in grid
    ]


def classify_change(delta: float | None, tolerance: float) -> str:
    """Lower magnitude is better. Returns improved | degraded | unchanged | unknown."""
    if delta is None:
        return "unknown"
    if delta < -tolerance:
        return "improved"
    if delta > tolerance:
        return "degraded"
    return "unchanged"
