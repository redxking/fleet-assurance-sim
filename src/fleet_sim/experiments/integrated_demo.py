"""Compatibility entrypoint for the Stage 0 integrated simulator."""

from .simulator import FleetSimulator, SimulationArtifacts

IntegratedFleetSimulator = FleetSimulator

__all__ = ["FleetSimulator", "IntegratedFleetSimulator", "SimulationArtifacts"]
