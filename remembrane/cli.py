from __future__ import annotations

import sys
from pathlib import Path

import click
import yaml

DEFAULT_DB = Path.home() / ".remembrane"


@click.group()
@click.option("--db", default=str(DEFAULT_DB), show_default=True,
              help="Path to remembrane database directory.")
@click.pass_context
def cli(ctx: click.Context, db: str) -> None:
    ctx.ensure_object(dict)
    ctx.obj["db"] = db


@cli.command()
@click.option("--path", default=None, help="Database path (overrides --db).")
@click.pass_context
def init(ctx: click.Context, path: str | None) -> None:
    """Initialize a new remembrane database."""
    from remembrane.registry import Registry
    target = path or ctx.obj["db"]
    Registry.init(target)
    click.echo(f"Initialized remembrane database at {target}")


@cli.command(name="list")
@click.pass_context
def list_records(ctx: click.Context) -> None:
    """List all records in the database."""
    from remembrane.registry import Registry
    reg = Registry.open(ctx.obj["db"])
    records = reg.list()
    if not records:
        click.echo("No records found.")
        return
    click.echo(f"{'ID':<38}  {'Scientific hash':<16}  Composition")
    click.echo("-" * 80)
    for rec in records:
        comp = _composition_summary(rec)
        click.echo(f"{str(rec.id):<38}  {rec.scientific_hash[:16]}  {comp}")


@cli.command()
@click.argument("record_id")
@click.pass_context
def show(ctx: click.Context, record_id: str) -> None:
    """Show full metadata for a record."""
    from remembrane.registry import Registry, RecordNotFoundError
    reg = Registry.open(ctx.obj["db"])
    try:
        rec = reg.get(record_id)
    except RecordNotFoundError as e:
        click.echo(str(e), err=True)
        sys.exit(1)
    click.echo(yaml.dump(rec.model_dump(mode="json"), default_flow_style=False))


@cli.command()
@click.option("--lipid", multiple=True, help="Require this lipid (repeatable).")
@click.option("--min-fraction", nargs=2, metavar="LIPID FRAC",
              help="Minimum combined leaflet fraction for a lipid, e.g. --min-fraction CDL2 0.15")
@click.option("--force-field", default=None)
@click.option("--temperature", type=float, default=None)
@click.option("--tag", multiple=True)
@click.pass_context
def query(ctx: click.Context, lipid, min_fraction, force_field, temperature, tag) -> None:
    """Query records by composition criteria."""
    from remembrane.registry import Registry
    from remembrane.query import filter_records
    reg = Registry.open(ctx.obj["db"])
    records = reg.list()
    mf = (min_fraction[0], float(min_fraction[1])) if min_fraction else None
    results = filter_records(
        records,
        lipid=list(lipid) or None,
        min_fraction=mf,
        force_field=force_field,
        temperature_K=temperature,
        tags=list(tag) or None,
    )
    if not results:
        click.echo("No matching records.")
        return
    click.echo(f"{'ID':<38}  {'Scientific hash':<16}  Composition")
    click.echo("-" * 80)
    for rec in results:
        click.echo(f"{str(rec.id):<38}  {rec.scientific_hash[:16]}  {_composition_summary(rec)}")


@cli.command()
@click.argument("record_dir")
@click.pass_context
def validate(ctx: click.Context, record_dir: str) -> None:
    """Validate a candidate record directory before importing."""
    from remembrane.record import MembraneRecord
    from remembrane.storage import verify_artifact
    errors = []
    d = Path(record_dir)
    meta_path = d / "metadata.yaml"
    if not meta_path.exists():
        click.echo(f"ERROR: metadata.yaml not found in {d}", err=True)
        sys.exit(1)
    try:
        rec = MembraneRecord.from_yaml(meta_path)
    except Exception as e:
        click.echo(f"ERROR: metadata.yaml failed validation: {e}", err=True)
        sys.exit(1)
    for name, artifact in [
        ("potential_total", rec.artifacts.potential_total),
        ("potential_components", rec.artifacts.potential_components),
    ]:
        if not verify_artifact(d, artifact.path, artifact.sha256):
            errors.append(f"Artifact checksum mismatch or missing: {artifact.path}")
    if errors:
        for e in errors:
            click.echo(f"ERROR: {e}", err=True)
        sys.exit(1)
    click.echo(f"Valid: {d}")


