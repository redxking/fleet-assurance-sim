"""Supervisory-loop margins and queue drift conditions."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy import signal


@dataclass(frozen=True, slots=True)
class StabilityMargins:
    gain_margin: float
    gain_margin_db: float
    phase_margin_deg: float
    gain_cross_frequency_rad_s: float | None
    phase_cross_frequency_rad_s: float | None
    closed_loop_poles: tuple[complex, ...]
    stable: bool


def _poly_add(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    size = max(len(left), len(right))
    a = np.pad(left, (size - len(left), 0))
    b = np.pad(right, (size - len(right), 0))
    return a + b


def supervisory_open_loop(
    plant_gain: float,
    time_constant_s: float,
    delay_s: float,
    proportional_gain: float,
    integral_gain: float = 0.0,
) -> tuple[np.ndarray, np.ndarray]:
    if plant_gain <= 0 or time_constant_s <= 0 or delay_s < 0 or proportional_gain < 0 or integral_gain < 0:
        raise ValueError("invalid controller parameters")
    delay_num = np.array([-delay_s / 2.0, 1.0]) if delay_s > 0 else np.array([1.0])
    delay_den = np.array([delay_s / 2.0, 1.0]) if delay_s > 0 else np.array([1.0])
    plant_num = np.array([plant_gain])
    plant_den = np.array([time_constant_s, 1.0])
    if integral_gain > 0:
        controller_num = np.array([proportional_gain, integral_gain])
        controller_den = np.array([1.0, 0.0])
    else:
        controller_num = np.array([proportional_gain])
        controller_den = np.array([1.0])
    numerator = np.polymul(np.polymul(controller_num, plant_num), delay_num)
    denominator = np.polymul(np.polymul(controller_den, plant_den), delay_den)
    return numerator, denominator


def stability_margins(
    plant_gain: float,
    time_constant_s: float,
    delay_s: float,
    proportional_gain: float,
    integral_gain: float = 0.0,
) -> StabilityMargins:
    numerator, denominator = supervisory_open_loop(
        plant_gain, time_constant_s, delay_s, proportional_gain, integral_gain
    )
    frequencies = np.logspace(-5, 5, 50_000)
    _, response = signal.freqs(numerator, denominator, worN=frequencies)
    magnitude = np.abs(response)
    phase = np.unwrap(np.angle(response)) * 180.0 / np.pi

    gain_cross = None
    phase_margin = math.inf
    crossings = np.where(np.diff(np.sign(magnitude - 1.0)) != 0)[0]
    if len(crossings):
        index = int(crossings[0])
        gain_cross = float(frequencies[index])
        phase_margin = float(180.0 + phase[index])

    phase_cross = None
    gain_margin = math.inf
    phase_crossings = np.where(np.diff(np.sign(phase + 180.0)) != 0)[0]
    if len(phase_crossings):
        index = int(phase_crossings[0])
        phase_cross = float(frequencies[index])
        gain_at_cross = float(magnitude[index])
        gain_margin = math.inf if gain_at_cross == 0 else 1.0 / gain_at_cross

    closed_loop_denominator = _poly_add(denominator, numerator)
    poles = tuple(complex(value) for value in np.roots(closed_loop_denominator))
    stable = all(pole.real < 0 for pole in poles)
    gain_margin_db = math.inf if math.isinf(gain_margin) else 20.0 * math.log10(gain_margin)
    return StabilityMargins(
        gain_margin,
        gain_margin_db,
        phase_margin,
        gain_cross,
        phase_cross,
        poles,
        stable,
    )


def foster_lyapunov_linear_drift(
    queue_length: int,
    arrival_rate: float,
    service_rate_per_server: float,
    servers: int,
) -> float:
    """Generator drift for V(x)=x in a continuous-time M/M/c queue."""

    if queue_length < 0 or arrival_rate < 0 or service_rate_per_server <= 0 or servers < 1:
        raise ValueError("invalid queue parameters")
    service_rate = min(queue_length, servers) * service_rate_per_server
    return arrival_rate - service_rate
