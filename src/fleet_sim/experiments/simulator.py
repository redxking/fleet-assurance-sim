"""Integrated deterministic fleet simulation and artifact production."""

from __future__ import annotations

import json
import math
import platform
import shutil
import time
from collections import Counter, deque
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import networkx as nx
import numpy as np
import pandas as pd
import yaml

from fleet_sim.analysis.cost import practical_cost_per_useful_task, practical_energy_per_useful_task
from fleet_sim.config import SimulationConfig
from fleet_sim.control_plane.queueing import erlang_c, minimum_servers
from fleet_sim.control_plane.service_center import ServiceCenter, ServiceRequest
from fleet_sim.credentials import certificate_issuance_rate, pairwise_key_count, size_issuer
from fleet_sim.graphs import GraphBundle, apply_segmentation, build_graph, graph_metrics
from fleet_sim.model.agent import AgentHealth
from fleet_sim.model.engine import DeterministicEventEngine
from fleet_sim.model.events import Event, EventLog
from fleet_sim.model.replay import ReplayEngine, write_snapshots
from fleet_sim.model.rng import RandomStreams
from fleet_sim.model.state import FleetState
from fleet_sim.model.task import Task, TaskStatus
from fleet_sim.provenance.manifest import capture_manifest, write_manifest
from fleet_sim.security.epidemic import epidemic_stability_product
from fleet_sim.telemetry import hierarchical_telemetry
from fleet_sim.timing import fiber_propagation_delay, holdover_uncertainty, landauer_energy


@dataclass(frozen=True, slots=True)
class SimulationArtifacts:
    run_id: str
    bundle_dir: Path
    event_log_path: Path
    summary_path: Path
    metrics_path: Path
    manifest_path: Path
    replay_html_path: Path | None
    final_state_hash: str
    replay_state_hash: str
    event_log_digest: str