@cli.command(name="import")
@click.argument("source", type=click.Choice(["directory", "aiida"]))
@click.option("--pk", type=int, default=None, help="AiiDA PK (for 'aiida' source).")
@click.option("--uuid", default=None, help="AiiDA UUID (for 'aiida' source).")
@click.option("--path", default=None, help="Record directory path (for 'directory' source).")
@click.option("--build-membrane-pk", type=int, default=None,
              help="Explicit BuildMembraneWorkChain PK when not in automatic provenance graph.")
@click.option("--run-md-pk", type=int, default=None,
              help="Explicit RunMembraneMDWorkChain PK when not in automatic provenance graph.")
@click.pass_context
def import_record(ctx: click.Context, source: str, pk: int | None, uuid: str | None,
                  path: str | None, build_membrane_pk: int | None,
                  run_md_pk: int | None) -> None:
    """Import a record from a directory or AiiDA workchain."""
    from remembrane.registry import Registry, DuplicateRecordError

    reg = Registry.open(ctx.obj["db"])

    if source == "directory":
        if path is None:
            click.echo("ERROR: --path required for 'directory' source.", err=True)
            sys.exit(1)
        from remembrane.record import MembraneRecord
        from remembrane.storage import verify_artifact
        d = Path(path)
        rec = MembraneRecord.from_yaml(d / "metadata.yaml")
        for artifact in [rec.artifacts.potential_total, rec.artifacts.potential_components]:
            if not verify_artifact(d, artifact.path, artifact.sha256):
                click.echo(f"ERROR: Artifact checksum mismatch: {artifact.path}", err=True)
                sys.exit(1)
        import shutil
        try:
            record_dir = reg.add(rec)
        except DuplicateRecordError as e:
            click.echo(f"ERROR: {e}", err=True)
            sys.exit(1)
        for fname in ["potential_total.npz", "potential_components.npz", "provenance.aiida"]:
            src = d / fname
            if src.exists():
                shutil.copy2(src, record_dir / fname)
        click.echo(f"Imported record {rec.id}")

    elif source == "aiida":
        identifier = uuid or pk
        if identifier is None:
            click.echo("ERROR: --pk or --uuid required for 'aiida' source.", err=True)
            sys.exit(1)
        try:
            from remembrane.aiida.importer import from_potential_workchain
        except ImportError:
            click.echo(
                "ERROR: AiiDA not available. Install remembrane[aiida] to use this command.",
                err=True,
            )
            sys.exit(1)
        from remembrane.aiida.importer import ImportIncompleteError
        try:
            rec, arrays = from_potential_workchain(
                identifier,
                build_membrane_pk=build_membrane_pk,
                run_md_pk=run_md_pk,
            )
        except ImportIncompleteError as e:
            click.echo(f"ERROR: Import incomplete:\n{e}", err=True)
            sys.exit(1)
        try:
            record_dir = reg.add(rec)
        except DuplicateRecordError as e:
            click.echo(f"ERROR: {e}", err=True)
            sys.exit(1)
        from remembrane.storage import save_potential_total, save_potential_components
        sha_total = save_potential_total(record_dir, arrays["z_nm"], arrays["phi_V"])
        sha_comp = save_potential_components(record_dir, arrays["components"], arrays["z_nm"])
        # Update checksums in saved metadata
        rec.artifacts.potential_total.sha256 = sha_total
        rec.artifacts.potential_components.sha256 = sha_comp
        rec.to_yaml(record_dir / "metadata.yaml")
        click.echo(f"Imported record {rec.id}")


