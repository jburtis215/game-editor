"""Reconciling what the build did against what the design said.

`build_reports` records *that* an object was built. This module handles the harder half:
the build and the design disagreeing about a specific value, and the design having been
silent about a value the build could not avoid deciding.

Three ideas do most of the work here.

**Field addresses.** `system:movement.gravity` names one value, not an object. A creator
can accept or reject "the build uses gravity 260, the design says 200"; nobody can act on
"the movement system differs". The field is resolved against the blueprint, so the address
an agent reports is the same address the export publishes.

**The platform reads the design itself.** A reporting agent says what the *build* does and
nothing more — `design_value` is looked up here. If the reporter supplied it, an agent
could misquote the design into a disagreement that doesn't exist, or file a genuine
contradiction as a harmless gap and have it written straight into the design. So the one
claim that decides how a report is treated is the one claim we never accept on trust.

**Kind decides handling** (the policy is `docs/VISION.md` Phase 4):

- The design specifies a value and the build differs → `CONFLICT`, held **pending**. The
  design is canonical; nothing is overwritten without the creator.
- The design says nothing → `GAP`. There is no disagreement to adjudicate and nothing to
  overwrite, so the value is written into the design and marked as originating in the
  build. The design becomes more complete instead of quietly drifting from the build.

Only the *knob bags* are writable — a system's `values`, an ability's `params`, an entity's
`behavior`. Those are collections of tuned numbers, which is exactly the shape an engine
invents values in; every gap the Godot demo produced was one. Authored prose and structure
(names, descriptions, layouts, dialogue) are deliberately not writable from a build: a
build has no standing to rewrite what a creator wrote, and a silent name change would break
the address that the whole loop is keyed on.
"""
from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils import timezone

from ..models import Ability, BuildRecord, Deviation, EntityType, Project
from . import addressing, blueprint

# address kind -> the object's writable "knob bag" in both the blueprint and the DB.
# A kind absent from this map can still have deviations recorded against it; they just
# can't be applied automatically.
WRITABLE_BAGS = {
    "system": "values",
    "ability": "params",
    "entity": "behavior",
}

# Fields that are part of an object's identity or its authored content. Reported as
# deviations (worth knowing the build disagrees), never written back.
READ_ONLY_FIELDS = {"name", "address", "hash", "id", "description", "glyph"}


class DeviationError(ValueError):
    """A report that can't be accepted — the message is written to be read by an agent."""


def split_address(address: str) -> tuple[str, str]:
    """`system:movement.gravity` -> (`system:movement`, `gravity`).

    Splits on the first dot *after* the colon, so a field name is separated from the
    address while an address containing no field comes back with an empty field.
    """
    address = (address or "").strip()
    kind, sep, rest = address.partition(":")
    if not sep:
        return address, ""
    name, dot, field = rest.partition(".")
    return f"{kind}:{name}", field if dot else ""


