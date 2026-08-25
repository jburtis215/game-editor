"""Derived "feel" numbers for the blueprint export.

Python port of the formulas in frontend/src/lib/systemSimMath.ts — the same numbers that
drive the Systems-tab simulations and their plain-language takeaways. Keep the two in sync:
if a constant changes there, change it here. Ported (rather than shared) because the export
must not depend on a Node toolchain; the formulas are a few lines each.

Only the systems relevant to downstream builders are derived here (health, movement,
stamina); the raw answers for every system are exported alongside regardless.
"""
import math
from typing import Any

POOL = 100
EARTH_GRAVITY_UNITS = 25.0  # units/sec² at gravity=100%
AUTO_REGEN_FRACTION = 0.4
PICKUP_HEAL = 25
PICKUP_EVERY_N_HITS = 3
JUMP_COST = 15
SPRINT_COST_PER_S = 25


def _num(values: dict, key: str, fallback: float) -> float:
    v = values.get(key)
    return float(v) if isinstance(v, (int, float)) else fallback


def derive_health(values: dict[str, Any]) -> dict[str, Any]:
    lethality = max(5.0, min(100.0, _num(values, "lethality", 65)))
    regen = values.get("regen") or "auto"
    hp, hits = float(POOL), 0
    while hp > 0 and hits < 24:
        hp -= lethality
        hits += 1
        if hp <= 0:
            break
        if regen == "auto":
            hp = min(POOL, hp + lethality * AUTO_REGEN_FRACTION)
        elif regen == "pickup" and hits % PICKUP_EVERY_N_HITS == 0:
            hp = min(POOL, hp + PICKUP_HEAL)
    died = hp <= 0
    clause = {
        "auto": " — but breathing room heals the damage",
        "pickup": " — unless they find a pickup",
        "rest": " — damage sticks until the next rest",
        "never": " — and every scratch is permanent",
    }.get(regen, "")
    takeaway = (
        f"A careless player dies in ~{hits} hit{'' if hits == 1 else 's'}{clause}"
        if died
        else "Damage wears the player down, but recovery outpaces it — a single fight can't kill"
    )
    return {"damage_per_hit": lethality, "hits_to_die": hits, "takeaway": takeaway}


def derive_movement(values: dict[str, Any]) -> dict[str, Any]:
    jump_height = max(1.0, min(10.0, _num(values, "jumpHeight", 3)))
    gravity_pct = max(10.0, min(200.0, _num(values, "gravity", 100)))
    run_speed = max(1.0, min(20.0, _num(values, "runSpeed", 8)))
    g = EARTH_GRAVITY_UNITS * (gravity_pct / 100.0)
    v0 = math.sqrt(2 * g * jump_height)
    hang = 2 * v0 / g
    feel = " — moon-bounce floaty" if hang >= 1.6 else " — snappy and heavy" if hang <= 0.6 else ""
    return {
        "gravity_units_per_s2": round(g, 2),
        "jump_velocity_units_per_s": round(v0, 2),
        "hang_time_s": round(hang, 2),
        "run_speed_units_per_s": run_speed,
        "jump_height_units": jump_height,
        "takeaway": f"Jumps {jump_height:g} unit{'' if jump_height == 1 else 's'} high · ~{hang:.1f}s of hang time{feel}",
    }


def derive_stamina(values: dict[str, Any]) -> dict[str, Any]:
    regen_rate = max(1.0, min(50.0, _num(values, "regenRate", 12)))
    drains = values.get("drains") if isinstance(values.get("drains"), list) else []
    bits = [f"Empty to full in ~{math.ceil(POOL / regen_rate)}s of rest"]
    if "jump" in drains:
        bits.append(f"chain ~{POOL // JUMP_COST} jumps before gasping")
    if "sprint" in drains:
        bits.append(f"~{POOL / SPRINT_COST_PER_S:.1f}s of full sprint")
    takeaway = (
        "Nothing drains stamina" if not drains else " · ".join(bits)
    )
    return {"refill_seconds": round(POOL / regen_rate, 1), "drains": drains, "takeaway": takeaway}


DERIVERS = {"health": derive_health, "movement": derive_movement, "stamina": derive_stamina}


def derive_for_system(system_id: str, values: dict[str, Any]) -> dict[str, Any] | None:
    fn = DERIVERS.get(system_id)
    return fn(values or {}) if fn else None
