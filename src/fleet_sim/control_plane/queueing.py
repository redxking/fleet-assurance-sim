"""Analytic queueing baselines, capacity sizing, and M/M/c verification simulation."""

from __future__ import annotations

import heapq
import math
from dataclasses import asdict, dataclass

import numpy as np
from scipy.special import gammaln, logsumexp


@dataclass(frozen=True, slots=True)
class QueueMetrics:
    arrival_rate: float
    service_rate_per_server: float
    servers: int
    utilization: float
    probability_wait: float
    mean_wait_queue_s: float
    mean_time_system_s: float
    mean_number_queue: float
    mean_number_system: float

    def to_dict(self) -> dict[str, float | int]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class QueueSimulationResult:
    jobs_measured: int
    effective_arrival_rate: float
    utilization: float
    mean_wait_queue_s: float
    mean_time_system_s: float
    p50_time_system_s: float
    p95_time_system_s: float
    p99_time_system_s: float
    time_average_number_system: float
    little_law_residual: float
    measurement_start_s: float
    measurement_end_s: float

    def to_dict(self) -> dict[str, float | int]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class QueueJobTrace:
    arrivals: np.ndarray
    starts: np.ndarray
    departures: np.ndarray
    service_times: np.ndarray


def mm1_metrics(arrival_rate: float, service_rate: float) -> QueueMetrics:
    if arrival_rate < 0 or service_rate <= 0:
        raise ValueError("arrival_rate must be nonnegative and service_rate positive")
    rho = arrival_rate / service_rate
    if rho >= 1.0:
        return QueueMetrics(
            arrival_rate,
            service_rate,
            1,
            rho,
            1.0,
            math.inf,
            math.inf,
            math.inf,
            math.inf,
        )
    probability_wait = rho
    mean_wait_queue = rho / (service_rate - arrival_rate) if arrival_rate > 0 else 0.0
    mean_time_system = 1.0 / (service_rate - arrival_rate)
    mean_number_queue = arrival_rate * mean_wait_queue
    mean_number_system = arrival_rate * mean_time_system
    return QueueMetrics(
        arrival_rate,
        service_rate,
        1,
        rho,
        probability_wait,
        mean_wait_queue,
        mean_time_system,
        mean_number_queue,
        mean_number_system,
    )


def erlang_c(arrival_rate: float, service_rate_per_server: float, servers: int) -> QueueMetrics:
    """Numerically stable M/M/c Erlang C calculation."""

    if arrival_rate < 0 or service_rate_per_server <= 0 or servers < 1:
        raise ValueError("invalid M/M/c parameters")
    if arrival_rate == 0:
        return QueueMetrics(
            0.0,
            service_rate_per_server,
            servers,
            0.0,
            0.0,
            0.0,
            1.0 / service_rate_per_server,
            0.0,
            0.0,
        )

    offered_load = arrival_rate / service_rate_per_server
    rho = offered_load / servers
    if rho >= 1.0:
        return QueueMetrics(
            arrival_rate,
            service_rate_per_server,
            servers,
            rho,
            1.0,
            math.inf,
            math.inf,
            math.inf,
            math.inf,
        )

    n = np.arange(servers, dtype=float)
    log_terms = n * math.log(offered_load) - np.array([gammaln(x + 1.0) for x in n])
    log_tail = (
        servers * math.log(offered_load)
        - gammaln(servers + 1.0)
        - math.log1p(-rho)
    )
    log_denominator = logsumexp(np.concatenate([log_terms, np.array([log_tail])]))
    probability_wait = float(math.exp(log_tail - log_denominator))
    mean_wait_queue = probability_wait / (
        servers * service_rate_per_server - arrival_rate
    )
    mean_time_system = mean_wait_queue + 1.0 / service_rate_per_server
    mean_number_queue = arrival_rate * mean_wait_queue
    mean_number_system = arrival_rate * mean_time_system

    return QueueMetrics(
        arrival_rate,
        service_rate_per_server,
        servers,
        rho,
        probability_wait,
        mean_wait_queue,
        mean_time_system,
        mean_number_queue,
        mean_number_system,
    )


def minimum_servers(
    arrival_rate: float,
    service_rate_per_server: float,
    target_utilization: float = 0.70,
) -> int:
    if not 0 < target_utilization < 1:
        raise ValueError("target_utilization must be in (0, 1)")
    if arrival_rate < 0 or service_rate_per_server <= 0:
        raise ValueError("invalid rates")
    return max(
        1,
        math.ceil(
            arrival_rate / (target_utilization * service_rate_per_server)
        ),
    )


def utilization_crossing_n(
    arrival_rate_per_agent: float,
    service_rate_per_server: float,
    servers: int,
    threshold: float,
) -> float:
    if arrival_rate_per_agent <= 0:
        return math.inf
    if not 0 < threshold <= 1:
        raise ValueError("threshold must be in (0, 1]")
    return (
        threshold * servers * service_rate_per_server / arrival_rate_per_agent
    )


