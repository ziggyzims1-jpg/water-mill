"""Small-sample statistics from published formulas, stdlib only.

`requirements.txt` is deliberately tiny, so nothing here imports scipy or
numpy. Each function is checked in `tests/test_stats.py` against values computed
once with SciPy / statsmodels (the producing call is quoted beside the number)
and against textbook worked examples.

Which tool for which data (the agent log is skewed and lopsided):

* proportions (landed, first-pass approval): `wilson` interval per group,
  `newcombe_diff` for the difference, `fisher_exact` for the p-value;
* durations, tokens, tool calls, sluice rounds: skewed, so no t-test --
  `median` with `median_ci`, `mann_whitney` for the p-value and a seeded
  `bootstrap_median_diff` for the difference's interval.

Nothing here decides whether n is big enough; `agentcompare` does that.
"""

from __future__ import annotations

import math
import random
from statistics import NormalDist

Z95 = NormalDist().inv_cdf(0.975)  # 1.959963984540054


def median(values: list[float]) -> float:
    v = sorted(values)
    n = len(v)
    if n == 0:
        raise ValueError("median of nothing")
    mid = n // 2
    return float(v[mid]) if n % 2 else (v[mid - 1] + v[mid]) / 2.0


def wilson(k: int, n: int, z: float = Z95) -> tuple[float, float]:
    """Wilson score interval for k successes in n trials (Wilson 1927)."""
    if n <= 0:
        raise ValueError("wilson needs n > 0")
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def newcombe_diff(k1: int, n1: int, k2: int, n2: int, z: float = Z95) -> tuple[float, float, float]:
    """(p1 - p2, lower, upper): Newcombe's hybrid score interval (method 10)."""
    p1, p2 = k1 / n1, k2 / n2
    l1, u1 = wilson(k1, n1, z)
    l2, u2 = wilson(k2, n2, z)
    d = p1 - p2
    lower = d - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2)
    upper = d + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)
    return d, lower, upper


def median_ci(values: list[float], alpha: float = 0.05) -> tuple[float, float] | None:
    """Distribution-free CI for the median from order statistics.

    The interval (x_(r), x_(n+1-r)) covers the median with probability
    1 - 2 P(Bin(n, 1/2) <= r-1); take the widest-r interval whose miss
    probability is at most alpha, so coverage is at least 1 - alpha (it is
    conservative, usually 96-99%). None when n is too small for any interval
    (n < 6 at alpha 0.05).
    """
    v = sorted(values)
    n = len(v)
    cum = 0  # running sum of C(n, i), i <= k
    best = None
    for k in range(0, n // 2):
        cum += math.comb(n, k)
        if 2 * cum / 2**n <= alpha:
            best = k + 1  # rank r = k + 1 (1-based)
        else:
            break
    if best is None:
        return None
    return float(v[best - 1]), float(v[n - best])


def _midranks(values: list[float]) -> tuple[list[float], list[int]]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    ties: list[int] = []
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for idx in range(i, j + 1):
            ranks[order[idx]] = avg
        ties.append(j - i + 1)
        i = j + 1
    return ranks, ties


def mann_whitney(x: list[float], y: list[float]) -> tuple[float, float]:
    """(U for x, two-sided p): normal approximation, tie-corrected, continuity-corrected.

    Matches scipy.stats.mannwhitneyu(method="asymptotic", use_continuity=True).
    Unreliable below roughly 8 per group -- the caller enforces a minimum n.
    """
    n1, n2 = len(x), len(y)
    if n1 == 0 or n2 == 0:
        raise ValueError("mann_whitney needs both samples non-empty")
    ranks, ties = _midranks(list(x) + list(y))
    u1 = sum(ranks[:n1]) - n1 * (n1 + 1) / 2.0
    n = n1 + n2
    mu = n1 * n2 / 2.0
    tie_term = sum(t**3 - t for t in ties) / (n * (n - 1)) if n > 1 else 0.0
    var = n1 * n2 / 12.0 * ((n + 1) - tie_term)
    if var <= 0:  # every value identical: no evidence of any difference
        return u1, 1.0
    z = (abs(u1 - mu) - 0.5) / math.sqrt(var)
    p = math.erfc(max(z, 0.0) / math.sqrt(2))
    return u1, min(1.0, p)


def fisher_exact(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher exact p for [[a, b], [c, d]] (sum of tables no likelier
    than the observed, with scipy's 1e-7 relative tolerance)."""
    row1, row2, col1 = a + b, c + d, a + c
    n = row1 + row2
    denom = math.comb(n, col1)

    def prob(x: int) -> float:
        return math.comb(row1, x) * math.comb(row2, col1 - x) / denom

    lo, hi = max(0, col1 - row2), min(row1, col1)
    observed = prob(a)
    total = sum(p for p in (prob(x) for x in range(lo, hi + 1)) if p <= observed * (1 + 1e-7))
    return min(1.0, total)


def bootstrap_median_diff(
    x: list[float], y: list[float], *, seed: int = 0, n_boot: int = 2000, alpha: float = 0.05,
) -> tuple[float, float, float]:
    """(median(x) - median(y), lower, upper): seeded percentile bootstrap.

    Each group is resampled with replacement on its own. Deterministic for a
    given seed, so the same data prints the same interval every time.
    """
    rng = random.Random(seed)
    diffs = []
    for _ in range(n_boot):
        bx = [x[rng.randrange(len(x))] for _ in x]
        by = [y[rng.randrange(len(y))] for _ in y]
        diffs.append(median(bx) - median(by))
    diffs.sort()
    lo = diffs[int(math.floor((alpha / 2) * n_boot))]
    hi = diffs[min(n_boot - 1, int(math.ceil((1 - alpha / 2) * n_boot)) - 1)]
    return median(x) - median(y), lo, hi
