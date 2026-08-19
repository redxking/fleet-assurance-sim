"""Concrete message, byte, operation, and latency accounting for consensus families."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ConsensusCost:
    protocol: str
    committee_size: int
    messages: int
    bytes_transmitted: int
    signature_generations: int
    signature_verifications: int
    sequential_message_steps: int
    view_change: bool = False


def pbft_class_cost(
    committee_size: int,
    *,
    payload_bytes: int = 1_024,
    digest_message_bytes: int = 256,
    signature_bytes: int = 64,
    include_client_replies: bool = True,
    view_change: bool = False,
) -> ConsensusCost:
    """PBFT-class pattern: pre-prepare, all-to-all prepare, all-to-all commit."""

    n = committee_size
    if n < 1:
        raise ValueError("committee_size must be positive")
    pre_prepare = max(0, n - 1)
    prepare = n * max(0, n - 1)
    commit = n * max(0, n - 1)
    replies = n if include_client_replies else 0
    normal_messages = pre_prepare + prepare + commit + replies
    normal_bytes = (
        pre_prepare * (payload_bytes + signature_bytes)
        + (prepare + commit + replies) * (digest_message_bytes + signature_bytes)
    )
    signatures = pre_prepare + prepare + commit + replies
    verifications = normal_messages * max(1, n - 1)
    sequential_steps = 4 if include_client_replies else 3

    if view_change and n > 1:
        view_change_messages = (n - 1) + (n - 1)
        view_change_bytes = view_change_messages * (digest_message_bytes + signature_bytes)
        normal_messages += view_change_messages
        normal_bytes += view_change_bytes
        signatures += view_change_messages
        verifications += (n - 1) ** 2
        sequential_steps += 2

    return ConsensusCost(
        "pbft_class",
        n,
        normal_messages,
        normal_bytes,
        signatures,
        verifications,
        sequential_steps,
        view_change,
    )


def threshold_leader_cost(
    committee_size: int,
    *,
    payload_bytes: int = 1_024,
    vote_bytes: int = 128,
    quorum_certificate_bytes: int = 256,
    view_change: bool = False,
) -> ConsensusCost:
    n = committee_size
    if n < 1:
        raise ValueError("committee_size must be positive")
    proposal = max(0, n - 1)
    votes = max(0, n - 1)
    certificate = max(0, n - 1)
    messages = proposal + votes + certificate
    bytes_transmitted = (
        proposal * payload_bytes + votes * vote_bytes + certificate * quorum_certificate_bytes
    )
    signature_generations = votes + 1
    signature_verifications = votes + certificate
    steps = 3
    if view_change and n > 1:
        messages += 2 * (n - 1)
        bytes_transmitted += 2 * (n - 1) * quorum_certificate_bytes
        signature_generations += n - 1
        signature_verifications += (n - 1) ** 2
        steps += 2
    return ConsensusCost(
        "threshold_leader",
        n,
        messages,
        bytes_transmitted,
        signature_generations,
        signature_verifications,
        steps,
        view_change,
    )


def bounded_committee_cost(
    fleet_size: int,
    committee_size: int,
    *,
    dissemination_fanout: int = 8,
    payload_bytes: int = 1_024,
) -> ConsensusCost:
    if fleet_size < 1 or committee_size < 1 or committee_size > fleet_size:
        raise ValueError("invalid fleet or committee size")
    committee = threshold_leader_cost(committee_size, payload_bytes=payload_bytes)
    recipients = fleet_size - committee_size
    dissemination_messages = recipients
    dissemination_bytes = recipients * 256
    return ConsensusCost(
        "bounded_committee",
        committee_size,
        committee.messages + dissemination_messages,
        committee.bytes_transmitted + dissemination_bytes,
        committee.signature_generations,
        committee.signature_verifications + recipients,
        committee.sequential_message_steps + (1 if recipients else 0),
        False,
    )


def fault_bounds(committee_size: int) -> dict[str, int]:
    if committee_size < 1:
        raise ValueError("committee_size must be positive")
    return {
        "max_byzantine_f": (committee_size - 1) // 3,
        "max_crash_f": (committee_size - 1) // 2,
    }