@cli.command()
@click.argument("record_id")
@click.pass_context
def verify(ctx: click.Context, record_id: str) -> None:
    """Verify stored artifacts match recorded checksums."""
    from remembrane.registry import Registry, RecordNotFoundError
    from remembrane.storage import verify_artifact
    import numpy as np

    reg = Registry.open(ctx.obj["db"])
    try:
        rec = reg.get(record_id)
    except RecordNotFoundError as e:
        click.echo(str(e), err=True)
        sys.exit(1)
    d = reg.record_dir(record_id)
    errors = []

    for name, artifact in [
        ("potential_total", rec.artifacts.potential_total),
        ("potential_components", rec.artifacts.potential_components),
    ]:
        if not verify_artifact(d, artifact.path, artifact.sha256):
            errors.append(f"{name}: checksum mismatch or file missing")

    errors, warnings = _verify_record(rec, d)

    for e in errors:
        click.echo(f"ERROR: {e}", err=True)
    for w in warnings:
        click.echo(f"WARNING: {w}")

    if errors:
        sys.exit(1)
    click.echo(f"OK: {record_id}")


@cli.group(name="export")
def export_group() -> None:
    """Export records or provenance archives."""


@export_group.command(name="aiida-archive")
@click.argument("record_id")
@click.option("--output", default=None, help="Output path for .aiida archive.")
@click.pass_context
def export_aiida_archive(ctx: click.Context, record_id: str, output: str | None) -> None:
    """Export AiiDA provenance archive for a record."""
    from remembrane.registry import Registry, RecordNotFoundError
    reg = Registry.open(ctx.obj["db"])
    try:
        rec = reg.get(record_id)
    except RecordNotFoundError as e:
        click.echo(str(e), err=True)
        sys.exit(1)
    if rec.aiida_refs.compute_potential_wc is None:
        click.echo("ERROR: No AiiDA UUID stored for this record.", err=True)
        sys.exit(1)
    try:
        from remembrane.aiida.export import export_provenance_archive
    except ImportError:
        click.echo(
            "ERROR: AiiDA not available. Install remembrane[aiida] to use this command.",
            err=True,
        )
        sys.exit(1)
    out_path = output or str(reg.record_dir(record_id) / "provenance.aiida")
    export_provenance_archive(rec.aiida_refs.compute_potential_wc, out_path)
    click.echo(f"Archive written to {out_path}")


@export_group.command(name="json")
@click.option("--all", "export_all", is_flag=True, default=False, help="Export all records.")
@click.option("--output", default=None, help="Output file path (default: stdout).")
@click.option("--lipid", multiple=True, help="Filter: require this lipid.")
@click.pass_context
def export_json(ctx: click.Context, export_all: bool, output: str | None, lipid) -> None:
    """Export records as JSON."""
    from remembrane.registry import Registry
    from remembrane.query import filter_records
    from remembrane.export import records_to_json

    reg = Registry.open(ctx.obj["db"])
    records = reg.list()
    if not export_all and lipid:
        records = filter_records(records, lipid=list(lipid))
    elif not export_all and not lipid:
        pass  # export all by default when no filter given

    result = records_to_json(records)
    if output:
        Path(output).write_text(result)
        click.echo(f"Wrote {len(records)} record(s) to {output}")
    else:
        click.echo(result)


@export_group.command(name="csv")
@click.option("--all", "export_all", is_flag=True, default=False, help="Export all records.")
@click.option("--output", default=None, help="Output file path (default: stdout).")
@click.option("--lipid", multiple=True, help="Filter: require this lipid.")
@click.pass_context
def export_csv(ctx: click.Context, export_all: bool, output: str | None, lipid) -> None:
    """Export records as CSV (composition + potential metadata, one row per record)."""
    from remembrane.registry import Registry
    from remembrane.query import filter_records
    from remembrane.export import records_to_csv

    reg = Registry.open(ctx.obj["db"])
    records = reg.list()
    if not export_all and lipid:
        records = filter_records(records, lipid=list(lipid))

    result = records_to_csv(records)
    if output:
        Path(output).write_text(result)
        click.echo(f"Wrote {len(records)} record(s) to {output}")
    else:
        click.echo(result, nl=False)


