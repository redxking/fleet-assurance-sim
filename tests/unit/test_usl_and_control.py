from __future__ import annotations

import math

import numpy as np

from fleet_sim.analysis.control import foster_lyapunov_linear_drift
from fleet_sim.analysis.usl import fit_usl, retrograde_point, usl_capacity


def test_usl_parameter_recovery() -> None:
    n = np.array([1, 10, 100, 1_000, 10_000], dtype=float)
    throughput = usl_capacity(n, alpha=0.02, beta=2e-6, scale=5.0)
    fitted = fit_usl(n, throughput)
    assert math.isclose(fitted.alpha, 0.02, rel_tol=1e-5)
    assert math.isclose(fitted.beta, 2e-6, rel_tol=1e-5)
    assert math.isclose(fitted.n_star or 0.0, retrograde_point(0.02, 2e-6) or 0.0, rel_tol=1e-5)


def test_foster_lyapunov_drift_sign() -> None:
    assert foster_lyapunov_linear_drift(10, 5.0, 3.0, 2) < 0
    assert foster_lyapunov_linear_drift(1, 5.0, 3.0, 2) > 0
