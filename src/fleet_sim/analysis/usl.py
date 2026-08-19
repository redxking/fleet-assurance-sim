"""Universal Scalability Law fitting and retrograde-point analysis."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.optimize import curve_fit


@dataclass(frozen=True, slots=True)
class USLFit:
    scale: float
    alpha: float
    beta: float
    n_star: float | None
    r_squared: float
    residual_rmse: float
    covariance: tuple[tuple[float, ...], ...]


def usl_capacity(n: np.ndarray | float, alpha: float, beta: float, scale: float = 1.0):
    values = np.asarray(n, dtype=float)
    denominator = 1.0 + alpha * (values - 1.0) + beta * values * (values - 1.0)
    return scale * values / denominator


def retrograde_point(alpha: float, beta: float) -> float | None:
    if beta <= 0 or alpha >= 1:
        return None
    return math.sqrt((1.0 - alpha) / beta)


def fit_usl(n_values, throughput_values) -> USLFit:
    n = np.asarray(n_values, dtype=float)
    throughput = np.asarray(throughput_values, dtype=float)
    if len(n) < 3 or len(n) != len(throughput):
        raise ValueError("at least three paired observations are required")
    if np.any(n < 1) or np.any(throughput <= 0):
        raise ValueError("N must be at least 1 and throughput must be positive")

    def model(x, scale, alpha, beta):
        return usl_capacity(x, alpha, beta, scale)

    scale_guess = max(throughput[0], np.max(throughput / n))
    parameters, covariance = curve_fit(
        model,
        n,
        throughput,
        p0=(scale_guess, 0.01, 1e-6),
        bounds=((1e-12, 0.0, 0.0), (np.inf, np.inf, np.inf)),
        maxfev=100_000,
    )
    scale, alpha, beta = (float(value) for value in parameters)
    prediction = model(n, *parameters)
    residual = throughput - prediction
    ss_residual = float(np.sum(residual**2))
    ss_total = float(np.sum((throughput - throughput.mean()) ** 2))
    r_squared = 1.0 - ss_residual / ss_total if ss_total > 0 else 1.0
    rmse = math.sqrt(ss_residual / len(n))
    return USLFit(
        scale,
        alpha,
        beta,
        retrograde_point(alpha, beta),
        r_squared,
        rmse,
        tuple(tuple(float(value) for value in row) for row in covariance),
    )


def bootstrap_usl(
    n_values,
    throughput_matrix,
    *,
    seed: int,
    replications: int = 1_000,
) -> dict[str, tuple[float, float]]:
    """Bootstrap across independent replication columns at each N."""

    n = np.asarray(n_values, dtype=float)
    values = np.asarray(throughput_matrix, dtype=float)
    if values.ndim != 2 or values.shape[0] != len(n):
        raise ValueError("throughput_matrix must have shape [len(N), replications]")
    rng = np.random.Generator(np.random.PCG64DXSM(seed))
    estimates: dict[str, list[float]] = {"alpha": [], "beta": [], "n_star": []}
    columns = values.shape[1]
    for _ in range(replications):
        sampled = rng.integers(0, columns, size=columns)
        means = values[:, sampled].mean(axis=1)
        try:
            fitted = fit_usl(n, means)
        except (RuntimeError, ValueError):
            continue
        estimates["alpha"].append(fitted.alpha)
        estimates["beta"].append(fitted.beta)
        if fitted.n_star is not None:
            estimates["n_star"].append(fitted.n_star)
    intervals = {}
    for name, data in estimates.items():
        if data:
            intervals[name] = (float(np.quantile(data, 0.025)), float(np.quantile(data, 0.975)))
        else:
            intervals[name] = (math.nan, math.nan)
    return intervals