@cli.command(name="plot")
@click.argument("record_ids", nargs=-1)
@click.option("--lipid", multiple=True, help="Query: require this lipid (repeatable).")
@click.option("--min-fraction", nargs=2, metavar="LIPID FRAC",
              help="Query: minimum combined leaflet fraction.")
@click.option("--force-field", default=None, help="Query: filter by force field.")
@click.option("--temperature", type=float, default=None, help="Query: filter by temperature (K).")
@click.option("--tag", multiple=True, help="Query: require this tag (repeatable).")
@click.option("--components", is_flag=True, default=False,
              help="Show decomposed component profiles.")
@click.option("--title", default=None, help="Figure title.")
@click.option("--output", default=None,
              help="Save to file (PNG, PDF, SVG…) instead of showing interactively.")
@click.pass_context
def plot_cmd(ctx: click.Context, record_ids, lipid, min_fraction, force_field,
             temperature, tag, components, title, output) -> None:
    """Plot electrostatic potential profiles.

    Pass record IDs to plot specific records, or use query options (--lipid, etc.)
    to select by composition. The two modes are mutually exclusive.

    Examples:\n
      remembrane plot <id>\n
      remembrane plot <id> --components --output profile.png\n
      remembrane plot --lipid POPC --output comparison.png\n
      remembrane plot <id1> <id2>
    """
    from remembrane.registry import Registry, RecordNotFoundError
    from remembrane.query import filter_records

    has_ids = bool(record_ids)
    has_query = bool(lipid or min_fraction or force_field or temperature or tag)

    if has_ids and has_query:
        click.echo("ERROR: Provide either record IDs or query options, not both.", err=True)
        sys.exit(1)
    if not has_ids and not has_query:
        click.echo("ERROR: Provide at least one record ID or a query option.", err=True)
        sys.exit(1)

    try:
        from remembrane.plot import plot_profile, plot_comparison
    except ImportError:
        click.echo(
            "ERROR: matplotlib is required for plotting. "
            "Install it with: pip install remembrane[plot]",
            err=True,
        )
        sys.exit(1)

    reg = Registry.open(ctx.obj["db"])

    if has_ids:
        records = []
        for rid in record_ids:
            try:
                records.append(reg.get(rid))
            except RecordNotFoundError as e:
                click.echo(f"ERROR: {e}", err=True)
                sys.exit(1)
    else:
        mf = (min_fraction[0], float(min_fraction[1])) if min_fraction else None
        records = filter_records(
            reg.list(),
            lipid=list(lipid) or None,
            min_fraction=mf,
            force_field=force_field,
            temperature_K=temperature,
            tags=list(tag) or None,
        )
        if not records:
            click.echo("No records match the query.")
            return

    record_dirs = [reg.record_dir(rec.id) for rec in records]

    if len(records) == 1:
        fig = plot_profile(records[0], record_dirs[0], components=components, title=title)
    else:
        fig = plot_comparison(records, record_dirs, components=components, title=title)

    if output:
        fig.savefig(output, dpi=150, bbox_inches="tight")
        click.echo(f"Saved to {output}")
    else:
        import matplotlib.pyplot as plt
        plt.show()


