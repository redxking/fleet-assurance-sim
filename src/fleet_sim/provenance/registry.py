"""Parameter registry loading and provenance enforcement."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


class ParameterRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parameter_id: str
    symbol: str
    definition: str
    units: str
    baseline_value: float | int | str | bool
    sweep: list[float | int | str | bool] | None = None
    provenance_class: Literal["measured", "inferred", "notional", "analytically_fixed"]
    source: str
    date: str
    environment: str
    uncertainty: str
    applicable_scenarios: list[str] = Field(default_factory=list)


def load_parameter_registry(path: str | Path) -> list[ParameterRecord]:
    raw: Any = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    adapter = TypeAdapter(list[ParameterRecord])
    records = adapter.validate_python(raw)
    seen: set[str] = set()
    for record in records:
        if record.parameter_id in seen:
            raise ValueError(f"duplicate parameter_id: {record.parameter_id}")
        seen.add(record.parameter_id)
        if record.provenance_class in {"measured", "inferred"} and not record.source.strip():
            raise ValueError(f"parameter {record.parameter_id} requires a source")
    return records