class FleetSimulator:
    """Version-zero integrated model for Stage 0 verification and visual replay.

    The model is deliberately stylized. All default parameters are notional. The
    same FleetState.apply transition function is used during execution and replay.
    """

    def __init__(self, config: SimulationConfig, repository_root: str | Path) -> None:
        self.config = config
        self.repository_root = Path(repository_root)
        self.engine = DeterministicEventEngine()
        self.streams = RandomStreams(config.seed)
        self.run_id = config.run_id
        self.configuration_hash = config.configuration_hash
        self.agent_ids = [f"agent-{index:06d}" for index in range(config.n_agents)]
        self.initial_state = FleetState.initial(
            self.agent_ids,
            hierarchy_span=config.hierarchy_span,
            timing_uncertainty_s=config.clock_uncertainty_s,
        )
        self.state = FleetState.from_dict(self.initial_state.to_dict())
        self.log = EventLog()
        self.logical_time = 0
        self.started_unix = 0.0
        self.ended_unix = 0.0

        communication_seed = int(
            self.streams.rng("graph_communication").integers(0, 2**32 - 1)
        )
        authorization_seed = int(
            self.streams.rng("graph_authorization").integers(0, 2**32 - 1)
        )
        self.communication_graph = build_graph(
            config.n_agents,
            config.communication_topology,
            seed=communication_seed,
            degree=config.random_regular_degree,
            probability=config.erdos_renyi_p,
            attachment=config.barabasi_albert_m,
            span=config.hierarchy_span,
        )
        authorization_base = build_graph(
            config.n_agents,
            config.authorization_topology,
            seed=authorization_seed,
            degree=config.random_regular_degree,
            probability=config.erdos_renyi_p,
            attachment=config.barabasi_albert_m,
            span=config.hierarchy_span,
        )
        self.authorization_graph = apply_segmentation(
            authorization_base,
            config.segmentation_policy,
            partitions=config.segmentation_partitions,
            degree_cap=config.authorization_degree_cap,
        )

        self.tasks: dict[str, Task] = {}
        self.task_counter = 0
        self.agent_busy: set[str] = set()
        self.agent_queues: dict[str, deque[str]] = {agent_id: deque() for agent_id in self.agent_ids}
        self.authorization_sojourn_s: list[float] = []
        self.task_latencies_s: list[float] = []
        self.useful_latencies_s: list[float] = []
        self.authorization_arrival: dict[str, float] = {}

        self._control_last_time = 0.0
        self._control_queue = 0
        self._control_busy = 0
        self._control_system_area = 0.0
        self._control_busy_area = 0.0

        self.gossip_informed: set[int] = set()
        self.gossip_round = 0
        self.gossip_messages = 0
        self.model_bytes_transmitted = 0
        self.gossip_max_rounds = max(8, int(8 * math.ceil(math.log2(config.n_agents + 1))))

        self.security_infected: set[int] = set()
        self.security_removed: set[int] = set()
        self.security_round = 0
        self.unique_compromised: set[int] = set()
        self.max_active_compromised = 0
        self.compromise_time: dict[int, float] = {}
        self.detection_time: dict[int, float] = {}
        self.containment_time: dict[int, float] = {}

        self.auth_center = ServiceCenter(
            name="authorization",
            engine=self.engine,
            servers=config.control_servers,
            service_rate=config.control_service_rate_per_server_hz,
            rng=self.streams.rng("control_service"),
            on_queue_change=self._queue_change,
        )

    @staticmethod
    def _agent_id(index: int) -> str:
        return f"agent-{index:06d}"

    def _advance_control_areas(self, now: float) -> None:
        delta = max(0.0, now - self._control_last_time)
        self._control_system_area += (self._control_queue + self._control_busy) * delta
        self._control_busy_area += self._control_busy * delta
        self._control_last_time = now

    def _queue_change(self, name: str, queue_length: int, busy: int, servers: int) -> None:
        self._advance_control_areas(self.engine.now)
        self._control_queue = queue_length
        self._control_busy = busy
        self.emit(
            "QUEUE_SAMPLE",
            source_id=f"service:{name}",
            resource_id=f"queue:{name}",
            metadata={
                "service_center": name,
                "queue_length": queue_length,
                "busy_servers": busy,
                "servers": servers,
                "utilization": busy / servers,
            },
        )

    def emit(
        self,
        event_type: str,
        *,
        parent_event_id: str | None = None,
        source_id: str | None = None,
        destination_id: str | None = None,
        resource_id: str | None = None,
        graph_layer: str | None = None,
        task_id: str | None = None,
        coalition_id: str | None = None,
        message_id: str | None = None,
        message_bytes: int = 0,
        capability_id: str | None = None,
        authorization_decision: str | None = None,
        credential_epoch: int | None = None,
        severity: str = "info",
        timing_uncertainty: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Event:
        if len(self.log) >= self.config.max_events:
            raise RuntimeError(f"max_events={self.config.max_events} exceeded")
        self.logical_time += 1
        integrity_checkpoint = (
            self.logical_time == 1
            or self.logical_time % self.config.integrity_hash_interval_events == 0
            or event_type == "SIMULATION_END"
        )
        before_hash = self.state.state_hash() if integrity_checkpoint else None
        event = Event(
            run_id=self.run_id,
            configuration_hash=self.configuration_hash,
            seed=self.config.seed,
            event_id=f"{self.run_id}:evt-{self.logical_time:010d}",
            parent_event_id=parent_event_id,
            simulation_time=round(float(self.engine.now), 9),
            logical_time=self.logical_time,
            event_type=event_type,
            source_id=source_id,
            destination_id=destination_id,
            resource_id=resource_id,
            graph_layer=graph_layer,
            task_id=task_id,
            coalition_id=coalition_id,
            message_id=message_id,
            message_bytes=message_bytes,
            capability_id=capability_id,
            authorization_decision=authorization_decision,
            credential_epoch=credential_epoch,
            state_before=before_hash,
            severity=severity,
            policy_version="v0.1",
            timing_uncertainty=timing_uncertainty,
            provenance_tag=self.config.provenance,
            metadata=metadata or {},
        )
        self.state.apply(event)
        event = replace(
            event,
            state_after=self.state.state_hash() if integrity_checkpoint else None,
        )
        self.log.append(event)
        return event

    def _schedule_first_task(self) -> None:
        rate = self.config.n_agents * self.config.task_arrival_rate_per_agent_hz
        if rate <= 0:
            return
        delay = float(self.streams.rng("workload_arrival").exponential(1.0 / rate))
        if self.engine.now + delay <= self.config.duration_s:
            self.engine.schedule_after(delay, self._task_arrival, label="workload:arrival")

    def _task_arrival(self) -> None:
        self.task_counter += 1
        task_id = f"task-{self.task_counter:09d}"
        target_index = int(self.streams.rng("workload_target").integers(0, self.config.n_agents))
        target = self._agent_id(target_index)
        task = Task(
            task_id=task_id,
            arrival_time=self.engine.now,
            deadline_s=self.config.task_deadline_s,
            assigned_agent=target,
        )
        task.status = TaskStatus.AUTH_QUEUED
        self.tasks[task_id] = task
        self.authorization_arrival[task_id] = self.engine.now
        self.model_bytes_transmitted += self.config.task_message_bytes
        arrival = self.emit(
            "TASK_ARRIVAL",
            source_id="workload-generator",
            destination_id=target,
            task_id=task_id,
            message_bytes=self.config.task_message_bytes,
            capability_id="task.execute",
            metadata={"deadline_absolute_s": self.engine.now + self.config.task_deadline_s},
        )
        self.emit(
            "AUTH_REQUEST",
            parent_event_id=arrival.event_id,
            source_id=target,
            destination_id="service:authorization",
            resource_id=target,
            task_id=task_id,
            capability_id="task.execute",
        )

        def completed(service_time: float, request_task: str = task_id) -> None:
            self._authorization_complete(request_task, service_time)

        self.auth_center.submit(
            ServiceRequest(task_id, self.engine.now, completed)
        )
        self._schedule_first_task()

    def _authorization_complete(self, task_id: str, service_time: float) -> None:
        task = self.tasks[task_id]
        agent_state = self.state.agents[task.assigned_agent]
        authorization_rng = self.streams.rng("authorization")
        policy_permit = agent_state.health not in {
            AgentHealth.ISOLATED,
            AgentHealth.REVOKED,
            AgentHealth.TERMINATED,
        }
        false_deny = bool(
            policy_permit
            and authorization_rng.random() < self.config.false_deny_probability
        )
        false_permit = bool(
            not policy_permit
            and authorization_rng.random() < self.config.false_permit_probability
        )
        permit = (policy_permit and not false_deny) or false_permit
        task.authorization_time = self.engine.now
        self.authorization_sojourn_s.append(self.engine.now - self.authorization_arrival[task_id])
        decision = self.emit(
            "AUTH_DECISION",
            source_id="service:authorization",
            destination_id=task.assigned_agent,
            task_id=task_id,
            capability_id="task.execute",
            authorization_decision="permit" if permit else "deny",
            severity="critical" if false_permit else ("info" if permit else "warning"),
            metadata={
                "service_time_s": service_time,
                "policy_permit": policy_permit,
                "false_deny": false_deny,
                "false_permit": false_permit,
                "agent_health": agent_state.health.value,
            },
        )
        if not permit:
            task.status = TaskStatus.DENIED
            self.emit(
                "TASK_FAILED",
                parent_event_id=decision.event_id,
                source_id="service:authorization",
                destination_id=task.assigned_agent,
                task_id=task_id,
                severity="warning",
                metadata={"reason": "authorization_denied"},
            )
            return
        task.status = TaskStatus.AUTHORIZED
        self._enqueue_agent_task(task_id, decision.event_id)

    def _enqueue_agent_task(self, task_id: str, parent_event_id: str) -> None:
        task = self.tasks[task_id]
        target = task.assigned_agent
        self.agent_queues[target].append(task_id)
        task.metadata["dispatch_parent"] = parent_event_id
        if target not in self.agent_busy:
            self._start_next_agent_task(target)

    def _start_next_agent_task(self, agent_id: str) -> None:
        if not self.agent_queues[agent_id]:
            self.agent_busy.discard(agent_id)
            return
        health = self.state.agents[agent_id].health
        task_id = self.agent_queues[agent_id].popleft()
        task = self.tasks[task_id]
        if health in {AgentHealth.ISOLATED, AgentHealth.REVOKED, AgentHealth.TERMINATED}:
            task.status = TaskStatus.FAILED
            self.emit(
                "TASK_FAILED",
                source_id=agent_id,
                destination_id="mission-output",
                task_id=task_id,
                severity="warning",
                metadata={"reason": f"agent_{health.value}"},
            )
            self._start_next_agent_task(agent_id)
            return

        self.agent_busy.add(agent_id)
        task.status = TaskStatus.EXECUTING
        dispatch_parent = task.metadata.get("dispatch_parent")
        dispatch = self.emit(
            "TASK_DISPATCH",
            parent_event_id=(str(dispatch_parent) if dispatch_parent is not None else None),
            source_id="service:dispatcher",
            destination_id=agent_id,
            task_id=task_id,
            capability_id="task.execute",
        )
        service_time = float(
            self.streams.rng("agent_service").exponential(
                1.0 / self.config.task_service_rate_per_agent_hz
            )
        )

        def complete(
            completed_task: str = task_id,
            completed_agent: str = agent_id,
            parent: str = dispatch.event_id,
        ) -> None:
            self._task_complete(completed_task, completed_agent, parent)

        self.engine.schedule_after(service_time, complete, label=f"task:{task_id}:complete")

    def _task_complete(self, task_id: str, agent_id: str, parent_event_id: str) -> None:
        task = self.tasks[task_id]
        task.completion_time = self.engine.now
        task.compromised_result = self.state.agents[agent_id].health in {
            AgentHealth.COMPROMISED,
            AgentHealth.SUSPECTED,
        }
        task.status = TaskStatus.COMPLETE
        latency = self.engine.now - task.arrival_time
        self.task_latencies_s.append(latency)
        if task.useful:
            self.useful_latencies_s.append(latency)
        self.emit(
            "TASK_COMPLETE",
            parent_event_id=parent_event_id,
            source_id=agent_id,
            destination_id="mission-output",
            task_id=task_id,
            severity="info" if task.useful else "warning",
            metadata={
                "useful": task.useful,
                "latency_s": latency,
                "deadline_s": task.deadline_s,
                "compromised_result": task.compromised_result,
            },
        )
        self.agent_busy.discard(agent_id)
        self._start_next_agent_task(agent_id)

    def _sample_neighbors(self, bundle: GraphBundle, node: int, count: int | None = None) -> list[int]:
        rng = self.streams.rng("network")
        if bundle.graph is None and bundle.topology == "complete":
            available = bundle.n - 1
            if available <= 0:
                return []
            size = available if count is None else min(count, available)
            raw = rng.choice(available, size=size, replace=False)
            return [int(value + (value >= node)) for value in np.atleast_1d(raw)]
        neighbors = np.fromiter(bundle.neighbors(node), dtype=int)
        if len(neighbors) == 0:
            return []
        size = len(neighbors) if count is None else min(count, len(neighbors))
        if size == len(neighbors):
            return [int(value) for value in neighbors]
        return [int(value) for value in rng.choice(neighbors, size=size, replace=False)]

    def _start_gossip(self) -> None:
        self.gossip_informed = {0}
        self.emit(
            "GOSSIP_SEED",
            source_id="service:dissemination",
            destination_id=self._agent_id(0),
            graph_layer="communication",
            metadata={"round": 0, "coverage": 1.0 / self.config.n_agents},
        )
        self.engine.schedule_after(
            self.config.gossip_round_interval_s,
            self._gossip_round,
            label="gossip:round",
        )

    def _gossip_round(self) -> None:
        self.gossip_round += 1
        rng = self.streams.rng("network")
        old = set(self.gossip_informed)
        newly: set[int] = set()
        transmissions = 0
        for sender in sorted(old):
            targets = self._sample_neighbors(
                self.communication_graph, sender, self.config.gossip_fanout
            )
            for target in targets:
                transmissions += 1
                self.gossip_messages += 1
                self.model_bytes_transmitted += 512
                lost = rng.random() < self.config.gossip_loss_probability
                if self.config.trace_level == "full":
                    self.emit(
                        "GOSSIP_MESSAGE",
                        source_id=self._agent_id(sender),
                        destination_id=self._agent_id(target),
                        graph_layer="communication",
                        message_id=f"gossip-{self.gossip_round:05d}-{sender:06d}-{target:06d}",
                        message_bytes=512,
                        severity="warning" if lost else "info",
                        metadata={"round": self.gossip_round, "lost": bool(lost)},
                    )
                if not lost and target not in old:
                    newly.add(target)
        for target in sorted(newly):
            self.emit(
                "GOSSIP_INFORMED",
                source_id="service:dissemination",
                destination_id=self._agent_id(target),
                graph_layer="communication",
                metadata={"round": self.gossip_round},
            )
        self.gossip_informed.update(newly)
        coverage = len(self.gossip_informed) / self.config.n_agents
        self.emit(
            "GOSSIP_ROUND",
            source_id="service:dissemination",
            graph_layer="communication",
            metadata={
                "round": self.gossip_round,
                "coverage": coverage,
                "newly_informed": len(newly),
                "transmissions": transmissions,
            },
        )
        if coverage < 1.0 and self.gossip_round < self.gossip_max_rounds:
            self.engine.schedule_after(
                self.config.gossip_round_interval_s,
                self._gossip_round,
                label="gossip:round",
            )

    def _start_security_incident(self) -> None:
        for node in sorted(set(self.config.initial_compromised_agents)):
            if 0 <= node < self.config.n_agents:
                self.security_infected.add(node)
                self.unique_compromised.add(node)
                self.compromise_time.setdefault(node, self.engine.now)
                self.emit(
                    "COMPROMISE",
                    source_id="adversary",
                    destination_id=self._agent_id(node),
                    graph_layer="attack_reachability",
                    severity="critical",
                    metadata={"initial_seed": True, "round": 0},
                )
        self.max_active_compromised = max(self.max_active_compromised, len(self.security_infected))
        if self.security_infected:
            self.engine.schedule_after(
                self.config.security_round_s,
                self._security_round,
                label="security:round",
            )

    def _security_round(self) -> None:
        self.security_round += 1
        compromise_rng = self.streams.rng("compromise")
        detection_rng = self.streams.rng("detection")
        dt = self.config.security_round_s
        base_edge_infection_probability = (
            1.0 - math.exp(-self.config.infection_rate_per_edge_hz * dt)
        )
        gateway_effective_infection_probability = (
            base_edge_infection_probability * self.config.boundary_traversal_probability
        )
        p_detect = 1.0 - math.exp(-self.config.detection_rate_hz * dt)
        newly: set[int] = set()

        for source in sorted(self.security_infected):
            neighbors = self._sample_neighbors(self.authorization_graph, source)
            for target in neighbors:
                if target in self.security_infected or target in self.security_removed or target in newly:
                    continue
                edge_data: dict[str, Any] = {}
                if self.authorization_graph.graph is not None:
                    edge_data = dict(
                        self.authorization_graph.graph.get_edge_data(source, target, default={})
                    )
                is_assurance_boundary = edge_data.get("assurance_boundary") == "gateway"
                p_infect = (
                    gateway_effective_infection_probability
                    if is_assurance_boundary
                    else base_edge_infection_probability
                )
                if compromise_rng.random() < p_infect:
                    newly.add(target)
                    traversal_event_id: str | None = None
                    if is_assurance_boundary and self.config.trace_level in {"security", "full"}:
                        traversal = self.emit(
                            "AUTHORIZATION_BOUNDARY_TRAVERSAL",
                            source_id=self._agent_id(source),
                            destination_id=self._agent_id(target),
                            graph_layer="authorization",
                            severity="critical",
                            metadata={
                                "round": self.security_round,
                                "base_edge_probability": base_edge_infection_probability,
                                "boundary_failure_probability": self.config.boundary_traversal_probability,
                                "effective_probability": p_infect,
                                "boundary_type": "gateway",
                            },
                        )
                        traversal_event_id = traversal.event_id
                    self.emit(
                        "COMPROMISE",
                        parent_event_id=traversal_event_id,
                        source_id=self._agent_id(source),
                        destination_id=self._agent_id(target),
                        graph_layer="attack_reachability",
                        severity="critical",
                        metadata={
                            "round": self.security_round,
                            "assurance_boundary_crossed": is_assurance_boundary,
                            "effective_probability": p_infect,
                        },
                    )
                    self.unique_compromised.add(target)
                    self.compromise_time.setdefault(target, self.engine.now)
        self.security_infected.update(newly)

        detected = [
            node
            for node in sorted(self.security_infected)
            if detection_rng.random() < p_detect
        ]
        for node in detected:
            agent_id = self._agent_id(node)
            detection = self.emit(
                "DETECTION",
                source_id="service:detection",
                destination_id=agent_id,
                graph_layer="supervisory",
                severity="critical",
                metadata={"round": self.security_round},
            )
            self.detection_time.setdefault(node, self.engine.now)
            self.emit(
                "QUARANTINE",
                parent_event_id=detection.event_id,
                source_id="service:response",
                destination_id=agent_id,
                graph_layer="supervisory",
                severity="critical",
            )
            epoch = self.state.agents[agent_id].credential_epoch + 1
            self.emit(
                "REVOCATION",
                parent_event_id=detection.event_id,
                source_id="service:identity",
                destination_id=agent_id,
                graph_layer="authorization",
                credential_epoch=epoch,
                severity="critical",
            )
            self.security_infected.discard(node)
            self.security_removed.add(node)
            self.containment_time.setdefault(node, self.engine.now)
            recovery_delay = float(
                self.streams.rng("recovery").exponential(1.0 / self.config.recovery_rate_hz)
            )

            def recover(target_node: int = node, parent: str = detection.event_id) -> None:
                target_agent = self._agent_id(target_node)
                reissue = self.emit(
                    "CREDENTIAL_RENEWAL",
                    parent_event_id=parent,
                    source_id="service:identity",
                    destination_id=target_agent,
                    resource_id="credential-authority",
                    graph_layer="authorization",
                    credential_epoch=self.state.agents[target_agent].credential_epoch + 1,
                    metadata={"recovery_reissue": True},
                )
                self.emit(
                    "RECOVERY",
                    parent_event_id=reissue.event_id,
                    source_id="service:recovery",
                    destination_id=target_agent,
                    graph_layer="supervisory",
                    metadata={"durable_immunity": True, "credential_reissued": True},
                )

            self.engine.schedule_after(recovery_delay, recover, label=f"security:recover:{node}")

        self.max_active_compromised = max(self.max_active_compromised, len(self.security_infected))
        self.emit(
            "SECURITY_ROUND",
            source_id="service:detection",
            graph_layer="attack_reachability",
            metadata={
                "round": self.security_round,
                "active_compromised": len(self.security_infected),
                "removed": len(self.security_removed),
                "new_compromises": len(newly),
                "detections": len(detected),
                "base_edge_infection_probability": base_edge_infection_probability,
                "gateway_boundary_failure_probability": self.config.boundary_traversal_probability,
                "gateway_effective_infection_probability": gateway_effective_infection_probability,
                "p_detect": p_detect,
            },
        )
        if self.security_infected and self.engine.now + dt <= self.config.duration_s:
            self.engine.schedule_after(dt, self._security_round, label="security:round")

    def _timing_denial_start(self) -> None:
        self.emit(
            "TIMING_DENIAL_START",
            source_id="adversary",
            resource_id="timing-source:primary",
            graph_layer="dependency",
            severity="critical",
            timing_uncertainty=self.config.clock_uncertainty_s,
        )
        self._timing_update()

    def _timing_update(self) -> None:
        if self.config.timing_denial_start_s is None:
            return
        elapsed = max(0.0, self.engine.now - self.config.timing_denial_start_s)
        uncertainty = holdover_uncertainty(
            elapsed,
            self.config.clock_uncertainty_s,
            self.config.holdover_fractional_frequency_error,
        )
        for agent_id in self.agent_ids:
            self.emit(
                "TIMING_UPDATE",
                source_id="service:time",
                destination_id=agent_id,
                graph_layer="dependency",
                timing_uncertainty=uncertainty,
                severity="warning" if uncertainty >= 1e-3 else "info",
                metadata={"holdover_elapsed_s": elapsed},
            )
        next_time = self.engine.now + self.config.timing_update_interval_s
        if next_time <= self.config.duration_s:
            self.engine.schedule_at(next_time, self._timing_update, label="timing:update")


    def _schedule_credential_renewals(self) -> None:
        rng = self.streams.rng("credentials")
        for agent_id in self.agent_ids:
            initial_delay = float(rng.uniform(0.0, self.config.credential_ttl_s))
            if initial_delay <= self.config.duration_s:
                self.engine.schedule_after(
                    initial_delay,
                    lambda target=agent_id: self._credential_renewal(target),
                    label=f"credentials:renew:{agent_id}",
                )

    def _credential_renewal(self, agent_id: str) -> None:
        agent = self.state.agents[agent_id]
        if agent.health in {AgentHealth.ISOLATED, AgentHealth.REVOKED, AgentHealth.TERMINATED}:
            self.emit(
                "CREDENTIAL_RENEWAL_DENIED",
                source_id="service:identity",
                destination_id=agent_id,
                resource_id="credential-authority",
                graph_layer="authorization",
                severity="warning",
                metadata={"reason": f"agent_{agent.health.value}"},
            )
        else:
            self.emit(
                "CREDENTIAL_RENEWAL",
                source_id="service:identity",
                destination_id=agent_id,
                resource_id="credential-authority",
                graph_layer="authorization",
                credential_epoch=agent.credential_epoch + 1,
                metadata={"scheduled_renewal": True},
            )

        jitter = self.config.credential_renewal_jitter_fraction
        multiplier = float(self.streams.rng("credentials").uniform(1.0 - jitter, 1.0 + jitter))
        interval = max(1e-9, self.config.credential_ttl_s * multiplier)
        if self.engine.now + interval <= self.config.duration_s:
            self.engine.schedule_after(
                interval,
                lambda target=agent_id: self._credential_renewal(target),
                label=f"credentials:renew:{agent_id}",
            )

    def _mass_revocation_start(self) -> None:
        count = max(1, round(self.config.n_agents * self.config.mass_revocation_fraction))
        selected = sorted(
            int(value)
            for value in np.atleast_1d(
                self.streams.rng("credentials").choice(
                    self.config.n_agents,
                    size=min(count, self.config.n_agents),
                    replace=False,
                )
            )
        )
        self.emit(
            "CREDENTIAL_REVOCATION_STORM_START",
            source_id="service:identity",
            resource_id="credential-authority",
            severity="critical",
            metadata={
                "agents": len(selected),
                "issuance_capacity_hz": self.config.credential_issuance_capacity_hz,
            },
        )
        interval = 1.0 / self.config.credential_issuance_capacity_hz
        for index, node in enumerate(selected):
            agent_id = self._agent_id(node)

            def revoke(target: str = agent_id) -> None:
                epoch = self.state.agents[target].credential_epoch + 1
                self.emit(
                    "REVOCATION",
                    source_id="service:identity",
                    destination_id=target,
                    resource_id="credential-authority",
                    graph_layer="authorization",
                    credential_epoch=epoch,
                    severity="critical",
                    metadata={"mass_revocation": True},
                )

            when = self.engine.now + index * interval
            if when <= self.config.duration_s:
                self.engine.schedule_at(when, revoke, label=f"credentials:revoke:{node}")

        if selected:
            storm_duration = (len(selected) - 1) * interval
            completion_time = self.engine.now + storm_duration
            if completion_time <= self.config.duration_s:
                self.engine.schedule_at(
                    completion_time,
                    lambda duration=storm_duration: self.emit(
                        "CREDENTIAL_REVOCATION_STORM_END",
                        source_id="service:identity",
                        resource_id="credential-authority",
                        metadata={
                            "agents": len(selected),
                            "elapsed_s": duration,
                        },
                    ),
                    label="credentials:mass-revocation:end",
                )

    def _schedule_scenario_events(self) -> None:
        self._schedule_first_task()
        self._schedule_credential_renewals()
        if self.config.gossip_enabled and self.config.gossip_start_s <= self.config.duration_s:
            self.engine.schedule_at(self.config.gossip_start_s, self._start_gossip, label="gossip:start")
        if (
            self.config.security_enabled
            and self.config.attack_start_s is not None
            and self.config.attack_start_s <= self.config.duration_s
        ):
            self.engine.schedule_at(
                self.config.attack_start_s,
                self._start_security_incident,
                label="security:start",
            )
        if (
            self.config.timing_denial_start_s is not None
            and self.config.timing_denial_start_s <= self.config.duration_s
        ):
            self.engine.schedule_at(
                self.config.timing_denial_start_s,
                self._timing_denial_start,
                label="timing:denial",
            )
        if (
            self.config.mass_revocation_start_s is not None
            and self.config.mass_revocation_start_s <= self.config.duration_s
        ):
            self.engine.schedule_at(
                self.config.mass_revocation_start_s,
                self._mass_revocation_start,
                label="credentials:mass-revocation",
            )

    def run(self, artifact_root: str | Path | None = None) -> SimulationArtifacts:
        root = Path(artifact_root) if artifact_root is not None else self.repository_root
        self.started_unix = time.time()
        self.emit(
            "SIMULATION_START",
            source_id="experiment-runner",
            metadata={
                "scenario_name": self.config.scenario_name,
                "n_agents": self.config.n_agents,
                "trace_level": self.config.trace_level,
                "representation": "exact",
                "parameter_class": self.config.provenance,
            },
        )
        self._schedule_scenario_events()
        self.engine.run(until=self.config.duration_s, max_events=self.config.max_events)
        self._advance_control_areas(self.config.duration_s)
        pre_end_digest = self.log.digest()
        self.emit(
            "SIMULATION_END",
            source_id="experiment-runner",
            metadata={
                "pending_actions": self.engine.pending_events,
                "event_log_digest_before_end": pre_end_digest,
            },
        )
        self.ended_unix = time.time()
        return self._write_artifacts(root)

    @staticmethod
    def _quantiles(values: list[float]) -> dict[str, float | None]:
        if not values:
            return {"p50": None, "p95": None, "p99": None}
        return {
            "p50": float(np.quantile(values, 0.50)),
            "p95": float(np.quantile(values, 0.95)),
            "p99": float(np.quantile(values, 0.99)),
        }

    def _metrics(self) -> dict[str, Any]:
        completed = [task for task in self.tasks.values() if task.status == TaskStatus.COMPLETE]
        useful = [task for task in completed if task.useful]
        duration = self.config.duration_s
        effective_lambda = len(self.authorization_sojourn_s) / duration
        average_control_l = self._control_system_area / duration
        mean_control_w = float(np.mean(self.authorization_sojourn_s)) if self.authorization_sojourn_s else 0.0
        little_residual = average_control_l - effective_lambda * mean_control_w
        utilization = self._control_busy_area / (self.config.control_servers * duration)
        total_arrival_rate = self.config.n_agents * self.config.task_arrival_rate_per_agent_hz
        analytic_queue = erlang_c(
            total_arrival_rate,
            self.config.control_service_rate_per_server_hz,
            self.config.control_servers,
        )
        auth_metrics = graph_metrics(self.authorization_graph)
        communication_metrics = graph_metrics(self.communication_graph)
        stability_product = epidemic_stability_product(
            self.authorization_graph,
            self.config.infection_rate_per_edge_hz,
            self.config.recovery_rate_hz,
        )
        detection_delays = [
            self.detection_time[node] - self.compromise_time[node]
            for node in self.detection_time
            if node in self.compromise_time
        ]
        containment_delays = [
            self.containment_time[node] - self.compromise_time[node]
            for node in self.containment_time
            if node in self.compromise_time
        ]
        telemetry = hierarchical_telemetry(
            self.config.n_agents,
            self.config.telemetry_rate_bps_per_agent,
            span=self.config.hierarchy_span,
            compression_ratio=self.config.telemetry_compression_ratio,
        )
        bytes_transmitted = self.model_bytes_transmitted
        trace_bytes_stored = sum(len(event.canonical_json()) + 1 for event in self.log)
        crypto_operations = self.state.counters.get("authorization_decisions", 0.0)
        cost = practical_cost_per_useful_task(
            useful_tasks=len(useful),
            duration_s=duration,
            n_agents=self.config.n_agents,
            bytes_transmitted=bytes_transmitted,
            bytes_stored=trace_bytes_stored,
            crypto_operations=crypto_operations,
            supervisor_seconds=sum(containment_delays),
        )
        energy = practical_energy_per_useful_task(
            useful_tasks=len(useful),
            duration_s=duration,
            n_agents=self.config.n_agents,
            bits_transmitted=8 * bytes_transmitted,
        )
        landauer = landauer_energy(8 * bytes_transmitted)
        one_way_floor = fiber_propagation_delay(self.config.geographic_diameter_km)
        issuance = size_issuer(
            self.config.n_agents,
            self.config.credential_ttl_s,
        )

        return {
            "evidence_class": "numerically_demonstrated_stage0_integration_only",
            "parameter_class": self.config.provenance,
            "run_id": self.run_id,
            "configuration_hash": self.configuration_hash,
            "seed": self.config.seed,
            "scenario_name": self.config.scenario_name,
            "n_agents": self.config.n_agents,
            "duration_s": duration,
            "trace_level": self.config.trace_level,
            "event_count": len(self.log),
            "event_log_digest": self.log.digest(),
            "final_state_hash": self.state.state_hash(),
            "event_counts_by_type": self.log.event_counts(),
            "tasks": {
                "arrived": len(self.tasks),
                "completed": len(completed),
                "useful_completed": len(useful),
                "raw_throughput_hz": len(completed) / duration,
                "useful_throughput_hz": len(useful) / duration,
                "latency_s": self._quantiles(self.task_latencies_s),
                "useful_latency_s": self._quantiles(self.useful_latencies_s),
            },
            "control_plane": {
                "observed_utilization": utilization,
                "observed_mean_number_system": average_control_l,
                "observed_mean_sojourn_s": mean_control_w,
                "little_law_residual": little_residual,
                "completed_authorizations": self.auth_center.completed,
                "max_queue": self.auth_center.max_queue,
                "analytic_erlang_c": {
                    "utilization": analytic_queue.utilization,
                    "probability_wait": analytic_queue.probability_wait,
                    "mean_wait_queue_s": analytic_queue.mean_wait_queue_s,
                    "mean_time_system_s": analytic_queue.mean_time_system_s,
                    "mean_number_system": analytic_queue.mean_number_system,
                },
                "minimum_servers_for_rho_0_70": minimum_servers(
                    total_arrival_rate,
                    self.config.control_service_rate_per_server_hz,
                    0.70,
                ),
            },
            "gossip": {
                "rounds": self.gossip_round,
                "coverage": len(self.gossip_informed) / self.config.n_agents,
                "messages": self.gossip_messages,
            },
            "security": {
                "authorization_spectral_radius": auth_metrics["spectral_radius"],
                "epidemic_stability_product": stability_product,
                "unique_compromised_agents": len(self.unique_compromised),
                "blast_radius_fraction": len(self.unique_compromised) / self.config.n_agents,
                "max_active_compromised": self.max_active_compromised,
                "final_active_compromised": len(self.security_infected),
                "contained_agents": len(self.security_removed),
                "detection_delay_s": self._quantiles(detection_delays),
                "containment_delay_s": self._quantiles(containment_delays),
            },
            "graphs": {
                "communication": communication_metrics,
                "authorization": auth_metrics,
            },
            "telemetry": {
                "raw_rate_bps": telemetry.raw_rate_bps,
                "apex_rate_bps": telemetry.apex_rate_bps,
                "depth": telemetry.depth,
                "layer_rates_bps": telemetry.layer_rates_bps,
            },
            "timing": {
                "continental_one_way_physics_floor_s": one_way_floor,
                "continental_round_trip_physics_floor_s": 2 * one_way_floor,
                "final_agent_clock_uncertainty_s": max(
                    state.timing_uncertainty_s for state in self.state.agents.values()
                ),
            },
            "credentials": {
                "pairwise_keys": pairwise_key_count(self.config.n_agents),
                "steady_state_issuance_rate_hz": certificate_issuance_rate(
                    self.config.n_agents,
                    self.config.credential_ttl_s,
                ),
                "sized_capacity_hz": issuance.required_capacity_per_s,
            },
            "cost_energy": {
                "practical_cost_per_useful_task_usd": cost,
                "practical_energy_per_useful_task_j": energy,
                "landauer_floor_for_modeled_message_bits_j": landauer,
                "modeled_network_bytes": bytes_transmitted,
                "trace_storage_bytes": trace_bytes_stored,
                "cost_and_practical_energy_parameter_class": "notional",
            },
            "limitations": [
                "The baseline parameter set is notional.",
                "This is a Stage 0 integration and replay demonstration, not a fleet assurance conclusion.",
                "The security process is a finite discrete-time SIR-like containment model.",
                "The workload, authorization queue, agent service queues, and cost rates are stylized.",
                "Little's Law is reported as a finite-horizon consistency residual, not a steady-state proof.",
            ],
        }

    def _layout(self) -> tuple[dict[int, tuple[float, float]], str]:
        if self.config.n_agents > 2_000:
            positions = {
                node: (
                    float(node % self.config.hierarchy_span),
                    float(node // self.config.hierarchy_span),
                )
                for node in range(self.config.n_agents)
            }
            return positions, "aggregated-layout-input"
        graph = self.communication_graph.materialize()
        if self.communication_graph.topology == "hierarchical":
            depths = nx.single_source_shortest_path_length(graph, 0)
            levels: dict[int, list[int]] = {}
            for node, depth in depths.items():
                levels.setdefault(int(depth), []).append(int(node))
            max_depth = max(levels, default=0)
            positions = {}
            for depth, nodes in sorted(levels.items()):
                ordered = sorted(nodes)
                width = max(1, len(ordered) - 1)
                for index, node in enumerate(ordered):
                    x = 0.0 if len(ordered) == 1 else -1.0 + 2.0 * index / width
                    y = 1.0 - 2.0 * depth / max(1, max_depth)
                    positions[node] = np.array([x, y])
        elif self.communication_graph.topology == "complete":
            positions = nx.circular_layout(graph)
        else:
            positions = nx.spring_layout(
                graph,
                seed=self.communication_graph.seed,
                iterations=50 if self.config.n_agents <= 500 else 20,
            )
        return {int(node): (float(value[0]), float(value[1])) for node, value in positions.items()}, "exact"

    def _write_artifacts(self, root: Path) -> SimulationArtifacts:
        results_dir = root / "results"
        manifests_dir = root / "manifests"
        bundle_dir = root / "replay_bundles" / self.run_id
        for directory in (results_dir, manifests_dir, bundle_dir):
            directory.mkdir(parents=True, exist_ok=True)

        event_path = self.log.write_jsonl(bundle_dir / "events.jsonl")
        self.log.write_csv(bundle_dir / "events.csv")
        initial_path = bundle_dir / "initial_state.json"
        final_path = bundle_dir / "final_state.json"
        config_path = bundle_dir / "config.yaml"
        summary_path = bundle_dir / "summary.json"
        graph_path = bundle_dir / "graph_layers.json"
        snapshots_path = bundle_dir / "snapshots.jsonl"
        metrics_path = results_dir / f"{self.run_id}_metrics.csv"
        manifest_path = manifests_dir / f"{self.run_id}.json"

        initial_path.write_text(json.dumps(self.initial_state.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
        final_path.write_text(json.dumps(self.state.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
        config_path.write_text(yaml.safe_dump(self.config.to_dict(), sort_keys=True), encoding="utf-8")

        replay = ReplayEngine(self.initial_state, self.log)
        replayed_state = replay.replay()
        if replayed_state.state_hash() != self.state.state_hash():
            raise RuntimeError("replay final state does not equal simulation final state")
        snapshots = replay.snapshots(self.config.snapshot_interval_events)
        write_snapshots(snapshots, snapshots_path)
        final_from_snapshot = replay.seek_from_snapshot(snapshots[-1], len(self.log.events))
        if final_from_snapshot.state_hash() != self.state.state_hash():
            raise RuntimeError("snapshot seek does not reproduce final simulation state")

        metrics = self._metrics()
        metrics["replay_validation"] = {
            "passed": True,
            "simulation_state_hash": self.state.state_hash(),
            "replay_state_hash": replayed_state.state_hash(),
            "snapshot_seek_state_hash": final_from_snapshot.state_hash(),
        }
        summary_path.write_text(json.dumps(metrics, indent=2, sort_keys=True, default=str), encoding="utf-8")

        flat_row = {
            "run_id": self.run_id,
            "configuration_hash": self.configuration_hash,
            "seed": self.config.seed,
            "n_agents": self.config.n_agents,
            "scenario_name": self.config.scenario_name,
            "useful_throughput_hz": metrics["tasks"]["useful_throughput_hz"],
            "raw_throughput_hz": metrics["tasks"]["raw_throughput_hz"],
            "p50_latency_s": metrics["tasks"]["latency_s"]["p50"],
            "p95_latency_s": metrics["tasks"]["latency_s"]["p95"],
            "p99_latency_s": metrics["tasks"]["latency_s"]["p99"],
            "control_utilization": metrics["control_plane"]["observed_utilization"],
            "control_little_residual": metrics["control_plane"]["little_law_residual"],
            "blast_radius_fraction": metrics["security"]["blast_radius_fraction"],
            "spectral_radius": metrics["security"]["authorization_spectral_radius"],
            "epidemic_stability_product": metrics["security"]["epidemic_stability_product"],
            "gossip_rounds": metrics["gossip"]["rounds"],
            "gossip_coverage": metrics["gossip"]["coverage"],
            "event_count": len(self.log),
            "wall_clock_s": self.ended_unix - self.started_unix,
            "parameter_class": self.config.provenance,
        }
        pd.DataFrame([flat_row]).to_csv(metrics_path, index=False)
        shutil.copyfile(metrics_path, results_dir / "latest_metrics.csv")

        positions, layout_representation = self._layout()
        graph_payload = {
            "representation": layout_representation,
            "nodes": [
                {
                    "id": self._agent_id(node),
                    "index": node,
                    "x": positions[node][0],
                    "y": positions[node][1],
                    "partition": self.state.agents[self._agent_id(node)].partition,
                    "supervisor_id": self.state.agents[self._agent_id(node)].supervisor_id,
                }
                for node in range(self.config.n_agents)
            ],
            "layers": {
                "communication": {
                    "topology": self.communication_graph.topology,
                    "representation": self.communication_graph.representation,
                    "edges": (
                        [[self._agent_id(int(u)), self._agent_id(int(v))]
                         for u, v in self.communication_graph.materialize().edges()]
                        if self.communication_graph.graph is not None
                        else []
                    ),
                },
                "authorization": {
                    "topology": self.authorization_graph.topology,
                    "representation": self.authorization_graph.representation,
                    "edges": (
                        [[self._agent_id(int(u)), self._agent_id(int(v))]
                         for u, v in self.authorization_graph.materialize().edges()]
                        if self.authorization_graph.graph is not None
                        else []
                    ),
                },
            },
        }
        graph_path.write_text(json.dumps(graph_payload, indent=2, sort_keys=True), encoding="utf-8")

        manifest = capture_manifest(
            root=self.repository_root,
            run_id=self.run_id,
            configuration_hash=self.configuration_hash,
            seed=self.config.seed,
            substreams=self.streams.manifest(),
            started_unix=self.started_unix,
            ended_unix=self.ended_unix,
            trace_level=self.config.trace_level,
        )
        manifest.update(
            {
                "event_log_digest": self.log.digest(),
                "final_state_hash": self.state.state_hash(),
                "replay_state_hash": replayed_state.state_hash(),
                "host_python_implementation": platform.python_implementation(),
            }
        )
        write_manifest(manifest_path, manifest)
        (bundle_dir / "README.md").write_text(
            "# Fleet Assurance Replay Bundle\n\n"
            f"Run ID: `{self.run_id}`\n\n"
            f"Configuration hash: `{self.configuration_hash}`\n\n"
            f"Seed: `{self.config.seed}`\n\n"
            "Representation: exact simulation with a notional parameter set. The visual layout may be "
            "aggregated at large N. This bundle demonstrates deterministic replay and does not establish "
            "production assurance.\n",
            encoding="utf-8",
        )

        return SimulationArtifacts(
            self.run_id,
            bundle_dir,
            event_path,
            summary_path,
            metrics_path,
            manifest_path,
            None,
            self.state.state_hash(),
            replayed_state.state_hash(),
            self.log.digest(),
        )
