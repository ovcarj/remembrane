from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

SCHEMA_VERSION = "0.1.0"


class LipidCount(BaseModel):
    count: int
    fraction: float


class Leaflet(BaseModel):
    lipids: dict[str, LipidCount]


class Composition(BaseModel):
    upper_leaflet: Leaflet
    lower_leaflet: Leaflet
    force_field: str
    water_model: str
    temperature_K: float
    ion_type: str
    ion_conc_M: float


class PotentialMeta(BaseModel):
    axis: str
    slices: int
    charge_group: str
    component_groups: list[str]
    symmetrize: bool
    correct: bool
    source_tool: str


class ArtifactEntry(BaseModel):
    path: str
    sha256: str
    units: dict[str, str] = Field(default_factory=dict)


class Artifacts(BaseModel):
    potential_total: ArtifactEntry
    potential_components: ArtifactEntry
    aiida_archive: ArtifactEntry | None = None


class FileHash(BaseModel):
    sha256: str


class SoftwareVersions(BaseModel):
    remembrane_version: str
    tracy_version: str | None = None
    gromacs_version: str | None = None
    aiida_core_version: str | None = None
    aiida_gromacs_version: str | None = None
    python_version: str | None = None


class AiidaRefs(BaseModel):
    profile: str | None = None
    build_membrane_wc: str | None = None
    run_md_wc: str | None = None
    compute_potential_wc: str | None = None


class MembraneRecord(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    schema_version: str = SCHEMA_VERSION
    scientific_hash: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    composition: Composition
    protocols: dict[str, Any]
    potential_meta: PotentialMeta
    artifacts: Artifacts
    source_files: dict[str, FileHash] = Field(default_factory=dict)
    software: SoftwareVersions
    aiida_refs: AiidaRefs = Field(default_factory=AiidaRefs)
    tags: list[str] = Field(default_factory=list)
    notes: str = ""

    model_config = {"arbitrary_types_allowed": True}

    def model_post_init(self, __context: Any) -> None:
        if not self.scientific_hash:
            object.__setattr__(self, "scientific_hash", self._compute_hash())

    def _compute_hash(self) -> str:
        stable = {
            "composition": self.composition.model_dump(),
            "protocols": self.protocols,
            "potential_meta": self.potential_meta.model_dump(),
            "source_files": {k: v.model_dump() for k, v in self.source_files.items()},
            "software": self.software.model_dump(),
        }
        canonical = json.dumps(stable, sort_keys=True, default=str).encode()
        return hashlib.sha256(canonical).hexdigest()

    @classmethod
    def from_yaml(cls, path: str | Path) -> "MembraneRecord":
        data = yaml.safe_load(Path(path).read_text())
        return cls.model_validate(data)

    def to_yaml(self, path: str | Path) -> None:
        data = json.loads(self.model_dump_json())
        # Serialize UUID and datetime to strings
        data["id"] = str(self.id)
        data["created_at"] = self.created_at.isoformat()
        Path(path).write_text(yaml.dump(data, default_flow_style=False, allow_unicode=True))
