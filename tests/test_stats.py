"""stats.py against SciPy / statsmodels reference values and textbook examples.

Reference values were computed once (scipy 1.18.1, statsmodels 0.15.0) and are
hard-coded; the producing call sits beside each. Tolerance is stated per test.
"""

from __future__ import annotations

import math

import pytest

from watermill import stats


def test_median_odd_even_and_empty():
    assert stats.median([3, 1, 2]) == 2
    assert stats.median([4, 1, 2, 3]) == 2.5
    with pytest.raises(ValueError):
        stats.median([])


# statsmodels.stats.proportion.proportion_confint(k, n, alpha=0.05, method="wilson")
WILSON = [
    (0, 10, 0.0, 0.27753279986288926),
    (10, 10, 0.7224672001371106, 1.0),
    (7, 20, 0.18119182410108203, 0.5671457233147638),
    (1, 8, 0.022417491450056642, 0.47088818221285356),
    (45, 155, 0.224622559644123, 0.3661643766973879),
]


@pytest.mark.parametrize(("k", "n", "lo", "hi"), WILSON)
def test_wilson_matches_statsmodels_to_1e_9(k, n, lo, hi):
    got = stats.wilson(k, n)
    assert got == pytest.approx((lo, hi), abs=1e-9)


def test_wilson_never_leaves_0_1_and_rejects_n_zero():
    lo, hi = stats.wilson(0, 3)
    assert lo == 0.0 and 0 < hi < 1
    with pytest.raises(ValueError):
        stats.wilson(0, 0)


# statsmodels.stats.proportion.confint_proportions_2indep(k1, n1, k2, n2,
#     method="newcomb", compare="diff")  -> (lower, upper)
NEWCOMBE = [
    (7, 20, 12, 30, -0.29444460805579253, 0.21626516733767803),
    (0, 10, 6, 10, -0.8318196702937638, -0.2005243216429799),
    (45, 155, 3, 16, -0.14850553818013057, 0.2461217409442267),
]


@pytest.mark.parametrize(("k1", "n1", "k2", "n2", "lo", "hi"), NEWCOMBE)
def test_newcombe_matches_statsmodels_to_1e_9(k1, n1, k2, n2, lo, hi):
    d, got_lo, got_hi = stats.newcombe_diff(k1, n1, k2, n2)
    assert d == pytest.approx(k1 / n1 - k2 / n2)
    assert (got_lo, got_hi) == pytest.approx((lo, hi), abs=1e-9)


# scipy.stats.mannwhitneyu(x, y, alternative="two-sided", method="asymptotic",
#     use_continuity=True) -> (statistic, pvalue)
MWU_X = [1.1, 2.3, 3.1, 4.8, 5.0, 6.2, 7.7, 9.1]
MWU_Y = [3.3, 5.5, 6.1, 8.8, 9.9, 12.0, 13.5, 15.2, 16.0]
MWU_TX = [1, 2, 2, 3, 3, 3, 4, 5, 5]
MWU_TY = [2, 3, 4, 4, 5, 6, 6, 7, 8, 8]


def test_mann_whitney_no_ties_matches_scipy_to_1e_9():
    u, p = stats.mann_whitney(MWU_X, MWU_Y)
    assert u == 12.0
    assert p == pytest.approx(0.02374139453072587, abs=1e-9)


def test_mann_whitney_with_ties_matches_scipy_both_orders():
    u, p = stats.mann_whitney(MWU_TX, MWU_TY)
    assert u == 17.5
    assert p == pytest.approx(0.025872552913041923, abs=1e-9)
    u2, p2 = stats.mann_whitney(MWU_TY, MWU_TX)
    assert u2 == 72.5 and u + u2 == len(MWU_TX) * len(MWU_TY)
    assert p2 == pytest.approx(p, abs=1e-12)


