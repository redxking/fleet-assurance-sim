"""Compatibility re-export for the canonical configuration model."""

from fleet_sim.config import SimulationConfig, load_config, save_config

__all__ = ["SimulationConfig", "load_config", "save_config"]