@cli.command()
@click.option("--pk", type=int, default=None, help="AiiDA PK of the ComputeMembranePotentialWorkChain.")
@click.option("--uuid", default=None, help="AiiDA UUID of the workchain.")
@click.option("--components", is_flag=True, default=False, help="Show decomposed component profiles.")
@click.option("--title", default=None, help="Figure title (default: auto-generated from PK).")
@click.option("--output", default=None, help="Save to file instead of showing interactively.")
def preview(pk: int | None, uuid: str | None, components: bool, title: str | None,
            output: str | None) -> None:
    """Preview a potential profile directly from AiiDA without importing it.

    Use this to quickly inspect a ComputeMembranePotentialWorkChain result
    before deciding whether to add it to the database.

    Examples:\n
      remembrane preview --pk 1894\n
      remembrane preview --pk 1894 --components --output /tmp/preview.png
    """
    identifier = uuid or pk
    if identifier is None:
        click.echo("ERROR: Provide --pk or --uuid.", err=True)
        sys.exit(1)

    try:
        from remembrane.aiida.preview import preview_from_workchain
    except ImportError:
        click.echo(
            "ERROR: AiiDA not available. Install remembrane[aiida] to use this command.",
            err=True,
        )
        sys.exit(1)

    try:
        fig, label = preview_from_workchain(identifier, components=components)
    except Exception as e:
        click.echo(f"ERROR: {e}", err=True)
        sys.exit(1)

    if title:
        fig.axes[0].set_title(title)
        fig.tight_layout()

    if output:
        fig.savefig(output, dpi=150, bbox_inches="tight")
        click.echo(f"Saved to {output}")
    else:
        import matplotlib.pyplot as plt
        plt.show()


@cli.command(name="rebuild-index")
@click.option("--dry-run", is_flag=True, default=False,
              help="Show what would change without writing.")
@click.pass_context
def rebuild_index(ctx: click.Context, dry_run: bool) -> None:
    """Rebuild index.json by scanning all record directories.

    Use this if index.json is missing, corrupted, or out of sync with disk.
    """
    from remembrane.registry import Registry
    reg = Registry.open(ctx.obj["db"])
    old_index = reg._load_index()
    new_index = reg.rebuild_index() if not dry_run else _compute_index(reg)

    added   = {k for k in new_index if k not in old_index}
    removed = {k for k in old_index if k not in new_index}
    changed = {k for k in new_index if k in old_index and new_index[k] != old_index[k]}

    for k in sorted(added):
        click.echo(f"  + {k}")
    for k in sorted(removed):
        click.echo(f"  - {k}")
    for k in sorted(changed):
        click.echo(f"  ~ {k}  (hash changed)")

    if not added and not removed and not changed:
        click.echo("Index is already consistent — no changes.")
    elif dry_run:
        click.echo(f"Dry run: {len(added)} added, {len(removed)} removed, {len(changed)} changed.")
    else:
        click.echo(f"Rebuilt: {len(new_index)} record(s) indexed.")


def _compute_index(reg) -> dict:
    """Like rebuild_index but without writing (for dry-run)."""
    from remembrane.record import MembraneRecord
    index: dict = {}
    if reg._records_dir.exists():
        for d in sorted(reg._records_dir.iterdir()):
            meta = d / "metadata.yaml"
            if d.is_dir() and meta.exists():
                try:
                    rec = MembraneRecord.from_yaml(meta)
                    index[str(rec.id)] = rec.scientific_hash
                except Exception:
                    pass
    return index


@cli.command()
@click.option("--checksums", is_flag=True, default=False,
              help="Also verify artifact checksums for every record (slower).")
