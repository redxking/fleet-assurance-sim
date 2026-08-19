"""Compatibility exports for the canonical integrated fleet simulator.

The project previously contained two overlapping integrated implementations. The
canonical implementation now lives in :mod:`fleet_sim.experiments.simulator` so
execution, artifact generation, and replay all share one state-transition model.
"""

from .simulator import FleetSimulator, SimulationArtifacts

FleetSimulation = FleetSimulator

__all__ = ["FleetSimulation", "FleetSimulator", "SimulationArtifacts"]