def test_mann_whitney_identical_values_say_no_difference():
    assert stats.mann_whitney([2, 2, 2], [2, 2, 2, 2])[1] == 1.0


# scipy.stats.fisher_exact([[a, b], [c, d]]).pvalue ; the first is Fisher's
# lady tasting tea (1935): two-sided p = 17/35 = 0.4857.
FISHER = [
    ((3, 1, 1, 3), 0.48571428571428565),
    ((8, 2, 1, 5), 0.034965034965034975),
    ((0, 6, 6, 0), 0.0021645021645021645),
    ((12, 5, 29, 3), 0.10642628903375537),
    ((10, 10, 10, 10), 1.0),
]


@pytest.mark.parametrize(("table", "p"), FISHER)
def test_fisher_exact_matches_scipy_to_1e_12(table, p):
    assert stats.fisher_exact(*table) == pytest.approx(p, abs=1e-12)


# Order-statistic median CI at alpha 0.05. 1-based ranks (lower, upper) come from
# scipy.stats.binom.cdf(r - 1, n, 0.5) <= 0.025: n=8 -> (1, 8), n=11 -> (2, 10),
# n=20 -> (6, 15). Cross-checked against the standard sign-test table.
@pytest.mark.parametrize(("n", "lo_rank", "hi_rank"), [(8, 1, 8), (11, 2, 10), (20, 6, 15)])
def test_median_ci_uses_the_published_ranks(n, lo_rank, hi_rank):
    data = [float(i * 3 + 1) for i in range(n)]
    assert stats.median_ci(data) == (data[lo_rank - 1], data[hi_rank - 1])


def test_median_ci_is_none_when_n_is_too_small():
    assert stats.median_ci([1, 2, 3, 4, 5]) is None  # 2 * 0.5**5 = 0.0625 > 0.05
    assert stats.median_ci([]) is None


def test_median_ci_ignores_input_order():
    assert stats.median_ci([9, 1, 5, 3, 7, 2, 8, 4]) == stats.median_ci(sorted([9, 1, 5, 3, 7, 2, 8, 4]))


def test_bootstrap_is_deterministic_and_seed_dependent():
    x = [float(i) for i in range(10, 30)]
    y = [float(i) for i in range(0, 20)]
    a = stats.bootstrap_median_diff(x, y, seed=3)
    assert a == stats.bootstrap_median_diff(x, y, seed=3)
    assert a != stats.bootstrap_median_diff(x, y, seed=4)


# stats.bootstrap_median_diff(x, y, seed=7) on the data below, recorded 2026-10-13
PINNED_BOOT = (1.8364803932976432, -1.6217561668719336, 7.142627330798805)


def test_bootstrap_is_pinned_for_a_seed():
    # A regression pin, not a SciPy reference (the resampling stream is
    # random.Random's): continuous data, so an unseeded or re-ordered resampler
    # moves the percentiles. Exact equality: the same seed must print the same CI.
    x = [math.exp(i / 7) for i in range(25)]
    y = [math.exp(i / 9) + 0.5 for i in range(22)]
    assert stats.bootstrap_median_diff(x, y, seed=7) == pytest.approx(PINNED_BOOT, abs=1e-12)


def test_bootstrap_interval_brackets_a_known_shift():
    # y is x shifted by exactly 10: the observed median difference is -10 and a
    # 95% percentile interval must contain it and exclude 0.
    x = [float(v) for v in (1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233)]
    y = [v + 10 for v in x]
    d, lo, hi = stats.bootstrap_median_diff(x, y, seed=1)
    assert d == -10
    assert lo <= d <= hi
    assert lo < hi


def test_bootstrap_of_constants_collapses_to_a_point():
    assert stats.bootstrap_median_diff([5.0] * 9, [2.0] * 9, seed=0) == (3.0, 3.0, 3.0)


def test_z95_is_the_textbook_constant():
    assert math.isclose(stats.Z95, 1.959963984540054, abs_tol=1e-12)
