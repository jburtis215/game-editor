"""Recording what got built, and working out what has since gone stale.

The platform cannot see inside an engine project — the boundary is deliberate (no daemons,
no per-engine plugins, agent-mediated only), so everything it knows about a build arrives
through `record_build`. What makes that worth doing is the hash: an agent reports which
*version* of the design it built from, and from then on the platform alone can tell that
the designer has changed that object since. No engine access, no reconcile pass, no
cooperation from the agent — just a comparison.

Staleness and rename-drift are derived at read time, never stored. A stored "is stale" flag
would itself need invalidating every time the design changed, which is the bug it was meant
to catch.
"""
from __future__ import annotations

from typing import Any

from ..models import BuildRecord, Project
from . import addressing, manifest

VALID_STATUSES = {BuildRecord.IN_PROGRESS, BuildRecord.BUILT, BuildRecord.VERIFIED}


class ReportError(ValueError):
    """A report that can't be accepted — the message is written to be read by an agent."""


def record_build(
    project: Project,
    *,
    address: str,
    engine_path: str = "",
    built_hash: str = "",
    status: str = BuildRecord.BUILT,
    engine: str = "godot",
    note: str = "",
) -> dict[str, Any]:
    """Record (or update) what an agent built for one design object.

    Rejects an address that names nothing in this project. That check is the point: an
    agent that invented an address instead of reading one would otherwise file a report
    nothing can ever match, and the gap would look like unbuilt work forever.
    """
    if status not in VALID_STATUSES:
        raise ReportError(
            f"status must be one of {sorted(VALID_STATUSES)}, not {status!r}."
        )

    resolved = addressing.resolve_any(project, address)
    if resolved is None:
        raise ReportError(
            f"'{address}' doesn't name anything in project {project.id}. Addresses come "
            "from get_manifest — don't construct them by hand."
        )

    current_address = resolved["current"]
    object_type = resolved["object_type"]
    object_id = resolved["object_id"]

    # Prefer the durable key so a report filed under an old address updates the same record
    # instead of forking a second one.
    record = None
    if object_id is not None:
        record = BuildRecord.objects.filter(
            project=project, engine=engine, object_type=object_type, object_id=object_id
        ).first()
    if record is None:
        record = BuildRecord.objects.filter(
            project=project, engine=engine, address=current_address
        ).first()

    if record is None:
        record = BuildRecord(project=project, engine=engine)

    record.address = current_address
    record.object_type = object_type
    record.object_id = object_id
    record.status = status
    if engine_path:
        record.engine_path = engine_path
    if built_hash:
        record.built_hash = built_hash
    if note:
        record.note = note
    record.save()

    current_hash = _current_hashes(project).get(current_address, "")
    out: dict[str, Any] = {
        "address": current_address,
        "engine": engine,
        "engine_path": record.engine_path,
        "status": record.status,
        "built_hash": record.built_hash,
        "current_hash": current_hash,
        "stale": bool(record.built_hash and current_hash and record.built_hash != current_hash),
        "recorded": True,
    }
    if resolved["renamed_from"]:
        out["renamed_from"] = resolved["renamed_from"]
        out["note_to_agent"] = (
            f"You reported '{resolved['renamed_from']}', which the creator has since renamed "
            f"to '{current_address}'. The record was filed under the new name — rename the "
            "engine artifact and your sync manifest entry to match."
        )
    elif out["stale"]:
        out["note_to_agent"] = (
            f"Recorded, but the design for '{current_address}' has already moved on since "
            f"hash {record.built_hash} (it is now {current_hash}). Re-read it before "
            "considering this done."
        )
    elif not record.built_hash:
        out["note_to_agent"] = (
            "Recorded without a hash, so staleness can't be detected for this object later. "
            "Pass the object's `hash` from the manifest next time."
        )
    return out


def _current_hashes(project: Project) -> dict[str, str]:
    """Address -> current design hash, for every object in the project."""
    return {
        obj["address"]: obj.get("hash", "")
        for obj in manifest.build_manifest(project)["objects"]
    }


def build_status(project: Project, engine: str = "godot") -> dict[str, Any]:
    """Every design object with what's been built for it, what's stale, and the rollup.

    An object is `stale` when its design hash no longer matches the hash it was built
    against, and `renamed` when the creator has renamed it since — both meaning the engine
    side needs another pass, for different reasons.
    """
    index = manifest.build_manifest(project)
    records = list(BuildRecord.objects.filter(project=project, engine=engine))
    by_object = {(r.object_type, r.object_id): r for r in records if r.object_id is not None}
    by_address = {r.address: r for r in records}

    objects: list[dict[str, Any]] = []
    for obj in index["objects"]:
        address = obj["address"]
        kind, _, _ = address.partition(":")
        record = by_address.get(address)
        if record is None:
            resolved = addressing.resolve_any(project, address)
            if resolved and resolved["object_id"] is not None:
                record = by_object.get((resolved["object_type"], resolved["object_id"]))

        entry: dict[str, Any] = {
            "address": address,
            "name": obj.get("name"),
            "kind": obj.get("kind", kind),
            "current_hash": obj.get("hash", ""),
            "status": "not_built",
            "stale": False,
            "renamed": False,
            "engine_path": "",
            "built_hash": "",
            "reported_at": None,
        }
        if record is not None:
            entry.update(
                {
                    "status": record.status,
                    "engine_path": record.engine_path,
                    "built_hash": record.built_hash,
                    "reported_at": record.reported_at.isoformat(),
                    "stale": bool(
                        record.built_hash
                        and entry["current_hash"]
                        and record.built_hash != entry["current_hash"]
                    ),
                    # The record was filed under a name the object no longer answers to, so
                    # the engine-side artifact is named wrong.
                    "renamed": record.address != address,
                }
            )
            if record.address != address:
                entry["built_as"] = record.address
            if record.note:
                entry["note"] = record.note
        objects.append(entry)

    total = len(objects)
    done = [o for o in objects if o["status"] in (BuildRecord.BUILT, BuildRecord.VERIFIED)]
    current = [o for o in done if not o["stale"]]
    summary = {
        "total": total,
        "not_built": sum(1 for o in objects if o["status"] == "not_built"),
        "in_progress": sum(1 for o in objects if o["status"] == BuildRecord.IN_PROGRESS),
        "built": sum(1 for o in objects if o["status"] == BuildRecord.BUILT),
        "verified": sum(1 for o in objects if o["status"] == BuildRecord.VERIFIED),
        "stale": sum(1 for o in objects if o["stale"]),
        "renamed": sum(1 for o in objects if o["renamed"]),
        # "Built" counts only what is built AND current — a stale build is work still owed.
        "percent_built": round(100 * len(current) / total) if total else 0,
    }

    # Orphans: reports for addresses that no longer appear in the design at all (the object
    # was deleted). Surfaced rather than hidden — the engine still has a file for it.
    live = {o["address"] for o in objects}
    orphans = [
        {"address": r.address, "engine_path": r.engine_path, "status": r.status}
        for r in records
        if r.address not in live
    ]

    return {
        "project": index["project"],
        "engine": engine,
        "summary": summary,
        "objects": objects,
        "orphaned_reports": orphans,
    }