def _index(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Every addressable object in a blueprint, keyed by its address.

    Built from the export rather than from the models so that the value a deviation is
    compared against is the same value the agent was served.
    """
    index: dict[str, dict[str, Any]] = {}

    for entry in (document.get("systems") or {}).values():
        if entry.get("address"):
            index[entry["address"]] = entry
    for entry in document.get("abilities") or []:
        if entry.get("address"):
            index[entry["address"]] = entry
    for entry in document.get("entity_types") or []:
        if entry.get("address"):
            index[entry["address"]] = entry
    for entry in document.get("characters") or []:
        if entry.get("address"):
            index[entry["address"]] = entry
    for entry in (document.get("state_schema") or {}).values():
        if entry.get("address"):
            index[entry["address"]] = entry
    for level in document.get("levels") or []:
        if level.get("address"):
            index[level["address"]] = level
        for loc in level.get("locations") or []:
            if loc.get("address"):
                index[loc["address"]] = loc
        for scene in level.get("scenes") or []:
            if scene.get("address"):
                index[scene["address"]] = scene
    return index


def read_design_value(
    document: dict[str, Any], address: str
) -> tuple[bool, Any, dict[str, Any] | None]:
    """What the design says at `address`. Returns (specified, value, the object's export slice).

    `specified` is False when the object exists but says nothing about that field — which
    is what separates a gap from a conflict, so it is deliberately distinct from a value of
    None or 0 or "".
    """
    base, field = split_address(address)
    obj = _index(document).get(base)
    if obj is None:
        return False, None, None
    if not field:
        return True, obj, obj

    if field in obj and field not in ("values", "params", "behavior"):
        return True, obj[field], obj

    kind, _, _ = base.partition(":")
    bag_key = WRITABLE_BAGS.get(kind)
    if bag_key:
        bag = obj.get(bag_key) or {}
        # `params.cooldown` and plain `cooldown` name the same value; accept both so an
        # agent doesn't have to know which bag a knob lives in.
        key = field[len(bag_key) + 1 :] if field.startswith(f"{bag_key}.") else field
        if isinstance(bag, dict) and key in bag:
            return True, bag[key], obj
    return False, None, obj


def _same(a: Any, b: Any) -> bool:
    """Value equality that doesn't trip over JSON's number types (200 vs 200.0)."""
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) < 1e-9
    return a == b


def design_values(project: Project) -> dict[str, Any]:
    """The design as a flat `{address, value}` list, for mechanical comparison.

    The nested blueprint is built for comprehension and is the wrong shape for diffing —
    walking it is exactly the work every reconcile pass would otherwise repeat. Only the
    knob bags and scalar fields appear; structure (layouts, dialogue graphs, connections)
    is not diffable one value at a time and is left to the blueprint.
    """
    document = blueprint.build_blueprint(project)
    rows: list[dict[str, Any]] = []
    for address, obj in sorted(_index(document).items()):
        kind, _, _ = address.partition(":")
        bag_key = WRITABLE_BAGS.get(kind)
        if bag_key:
            for key, value in (obj.get(bag_key) or {}).items():
                rows.append({"address": f"{address}.{key}", "value": value, "writable": True})
        for key, value in obj.items():
            if key in ("address", "hash", "former_addresses", bag_key):
                continue
            if isinstance(value, (dict, list)):
                continue  # structure, not a single comparable value
            rows.append({"address": f"{address}.{key}", "value": value, "writable": False})
    return {
        "project": document["project"],
        "count": len(rows),
        "values": rows,
        "note": (
            "Flat design values for diffing against a build. `writable` marks the values a "
            "deviation can be applied to automatically; the rest are authored content and "
            "need the creator. Report each mismatch with report_deviation."
        ),
    }


def _apply_to_design(project: Project, base_address: str, field: str, value: Any) -> str:
    """Write one value into the design. Returns "" on success, or why it couldn't be written."""
    kind, _, _ = base_address.partition(":")
    bag_key = WRITABLE_BAGS.get(kind)
    if not bag_key:
        return f"'{kind}:' objects have no writable values — apply this one by hand."
    key = field[len(bag_key) + 1 :] if field.startswith(f"{bag_key}.") else field
    if not key:
        return "No field named — a whole object can't be replaced by a build."
    if key in READ_ONLY_FIELDS:
        return f"'{key}' is authored content, not a tuned value — apply it by hand if you agree."

    resolved = addressing.resolve_any(project, base_address)
    if resolved is None:
        return f"'{base_address}' no longer names anything in this project."

    if kind == "system":
        system_id = base_address.partition(":")[2]
        systems = dict(project.systems or {})
        state = dict(systems.get(system_id) or {})
        values = dict(state.get("values") or {})
        values[key] = value
        state["values"] = values
        systems[system_id] = state
        project.systems = systems
        project.save(update_fields=["systems"])
        return ""

    if kind == "ability":
        ability = Ability.objects.filter(id=resolved["object_id"], project=project).first()
        if ability is None:
            return f"'{base_address}' no longer names an ability in this project."
        params = dict(ability.params or {})
        params[key] = value
        ability.params = params
        ability.save(update_fields=["params"])
        return ""

    if kind == "entity":
        entity = EntityType.objects.filter(id=resolved["object_id"], project=project).first()
        if entity is None:
            return f"'{base_address}' no longer names an entity in this project."
        behavior = dict(entity.behavior or {})
        behavior[key] = value
        entity.behavior = behavior
        entity.save(update_fields=["behavior"])
        return ""

    return f"'{kind}:' objects can't be written from a build."


def _resync_build_record(project: Project, base_address: str, engine: str) -> None:
    """Re-point the object's build record at the design hash it now has.

    Writing a build's own value into the design changes that object's hash, which would
    otherwise mark the build stale the instant it was reconciled — telling the agent to go
    re-read a value it supplied. The engine and the design agree here; only the fingerprint
    moved, so the record follows it.
    """
    record = BuildRecord.objects.filter(
        project=project, engine=engine, address=base_address
    ).first()
    if record is None or not record.built_hash:
        return
    document = blueprint.build_blueprint(project)
    obj = _index(document).get(base_address)
    if obj and obj.get("hash"):
        record.built_hash = obj["hash"]
        record.save(update_fields=["built_hash"])


@transaction.atomic
def record_deviation(
    project: Project,
    *,
    address: str,
    build_value: Any,
    engine: str = "godot",
    engine_path: str = "",
    note: str = "",
) -> dict[str, Any]:
    """Record one point where the build and the design disagree, or where the design was silent.

    The caller supplies only what the *build* does. What the design says is read here, and
    that reading decides everything: a value the design specifies differently is a conflict
    held for the creator; a value the design never specified is a gap written straight in.
    """
    base, field = split_address(address)
    if not base or ":" not in base:
        raise DeviationError(
            f"'{address}' isn't an address. Use `object:name.field`, e.g. "
            "`system:movement.gravity` — addresses come from get_manifest or get_design_values."
        )

    resolved = addressing.resolve_any(project, base)
    if resolved is None:
        raise DeviationError(
            f"'{base}' doesn't name anything in project {project.id}. Addresses come from "
            "get_manifest — don't construct them by hand."
        )
    current_base = resolved["current"]

    document = blueprint.build_blueprint(project)
    specified, design_value, obj = read_design_value(document, f"{current_base}.{field}" if field else current_base)

    if not field:
        raise DeviationError(
            f"'{address}' names a whole object. A deviation has to name one value so the "
            f"creator can act on it — e.g. `{current_base}.<field>`."
        )

    if specified and _same(design_value, build_value):
        return {
            "address": f"{current_base}.{field}",
            "recorded": False,
            "kind": "match",
            "design_value": design_value,
            "build_value": build_value,
            "note_to_agent": (
                "The design already says exactly this, so there's nothing to reconcile. "
                "Nothing was recorded."
            ),
        }

    kind = Deviation.CONFLICT if specified else Deviation.GAP
    full_address = f"{current_base}.{field}"
    design_hash = (obj or {}).get("hash", "")

    deviation = Deviation.objects.filter(
        project=project, engine=engine, address=full_address
    ).first() or Deviation(project=project, engine=engine, address=full_address)

    deviation.base_address = current_base
    deviation.field = field
    deviation.object_type = resolved["object_type"]
    deviation.object_id = resolved["object_id"]
    deviation.kind = kind
    deviation.design_value = design_value if specified else None
    deviation.build_value = build_value
    deviation.design_hash = design_hash
    if engine_path:
        deviation.engine_path = engine_path
    if note:
        deviation.note = note

    out: dict[str, Any] = {
        "address": full_address,
        "kind": kind,
        "design_value": design_value if specified else None,
        "build_value": build_value,
        "recorded": True,
    }

    if kind == Deviation.GAP:
        # Nothing to overwrite and no disagreement to adjudicate: the design was silent, so
        # this completes it rather than changing it.
        problem = _apply_to_design(project, current_base, field, build_value)
        deviation.status = Deviation.ACCEPTED
        deviation.applied = not problem
        deviation.resolved_at = timezone.now()
        deviation.resolution_note = (
            "Design was silent; value adopted from the build."
            if not problem
            else f"Design was silent, but the value couldn't be written: {problem}"
        )
        deviation.save()
        if not problem:
            _resync_build_record(project, current_base, engine)
        out["status"] = Deviation.ACCEPTED
        out["applied"] = deviation.applied
        out["note_to_agent"] = (
            f"The design didn't specify {full_address}, so your value was recorded as design "
            "and flagged as originating in the build. Keep using it."
            if not problem
            else (
                f"The design didn't specify {full_address}. It's recorded for the creator, but "
                f"couldn't be written automatically: {problem}"
            )
        )
    else:
        deviation.status = Deviation.PENDING
        deviation.applied = False
        deviation.resolved_at = None
        deviation.save()
        out["status"] = Deviation.PENDING
        out["applied"] = False
        out["note_to_agent"] = (
            f"Recorded as a pending deviation: the design says {design_value!r} and your build "
            f"uses {build_value!r}. The design is canonical, so nothing changed — the creator "
            "accepts it into the design or asks for rework. Build to the design value unless "
            "told otherwise."
        )
    out["id"] = deviation.id
    return out


def _serialize(deviation: Deviation, current_hashes: dict[str, str]) -> dict[str, Any]:
    current = current_hashes.get(deviation.base_address, "")
    return {
        "id": deviation.id,
        "address": deviation.address,
        "base_address": deviation.base_address,
        "field": deviation.field,
        "kind": deviation.kind,
        "status": deviation.status,
        "applied": deviation.applied,
        "design_value": deviation.design_value,
        "build_value": deviation.build_value,
        "engine": deviation.engine,
        "engine_path": deviation.engine_path,
        "note": deviation.note,
        "resolution_note": deviation.resolution_note,
        # The creator edited this object after the deviation was filed, so the values quoted
        # here may no longer be the ones in question.
        "stale": bool(deviation.design_hash and current and deviation.design_hash != current),
        "reported_at": deviation.reported_at.isoformat(),
        "resolved_at": deviation.resolved_at.isoformat() if deviation.resolved_at else None,
    }


def list_deviations(
    project: Project, *, status: str | None = None, engine: str | None = None
) -> dict[str, Any]:
    """Every deviation, newest first, with a rollup of what still needs the creator."""
    document = blueprint.build_blueprint(project)
    current_hashes = {addr: obj.get("hash", "") for addr, obj in _index(document).items()}

    qs = Deviation.objects.filter(project=project)
    if engine:
        qs = qs.filter(engine=engine)
    rows = [_serialize(d, current_hashes) for d in qs]
    if status:
        rows = [r for r in rows if r["status"] == status]

    everything = Deviation.objects.filter(project=project)
    return {
        "project": document["project"],
        "summary": {
            "pending": everything.filter(status=Deviation.PENDING).count(),
            "accepted": everything.filter(status=Deviation.ACCEPTED).count(),
            "rejected": everything.filter(status=Deviation.REJECTED).count(),
            "gaps_filled": everything.filter(kind=Deviation.GAP, applied=True).count(),
        },
        "deviations": rows,
    }


@transaction.atomic
def resolve_deviation(
    project: Project, deviation_id: int, *, action: str, note: str = ""
) -> dict[str, Any]:
    """The creator's call on one pending deviation.

    `accept` adopts the build's value into the design (writing it where the address is a
    tuned value, and saying so plainly when it isn't). `reject` keeps the design as it
    stands, which makes the build wrong and the object work still owed.
    """
    if action not in ("accept", "reject"):
        raise DeviationError(f"action must be 'accept' or 'reject', not {action!r}.")

    deviation = Deviation.objects.filter(project=project, id=deviation_id).first()
    if deviation is None:
        raise DeviationError(f"No deviation {deviation_id} in project {project.id}.")

    if action == "reject":
        deviation.status = Deviation.REJECTED
        deviation.applied = False
        deviation.resolution_note = note or "Design stands; the build needs rework."
        deviation.resolved_at = timezone.now()
        deviation.save()
    else:
        problem = _apply_to_design(
            project, deviation.base_address, deviation.field, deviation.build_value
        )
        deviation.status = Deviation.ACCEPTED
        deviation.applied = not problem
        deviation.resolution_note = note or (
            "Accepted into the design." if not problem else f"Accepted, but not written: {problem}"
        )
        deviation.resolved_at = timezone.now()
        deviation.save()
        if not problem:
            _resync_build_record(project, deviation.base_address, deviation.engine)

    document = blueprint.build_blueprint(project)
    current_hashes = {addr: obj.get("hash", "") for addr, obj in _index(document).items()}
    return _serialize(deviation, current_hashes)