def generate_mm_c_jobs(
    *,
    arrival_rate: float,
    service_rate_per_server: float,
    servers: int,
    jobs: int,
    seed: int,
) -> QueueJobTrace:
    """Generate exact FCFS job times for an M/M/c queue."""

    if arrival_rate <= 0 or service_rate_per_server <= 0:
        raise ValueError("rates must be positive")
    if servers < 1 or jobs < 1:
        raise ValueError("servers and jobs must be positive")
    if arrival_rate >= servers * service_rate_per_server:
        raise ValueError("verification simulation requires utilization below one")

    rng = np.random.Generator(np.random.PCG64DXSM(seed))
    arrivals = np.cumsum(rng.exponential(1.0 / arrival_rate, size=jobs))
    service_times = rng.exponential(1.0 / service_rate_per_server, size=jobs)
    starts = np.empty(jobs, dtype=float)
    departures = np.empty(jobs, dtype=float)
    available_servers: list[tuple[float, int]] = [(0.0, index) for index in range(servers)]
    heapq.heapify(available_servers)

    for index, arrival in enumerate(arrivals):
        available_at, server_index = heapq.heappop(available_servers)
        start = max(float(arrival), available_at)
        departure = start + float(service_times[index])
        starts[index] = start
        departures[index] = departure
        heapq.heappush(available_servers, (departure, server_index))

    return QueueJobTrace(arrivals, starts, departures, service_times)


def simulate_mm_c(
    *,
    arrival_rate: float,
    service_rate_per_server: float,
    servers: int,
    jobs: int,
    warmup_jobs: int,
    seed: int,
) -> QueueSimulationResult:
    if not 0 <= warmup_jobs < jobs - 1:
        raise ValueError("warmup_jobs must be between zero and jobs minus two")
    trace = generate_mm_c_jobs(
        arrival_rate=arrival_rate,
        service_rate_per_server=service_rate_per_server,
        servers=servers,
        jobs=jobs,
        seed=seed,
    )
    measurement_start = float(trace.arrivals[warmup_jobs])
    measurement_end = float(trace.arrivals[-1])
    selected = np.arange(warmup_jobs, jobs - 1)
    waits = trace.starts[selected] - trace.arrivals[selected]
    sojourn = trace.departures[selected] - trace.arrivals[selected]
    effective_arrival_rate = len(selected) / (measurement_end - measurement_start)
    time_average_number_system = _time_average_population(
        trace.arrivals,
        trace.departures,
        measurement_start,
        measurement_end,
    )
    mean_time_system = float(np.mean(sojourn))
    little_law_residual = (
        time_average_number_system - effective_arrival_rate * mean_time_system
    )
    busy_service = _busy_service_in_window(
        trace.starts,
        trace.departures,
        measurement_start,
        measurement_end,
    )
    utilization = busy_service / (
        servers * (measurement_end - measurement_start)
    )
    return QueueSimulationResult(
        jobs_measured=len(selected),
        effective_arrival_rate=effective_arrival_rate,
        utilization=float(utilization),
        mean_wait_queue_s=float(np.mean(waits)),
        mean_time_system_s=mean_time_system,
        p50_time_system_s=float(np.quantile(sojourn, 0.50)),
        p95_time_system_s=float(np.quantile(sojourn, 0.95)),
        p99_time_system_s=float(np.quantile(sojourn, 0.99)),
        time_average_number_system=time_average_number_system,
        little_law_residual=float(little_law_residual),
        measurement_start_s=measurement_start,
        measurement_end_s=measurement_end,
    )


def queue_population_samples(
    trace: QueueJobTrace,
    sample_times: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    sample_times = np.asarray(sample_times, dtype=float)
    in_system = np.empty(len(sample_times), dtype=int)
    waiting = np.empty(len(sample_times), dtype=int)
    for index, sample_time in enumerate(sample_times):
        arrived = trace.arrivals <= sample_time
        in_system[index] = int(
            np.count_nonzero(arrived & (trace.departures > sample_time))
        )
        waiting[index] = int(
            np.count_nonzero(arrived & (trace.starts > sample_time))
        )
    return in_system, waiting


def _time_average_population(
    arrivals: np.ndarray,
    departures: np.ndarray,
    start: float,
    end: float,
) -> float:
    active = int(np.count_nonzero((arrivals < start) & (departures > start)))
    events: list[tuple[float, int]] = []
    for arrival in arrivals[(arrivals >= start) & (arrivals < end)]:
        events.append((float(arrival), 1))
    for departure in departures[(departures >= start) & (departures < end)]:
        events.append((float(departure), -1))
    events.sort(key=lambda item: (item[0], item[1]))
    population = active
    previous = start
    area = 0.0
    for event_time, delta in events:
        area += population * (event_time - previous)
        population += delta
        previous = event_time
    area += population * (end - previous)
    return area / (end - start)


def _busy_service_in_window(
    starts: np.ndarray,
    departures: np.ndarray,
    start: float,
    end: float,
) -> float:
    overlap_starts = np.maximum(starts, start)
    overlap_ends = np.minimum(departures, end)
    return float(np.sum(np.maximum(0.0, overlap_ends - overlap_starts)))
