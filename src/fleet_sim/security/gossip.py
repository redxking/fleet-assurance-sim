"""Discrete-round gossip dissemination model."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from fleet_sim.graphs import GraphBundle


@dataclass(frozen=True, slots=True)
class GossipResult:
    rounds_executed: int
    coverage_by_round: tuple[float, ...]
    informed_round: tuple[int | None, ...]
    messages_sent: int
    reached_all: bool

    def rounds_to_coverage(self, fraction: float) -> int | None:
        if not 0 < fraction <= 1:
            raise ValueError("fraction must be in (0, 1]")
        for round_index, coverage in enumerate(self.coverage_by_round):
            if coverage >= fraction:
                return round_index
        return None


def _contacts(
    bundle: GraphBundle,
    node: int,
    fanout: int,
    rng: np.random.Generator,
) -> list[int]:
    if bundle.n <= 1:
        return []
    if bundle.graph is None and bundle.topology == "complete":
        sample_size = min(fanout, bundle.n - 1)
        raw = rng.choice(bundle.n - 1, size=sample_size, replace=False)
        return [int(value + (value >= node)) for value in raw]
    neighbors = np.fromiter(bundle.neighbors(node), dtype=int)
    if len(neighbors) == 0:
        return []
    size = min(fanout, len(neighbors))
    return [int(value) for value in rng.choice(neighbors, size=size, replace=False)]


def simulate_gossip(
    bundle: GraphBundle,
    *,
    seed: int,
    source: int = 0,
    fanout: int = 2,
    protocol: str = "push_pull",
    loss_probability: float = 0.0,
    max_rounds: int | None = None,
) -> GossipResult:
    if not 0 <= source < bundle.n:
        raise ValueError("source is outside the graph")
    if fanout < 1:
        raise ValueError("fanout must be positive")
    if protocol not in {"push", "pull", "push_pull"}:
        raise ValueError("protocol must be push, pull, or push_pull")
    if not 0 <= loss_probability <= 1:
        raise ValueError("loss_probability must be in [0, 1]")

    rng = np.random.Generator(np.random.PCG64DXSM(seed))
    informed = {source}
    informed_round: list[int | None] = [None] * bundle.n
    informed_round[source] = 0
    coverage = [1.0 / bundle.n]
    messages = 0
    limit = max_rounds if max_rounds is not None else max(4, int(8 * np.ceil(np.log2(bundle.n + 1))))

    for round_index in range(1, limit + 1):
        old_informed = set(informed)
        newly_informed: set[int] = set()

        if protocol in {"push", "push_pull"}:
            for node in sorted(old_informed):
                for target in _contacts(bundle, node, fanout, rng):
                    messages += 1
                    if rng.random() >= loss_probability and target not in old_informed:
                        newly_informed.add(target)

        if protocol in {"pull", "push_pull"}:
            for node in range(bundle.n):
                if node in old_informed:
                    continue
                for target in _contacts(bundle, node, fanout, rng):
                    messages += 1
                    if rng.random() >= loss_probability and target in old_informed:
                        newly_informed.add(node)
                        break

        for node in newly_informed:
            if informed_round[node] is None:
                informed_round[node] = round_index
        informed.update(newly_informed)
        coverage.append(len(informed) / bundle.n)
        if len(informed) == bundle.n:
            return GossipResult(round_index, tuple(coverage), tuple(informed_round), messages, True)
        if not newly_informed and protocol == "push" and bundle.graph is not None:
            # A push-only run can stall temporarily, so do not terminate early.
            pass

    return GossipResult(limit, tuple(coverage), tuple(informed_round), messages, len(informed) == bundle.n)


def simulate_complete_gossip_mean_field(
    n_agents: int,
    *,
    seed: int,
    fanout: int = 2,
    protocol: str = "push_pull",
    loss_probability: float = 0.0,
    max_rounds: int | None = None,
) -> GossipResult:
    """Fast state-count approximation for complete-graph gossip.

    The process preserves the expected per-node contact probability for the
    complete graph, then samples the number of newly informed nodes from a
    binomial distribution. It does not preserve target-to-target correlation.
    It must be validated against the exact agent-level model before use at a
    larger N.
    """

    if n_agents < 1:
        raise ValueError("n_agents must be positive")
    if fanout < 1:
        raise ValueError("fanout must be positive")
    if protocol not in {"push", "pull", "push_pull"}:
        raise ValueError("protocol must be push, pull, or push_pull")
    if not 0 <= loss_probability <= 1:
        raise ValueError("loss_probability must be in [0, 1]")
    if n_agents == 1:
        return GossipResult(0, (1.0,), (0,), 0, True)

    rng = np.random.Generator(np.random.PCG64DXSM(seed))
    informed = 1
    coverage = [1.0 / n_agents]
    messages = 0
    informed_round: list[int | None] = [0] + [None] * (n_agents - 1)
    limit = max_rounds if max_rounds is not None else max(
        4, int(8 * np.ceil(np.log2(n_agents + 1)))
    )
    effective_fanout = min(fanout, n_agents - 1)

    for round_index in range(1, limit + 1):
        uninformed = n_agents - informed
        if uninformed <= 0:
            return GossipResult(
                round_index - 1,
                tuple(coverage),
                tuple(informed_round),
                messages,
                True,
            )

        p_push = 0.0
        p_pull = 0.0
        if protocol in {"push", "push_pull"}:
            p_single_sender_misses = 1.0 - effective_fanout / (n_agents - 1)
            p_push = 1.0 - p_single_sender_misses**informed
            messages += informed * effective_fanout
        if protocol in {"pull", "push_pull"}:
            probability_no_informed = 1.0
            available_uninformed_peers = max(0, n_agents - 1 - informed)
            for draw in range(effective_fanout):
                numerator = max(0, available_uninformed_peers - draw)
                denominator = n_agents - 1 - draw
                probability_no_informed *= numerator / denominator
            p_pull = 1.0 - probability_no_informed
            messages += uninformed * effective_fanout

        contact_probability = 1.0 - (1.0 - p_push) * (1.0 - p_pull)
        success_probability = contact_probability * (1.0 - loss_probability)
        newly = int(rng.binomial(uninformed, min(1.0, max(0.0, success_probability))))
        if newly == 0 and success_probability > 0:
            # Preserve liveness in the finite approximation without inventing
            # more than one contact outcome.
            newly = int(rng.random() < 1.0 - (1.0 - success_probability) ** uninformed)
        start = informed
        informed += newly
        for node in range(start, min(informed, n_agents)):
            informed_round[node] = round_index
        coverage.append(informed / n_agents)
        if informed >= n_agents:
            return GossipResult(
                round_index,
                tuple(coverage),
                tuple(informed_round),
                messages,
                True,
            )

    return GossipResult(
        limit,
        tuple(coverage),
        tuple(informed_round),
        messages,
        informed >= n_agents,
    )