@click.pass_context
def doctor(ctx: click.Context, checksums: bool) -> None:
    """Check database health: index consistency and (optionally) artifact integrity.

    Exit code 0 if healthy, 1 if any issues found.
    """
    from remembrane.registry import Registry
    from remembrane.record import MembraneRecord
    from pathlib import Path

    reg = Registry.open(ctx.obj["db"])
    index = reg._load_index()
    issues: list[str] = []

    # Check 1: every index entry has a directory + metadata.yaml
    for rid in index:
        d = reg.record_dir(rid)
        if not d.exists():
            issues.append(f"Index entry {rid}: directory missing")
        elif not (d / "metadata.yaml").exists():
            issues.append(f"Index entry {rid}: metadata.yaml missing")

    # Check 2: every record directory has an index entry
    if reg._records_dir.exists():
        for d in reg._records_dir.iterdir():
            if d.is_dir() and (d / "metadata.yaml").exists():
                if d.name not in index:
                    issues.append(f"Directory {d.name}: not in index (run rebuild-index)")

    # Check 3: optional artifact verification
    if checksums:
        for rid in index:
            d = reg.record_dir(rid)
            if not d.exists():
                continue
            try:
                rec = MembraneRecord.from_yaml(d / "metadata.yaml")
            except Exception as e:
                issues.append(f"{rid}: metadata.yaml unreadable: {e}")
                continue
            errors, warnings = _verify_record(rec, d)
            for e in errors:
                issues.append(f"{rid}: {e}")
            for w in warnings:
                click.echo(f"WARNING {rid}: {w}")

    if issues:
        for issue in issues:
            click.echo(f"ISSUE: {issue}", err=True)
        click.echo(f"\n{len(issues)} issue(s) found.", err=True)
        sys.exit(1)
    else:
        n = len(index)
        extra = " (checksums verified)" if checksums else ""
        click.echo(f"Healthy: {n} record(s){extra}.")


def _verify_record(rec, record_dir: "Path") -> tuple[list[str], list[str]]:
    """Return (errors, warnings) for a single record's stored artifacts."""
    import numpy as np
    from remembrane.storage import verify_artifact

    errors: list[str] = []
    warnings: list[str] = []

    # Checksum verification
    for name, artifact in [
        ("potential_total", rec.artifacts.potential_total),
        ("potential_components", rec.artifacts.potential_components),
    ]:
        if not verify_artifact(record_dir, artifact.path, artifact.sha256):
            errors.append(f"{name}: checksum mismatch or file missing")

    # Array shape and key compatibility
    total_path = record_dir / "potential_total.npz"
    comp_path  = record_dir / "potential_components.npz"
    if total_path.exists() and comp_path.exists():
        total = np.load(total_path)
        comp  = np.load(comp_path)

        if "z_nm" not in total or "phi_V" not in total:
            errors.append("potential_total.npz: missing z_nm or phi_V keys")
        if "z_nm" not in comp:
            errors.append("potential_components.npz: missing z_nm key")
        elif "z_nm" in total and total["z_nm"].shape != comp["z_nm"].shape:
            errors.append("potential_total and potential_components have incompatible z grids")

        # Scientific: all declared component groups must be present
        if "phi_V" in total:
            missing_groups = [
                g for g in rec.potential_meta.component_groups if g not in comp
            ]
            if missing_groups:
                errors.append(
                    f"potential_components.npz: missing groups {missing_groups}"
                )

            # Scientific: component sum should approximate the total
            phi_total = total["phi_V"]
            present = [g for g in rec.potential_meta.component_groups if g in comp]
            if present and phi_total.size > 0:
                phi_sum = sum(comp[g] for g in present)
                residual = np.abs(phi_sum - phi_total)
                tolerance = 0.1 * (phi_total.max() - phi_total.min())
                if tolerance > 0 and residual.mean() > tolerance:
                    warnings.append(
                        f"Component sum deviates from total by "
                        f"{residual.mean():.3f} V mean "
                        f"(tolerance {tolerance:.3f} V)"
                    )

    return errors, warnings


def _composition_summary(rec) -> str:
    def _leaflet(leaflet) -> str:
        return "+".join(f"{n}:{v.fraction:.2f}" for n, v in leaflet.lipids.items())
    upper = _leaflet(rec.composition.upper_leaflet)
    lower = _leaflet(rec.composition.lower_leaflet)
    comp = f"{upper} | {lower}" if upper != lower else upper
    return f"{rec.composition.force_field} T={rec.composition.temperature_K}K [{comp}]"
