from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping

import yaml


_ALLOWED_TOPOLOGIES = {"complete", "random_regular", "erdos_renyi", "barabasi_albert", "hierarchical"}
_ALLOWED_COORDINATION = {"independent", "pairwise", "coalition", "hierarchical"}
_ALLOWED_CONSISTENCY = {"global_linearizable", "shard_linearizable", "causal", "eventual"}
_ALLOWED_SEGMENTATION = {"none", "flat_tenancy", "partition", "dynamic_microsegmentation", "degree_cap"}
_ALLOWED_TRACE = {"metrics", "summary", "security", "full"}


@dataclass(frozen=True, slots=True)
class SimulationConfig:
    """Validated, hashable configuration for one deterministic simulation run."""

    scenario_name: str = "mixed-baseline"
    seed: int = 20260819
    n_agents: int = 100
    duration_s: float = 120.0
    task_arrival_rate_per_agent_hz: float = 0.05
    task_service_rate_per_agent_hz: float = 1.0
    task_deadline_s: float = 5.0
    task_message_bytes: int = 1_024
    control_servers: int = 8
    control_service_rate_per_server_hz: float = 10.0
    control_replication: int = 3
    communication_topology: str = "random_regular"
    authorization_topology: str = "hierarchical"
    random_regular_degree: int = 4
    erdos_renyi_p: float | None = None
    barabasi_albert_m: int = 2
    hierarchy_span: int = 8
    coordination_regime: str = "hierarchical"
    consistency_regime: str = "shard_linearizable"
    segmentation_policy: str = "partition"
    segmentation_partitions: int = 8
    authorization_degree_cap: int = 8
    gossip_enabled: bool = True
    gossip_start_s: float = 5.0
    gossip_fanout: int = 2
    gossip_round_interval_s: float = 0.75
    gossip_loss_probability: float = 0.01
    false_permit_probability: float = 0.0
    false_deny_probability: float = 0.001
    telemetry_rate_bps_per_agent: float = 2_000.0
    telemetry_compression_ratio: float = 0.35
    credential_ttl_s: float = 300.0
    credential_renewal_jitter_fraction: float = 0.10
    security_enabled: bool = True
    infection_rate_per_edge_hz: float = 0.02
    detection_rate_hz: float = 0.40
    recovery_rate_hz: float = 0.20
    security_round_s: float = 1.0
    boundary_traversal_probability: float = 0.05
    attack_start_s: float | None = 30.0
    initial_compromised_agents: tuple[int, ...] = (0,)
    clock_uncertainty_s: float = 1e-6
    timing_denial_start_s: float | None = 75.0
    timing_update_interval_s: float = 5.0
    holdover_fractional_frequency_error: float = 1e-9
    geographic_diameter_km: float = 4_500.0
    mass_revocation_start_s: float | None = 90.0
    mass_revocation_fraction: float = 0.10
    credential_issuance_capacity_hz: float = 100.0
    snapshot_interval_events: int = 250
    integrity_hash_interval_events: int = 50
    trace_level: str = "summary"
    max_events: int = 2_000_000
    output_dir: str = "results"
    provenance: str = "notional"
    tags: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.n_agents < 1:
            raise ValueError("n_agents must be at least 1")
        if self.duration_s <= 0:
            raise ValueError("duration_s must be positive")
        if self.control_servers < 1 or self.control_service_rate_per_server_hz <= 0:
            raise ValueError("control-plane capacity must be positive")
        if self.task_arrival_rate_per_agent_hz < 0 or self.task_service_rate_per_agent_hz <= 0:
            raise ValueError("task rates must be nonnegative and service rate positive")
        if self.task_deadline_s <= 0 or self.task_message_bytes < 1:
            raise ValueError("task deadline and message size must be positive")
        if self.communication_topology not in _ALLOWED_TOPOLOGIES:
            raise ValueError(f"unsupported communication topology: {self.communication_topology}")
        if self.authorization_topology not in _ALLOWED_TOPOLOGIES:
            raise ValueError(f"unsupported authorization topology: {self.authorization_topology}")
        if self.coordination_regime not in _ALLOWED_COORDINATION:
            raise ValueError(f"unsupported coordination regime: {self.coordination_regime}")
        if self.consistency_regime not in _ALLOWED_CONSISTENCY:
            raise ValueError(f"unsupported consistency regime: {self.consistency_regime}")
        if self.segmentation_policy not in _ALLOWED_SEGMENTATION:
            raise ValueError(f"unsupported segmentation policy: {self.segmentation_policy}")
        if self.trace_level not in _ALLOWED_TRACE:
            raise ValueError(f"unsupported trace level: {self.trace_level}")
        if self.hierarchy_span < 2:
            raise ValueError("hierarchy_span must be at least 2")
        if self.random_regular_degree < 0:
            raise ValueError("random_regular_degree must be nonnegative")
        if self.barabasi_albert_m < 1:
            raise ValueError("barabasi_albert_m must be positive")
        if self.segmentation_partitions < 1:
            raise ValueError("segmentation_partitions must be positive")
        if self.credential_ttl_s <= 0 or self.credential_issuance_capacity_hz <= 0:
            raise ValueError("credential TTL and issuance capacity must be positive")
        if not 0.0 <= self.credential_renewal_jitter_fraction < 1.0:
            raise ValueError("credential_renewal_jitter_fraction must be within [0, 1)")
        if self.gossip_fanout < 1 or self.gossip_round_interval_s <= 0:
            raise ValueError("gossip fanout and interval must be positive")
        if (
            self.security_round_s <= 0
            or self.infection_rate_per_edge_hz < 0
            or self.detection_rate_hz <= 0
            or self.recovery_rate_hz <= 0
        ):
            raise ValueError("infection rate must be nonnegative and security timing rates positive")
        if self.holdover_fractional_frequency_error < 0:
            raise ValueError("holdover_fractional_frequency_error must be nonnegative")
        if self.geographic_diameter_km < 0:
            raise ValueError("geographic_diameter_km must be nonnegative")
        if self.timing_update_interval_s <= 0:
            raise ValueError("timing_update_interval_s must be positive")
        for event_time_name in ("gossip_start_s", "attack_start_s", "timing_denial_start_s", "mass_revocation_start_s"):
            event_time = getattr(self, event_time_name)
            if event_time is not None and event_time < 0:
                raise ValueError(f"{event_time_name} must be nonnegative when provided")
        for name in (
            "false_permit_probability",
            "false_deny_probability",
            "telemetry_compression_ratio",
            "boundary_traversal_probability",
            "gossip_loss_probability",
            "mass_revocation_fraction",
        ):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be within [0, 1]")
        if self.snapshot_interval_events < 1 or self.integrity_hash_interval_events < 1:
            raise ValueError("snapshot and integrity intervals must be positive")
        if self.max_events < 1:
            raise ValueError("max_events must be positive")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["initial_compromised_agents"] = list(self.initial_compromised_agents)
        data["tags"] = list(self.tags)
        return data

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "SimulationConfig":
        values = dict(data)
        if "initial_compromised_agents" in values:
            values["initial_compromised_agents"] = tuple(values["initial_compromised_agents"])
        if "tags" in values:
            values["tags"] = tuple(values["tags"])
        return cls(**values)

    @property
    def configuration_hash(self) -> str:
        canonical = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]

    @property
    def run_id(self) -> str:
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in self.scenario_name.lower())
        return f"{safe}-{self.configuration_hash}-s{self.seed}"


def load_config(path: str | Path) -> SimulationConfig:
    source = Path(path)
    with source.open("r", encoding="utf-8") as stream:
        if source.suffix.lower() in {".yaml", ".yml"}:
            data = yaml.safe_load(stream)
        elif source.suffix.lower() == ".json":
            data = json.load(stream)
        else:
            raise ValueError(f"unsupported configuration format: {source.suffix}")
    if not isinstance(data, Mapping):
        raise ValueError("configuration root must be a mapping")
    return SimulationConfig.from_mapping(data)


def save_config(config: SimulationConfig, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as stream:
        yaml.safe_dump(config.to_dict(), stream, sort_keys=True)
