# remembrane

A curated scientific database for membrane electrostatic potential profiles.

`remembrane` stores, validates, and queries the results of membrane MD simulations — specifically electrostatic potential φ(z) profiles computed across lipid bilayers. It is designed as a companion to the [`tracy`](https://github.com/ovcarj/tracy) AiiDA workflow package, but is independent of AiiDA at its core.

---

## Design principles

**AiiDA-independent core.** The core package (`remembrane`) stores and queries records using only numpy, pydantic, click, and PyYAML. AiiDA is an optional import bridge (`remembrane[aiida]`), not a runtime requirement.

**Complete records only.** A record is complete and valid, or it is not stored. There are no partial imports. If provenance cannot be fully reconstructed, the import fails with a structured error listing exactly what is missing.

**Directory-backed registry.** Records live as human-readable YAML files alongside numpy arrays in a plain directory tree — inspectable, git-friendly, and trivially backed up. A `Registry` abstraction exists for future SQL backends.

**Reproducibility by design.** Every record carries: full protocol dicts, source file SHA256 checksums, software version metadata, and a deterministic `scientific_hash` over the scientific content. AiiDA provenance archives (`.aiida`) can be attached for full end-to-end reproducibility.

---

## Installation

`remembrane` is not yet on PyPI. Install directly from GitHub:

```bash
# Core package (no AiiDA required)
pip install "git+https://github.com/ovcarj/remembrane.git"

# With AiiDA import bridge
pip install "remembrane[aiida] @ git+https://github.com/ovcarj/remembrane.git"

# With plotting
pip install "remembrane[plot] @ git+https://github.com/ovcarj/remembrane.git"

# Development install (clone first)
git clone https://github.com/ovcarj/remembrane.git
cd remembrane
pip install -e ".[dev]"
```

---

## Quick start

```bash
# Initialize a database
remembrane init
# → creates ~/.remembrane/

# Import a ComputeMembranePotentialWorkChain by AiiDA PK
remembrane import aiida --pk <pk>

# List all records
remembrane list

# Query by lipid composition
remembrane query --lipid CDL2
remembrane query --lipid POPE --lipid CDL2 --min-fraction CDL2 0.15

# Inspect a record
remembrane show <record-id>

# Verify stored artifacts
remembrane verify <record-id>

# Export AiiDA provenance archive (full reproducibility bundle)
remembrane export aiida-archive <record-id>

# Export data
remembrane export json --output results.json
remembrane export csv --output results.csv
```

Use `--db /path/to/db` to target a non-default database directory.

---

## Database layout

```
~/.remembrane/
  config.yaml
  index.json                      ← fast lookup cache
  records/
    <record-uuid>/
      metadata.yaml               ← composition, protocols, AiiDA refs, checksums
      potential_total.npz         ← z_nm + phi_V arrays
      potential_components.npz    ← {group_name: phi_array, z_nm: array}
      provenance.aiida            ← (optional) full AiiDA provenance archive
```

---

## Record schema

Each record captures everything needed to interpret and reproduce the result:

```yaml
id: <uuid4>
schema_version: "0.1.0"
scientific_hash: <sha256>       # deterministic over composition + protocols + checksums + software

composition:
  upper_leaflet:
    lipids:
      POPC: {count: 128, fraction: 1.0}
  lower_leaflet:
    lipids:
      POPC: {count: 128, fraction: 1.0}
  force_field: CHARMM36
  water_model: TIP3
  temperature_K: 303.15
  ion_type: KCl
  ion_conc_M: 0.15

potential_meta:
  axis: Z
  slices: 200
  charge_group: SYSTEM
  component_groups: [MEMB, Water, ION]
  symmetrize: false
  correct: true
  source_tool: gmx potential

artifacts:
  potential_total:
    path: potential_total.npz
    sha256: "..."
    units: {z: nm, phi: V}
  potential_components:
    path: potential_components.npz
    sha256: "..."

source_files:
  tpr:  {sha256: "..."}
  xtc:  {sha256: "..."}

software:
  remembrane_version: "0.1.0"
  tracy_version: "..."
  gromacs_version: null
  aiida_core_version: "..."
  python_version: "3.11.0"

aiida_refs:
  profile: "<aiida-profile>"
  build_membrane_wc: "<uuid>"
  run_md_wc: "<uuid>"
  compute_potential_wc: "<uuid>"

tags: []
notes: ""
```

### `scientific_hash`

A SHA256 hash over the scientific content of the record — composition, protocols, potential metadata, source file checksums, and software versions. Fields that do not affect scientific meaning (record id, creation time, notes, tags, local paths, AiiDA profile name) are excluded. This hash is used for deduplication: importing the same calculation twice is detected and rejected.

---

## CLI reference

```
remembrane [--db PATH] COMMAND

Commands:
  init                Initialize a new database directory.
  list                List all records.
  show RECORD_ID      Show full metadata for a record.
  query               Query records by composition criteria.
  validate DIR        Validate a candidate record directory before importing.
  verify RECORD_ID    Verify stored artifact checksums and array shapes.
  import              Import a record (see below).
  export              Export records or provenance archives (see below).

remembrane import aiida --pk PK [--uuid UUID]
remembrane import directory --path DIR

remembrane export aiida-archive RECORD_ID [--output PATH]
remembrane export json [--output PATH] [--lipid LIPID ...]
remembrane export csv  [--output PATH] [--lipid LIPID ...]

remembrane plot RECORD_ID [RECORD_ID ...]   [--components] [--title TEXT] [--output PATH]
remembrane plot --lipid LIPID ...           [--components] [--title TEXT] [--output PATH]

remembrane query/plot filter options (shared):
  --lipid NAME            Require this lipid (repeatable, all must match).
  --min-fraction NAME F   Minimum combined leaflet fraction for a lipid.
  --force-field NAME
  --temperature K
  --tag NAME              Require this tag (repeatable).
```

`plot` accepts either positional record IDs **or** query filter options — not both.
`--output` saves to a file (PNG, PDF, SVG); without it the plot is shown interactively.

---

## Python API

### Registry

```python
from remembrane import Registry

reg = Registry.open("~/.remembrane")
reg = Registry.init("/new/path")          # create new database

reg.add(record)                           # raises DuplicateRecordError on duplicate hash
rec = reg.get("record-uuid")
records = reg.list()
d = reg.record_dir("record-uuid")        # Path to the record's directory
```

### MembraneRecord

```python
from remembrane.record import MembraneRecord

rec = MembraneRecord.from_yaml("path/to/metadata.yaml")
rec.to_yaml("output/metadata.yaml")
print(rec.scientific_hash)               # 64-character hex string
print(rec.composition.upper_leaflet.lipids["POPC"].fraction)
```

### Query

```python
from remembrane.query import filter_records

results = filter_records(
    records,
    lipid=["CDL2", "POPE"],               # must contain all listed lipids
    min_fraction=("CDL2", 0.15),          # combined fraction ≥ 0.15
    force_field="CHARMM36",
    temperature_K=310.15,
    tags=["validated"],
)
```

### AiiDA import

```python
from remembrane.aiida.importer import from_potential_workchain, ImportIncompleteError

try:
    record, arrays = from_potential_workchain(pk=<pk>)
    # arrays: {"z_nm": ndarray, "phi_V": ndarray, "components": {"MEMB": ..., ...}}
except ImportIncompleteError as e:
    print(e)   # lists missing_fields, missing_artifacts, diagnostics
```

When `BuildMembraneWorkChain` is not in the automatic provenance graph (standalone
submission), pass it explicitly:

```python
record, arrays = from_potential_workchain(pk=<potential_pk>, build_membrane_pk=<build_pk>)
```

### Export

```python
from remembrane.export import records_to_json, records_to_csv

json_str = records_to_json(records)
csv_str  = records_to_csv(records)    # one row per record, one column per lipid
```

### Reading stored arrays

```python
import numpy as np
from remembrane.storage import load_potential_total, load_potential_components

z_nm, phi_V = load_potential_total(reg.record_dir(record.id))
components   = load_potential_components(reg.record_dir(record.id))
# components["MEMB"], components["Water"], components["ION"], components["z_nm"]
```

### Plotting (`remembrane[plot]`)

```python
from remembrane.plot import plot_profile, plot_comparison

# Single profile
fig = plot_profile(record, reg.record_dir(record.id))
fig = plot_profile(record, reg.record_dir(record.id), components=True)

# Overlay multiple records
records = reg.query(lipid="CDL2")
dirs    = [reg.record_dir(r.id) for r in records]
fig     = plot_comparison(records, dirs)

# Custom legend labels
fig = plot_comparison(records, dirs,
                      label_fn=lambda r: r.notes or str(r.id)[:8])

# Reuse an external Axes (e.g. in a subplot grid)
import matplotlib.pyplot as plt
fig, axes = plt.subplots(1, 2)
plot_profile(records[0], dirs[0], ax=axes[0])
plot_profile(records[1], dirs[1], ax=axes[1])
plt.show()

fig.savefig("comparison.png", dpi=150, bbox_inches="tight")
```

---

## Reproducibility

Each record contains three layers of reproducibility:

1. **Scientific content**: full protocol dicts, lipid counts (not just fractions), all parameter choices verbatim. The `scientific_hash` lets you detect duplicate imports or verify that two datasets represent the same experiment.

2. **Artifact integrity**: SHA256 checksums for every `.npz` file and (when present) source files (`.tpr`, `.xtc`). Run `remembrane verify <id>` at any time to confirm the database has not been corrupted.

3. **Full provenance archive** (AiiDA imports only): `remembrane export aiida-archive <id>` calls `verdi archive create` to bundle the complete AiiDA provenance graph — every input, calculation, and output — into a portable `.aiida` file that can be imported into any AiiDA instance for re-inspection or re-submission.

---

## Development

```bash
pip install -e ".[dev]"
pytest tests/
```

Practical integration tests requiring a live AiiDA instance with tracy calculations are not part of the package test suite.
