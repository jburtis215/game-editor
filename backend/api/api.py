"""Django Ninja API for the game-editor backend.

Mounted at /api/ (see config/urls.py). Interactive docs are served at /api/docs.
The schemas here drive the OpenAPI spec, which the frontend turns into typed TS
(`npm run gen:api` -> frontend/src/api/schema.d.ts).
"""
import re

from django.db.models import Q
from django.shortcuts import get_object_or_404
from ninja import File, NinjaAPI, Schema
from ninja.files import UploadedFile

from .services import blueprint, imagegen, storage, yarn_export, yarn_import

from typing import Any

from .models import (
    Ability,
    Character,
    CharacterRelationship,
    Dialogue,
    DialogueEdge,
    EntityType,
    Level,
    Location,
    LocationConnection,
    Project,
    Scene,
    User,
)

api = NinjaAPI(title="game-editor API", version="0.1.0")

VALID_THEMES = {choice for choice, _ in User.THEME_CHOICES}


# --- Schemas ----------------------------------------------------------------------------------
class Error(Schema):
    error: str


class UserOut(Schema):
    id: int
    name: str
    theme: str


class UserUpdateIn(Schema):
    """Partial update of the current user (e.g. their selected theme)."""

    name: str | None = None
    theme: str | None = None


class CharacterOut(Schema):
    id: int
    name: str
    description: str = ""
    image_url: str = ""  # derived (presigned) from the character's image_key at read time

    @staticmethod
    def resolve_image_url(obj) -> str:
        key = obj.get("image_key", "") if isinstance(obj, dict) else getattr(obj, "image_key", "")
        return storage.view_url(key)


class RelatedCharacterOut(Schema):
    """A character related to another, plus the relationship's label and edge id."""

    relationship_id: int
    id: int
    name: str
    relationship: str


class CharacterDetailOut(Schema):
    """A single character with its description, portrait, and relationships."""

    id: int
    name: str
    description: str = ""
    image_url: str = ""
    image_key: str = ""
    project_id: int | None = None
    related: list[RelatedCharacterOut] = []
    # {"values": {key: value}, "own": [trait definition, ...]} — see Character.traits. The
    # project's default traits are NOT merged in here; the client overlays them at render time.
    traits: dict[str, Any] = {}


class CharacterCreateIn(Schema):
    name: str = "New Character"
    description: str = ""
    project_id: int | None = None


class CharacterUpdateIn(Schema):
    """Partial update — omitted fields are left unchanged."""

    name: str | None = None
    description: str | None = None
    traits: dict[str, Any] | None = None


class RelationshipCreateIn(Schema):
    other_id: int
    relationship: str = ""


class GenerateImageIn(Schema):
    # Optional; defaults to a prompt built from the character's name + description.
    prompt: str | None = None


class ProjectOut(Schema):
    """A game project plus its game-wide config (settings/systems/HUD)."""

    id: int
    name: str
    order: int
    dimension: str
    genre: str
    systems: dict[str, Any] = {}  # ArchitectState (per-system enabled + answers)
    hud_layout: dict[str, Any] = {}  # HudLayout ({systemId: {x, y}})
    state_schema: dict[str, Any] = {} # this is to help track effects/requirements in choices in dialogue
    # Default character traits — a list of trait definitions applied to every character.
    character_traits: list[dict[str, Any]] = []


class ProjectCreateIn(Schema):
    name: str = "New Project"
    order: int | None = None  # None => appended after the current last project


class ProjectUpdateIn(Schema):
    """Partial update — omitted fields are left unchanged. One PATCH serves rename,
    Settings (dimension/genre), Systems, and Preview (hud_layout) saves."""

    name: str | None = None
    order: int | None = None
    dimension: str | None = None
    genre: str | None = None
    systems: dict[str, Any] | None = None
    hud_layout: dict[str, Any] | None = None
    state_schema: dict[str, Any] | None = None
    character_traits: list[dict[str, Any]] | None = None


class AbilityOut(Schema):
    """A player verb: what it is, the knobs that tune it, and what unlocks it."""

    id: int
    project_id: int | None = None
    name: str
    description: str = ""
    # {key: number|string|bool} — cooldown, distance, uses. Stored verbatim.
    params: dict[str, Any] = {}
    # Same bounded vocabulary as Dialogue.requirements (has_item / stat_check /
    # state_equals / remembered_choice). Empty => available from the start.
    unlock_requirements: list[dict[str, Any]] = []
    order: int


class AbilityCreateIn(Schema):
    project_id: int | None = None
    name: str = "New Ability"
    description: str = ""
    params: dict[str, Any] = {}
    unlock_requirements: list[dict[str, Any]] = []
    order: int | None = None  # None => appended after the project's current last ability


class AbilityUpdateIn(Schema):
    """Partial update — omitted fields are left unchanged; `params` and
    `unlock_requirements` replace the whole value when given."""

    name: str | None = None
    description: str | None = None
    params: dict[str, Any] | None = None
    unlock_requirements: list[dict[str, Any]] | None = None
    order: int | None = None


class LevelOut(Schema):
    id: int
    name: str
    order: int
    project_id: int | None = None
    layout: dict[str, Any] = {}  # {"width": W, "height": H, "rows": [str]} — {} = none drawn
    intro_scene_id: int | None = None


class LevelUpdateIn(Schema):
    """Partial update of a level (rename, layout grid, intro dialogue scene)."""

    name: str | None = None
    order: int | None = None
    layout: dict[str, Any] | None = None
    intro_scene_id: int | None = None  # must be one of this level's scenes; null clears


class LevelCreateIn(Schema):
    name: str = "New Level"
    order: int | None = None  # None => appended after the current last level
    project_id: int | None = None


class LevelCharacterLineOut(Schema):
    id: int
    text: str
    scene_id: int | None = None
    scene_name: str = ""


class LevelCharacterOut(Schema):
    """A character appearing in a level (deduced from dialogue), with the lines they speak."""

    id: int
    name: str
    description: str = ""
    image_url: str = ""
    lines: list[LevelCharacterLineOut] = []


class EntityTypeOut(Schema):
    """A placeable non-character thing (enemy/hazard/pickup/prop) in a project's palette."""

    id: int
    name: str
    glyph: str
    category: str
    description: str = ""
    behavior: dict[str, Any] = {}
    project_id: int
    image_url: str = ""  # derived (presigned) from image_key at read time

    @staticmethod
    def resolve_image_url(obj) -> str:
        key = obj.get("image_key", "") if isinstance(obj, dict) else getattr(obj, "image_key", "")
        return storage.view_url(key)


class EntityTypeCreateIn(Schema):
    project_id: int
    name: str
    glyph: str  # single character, unique per project, not a built-in tile glyph
    category: str = EntityType.CATEGORY_ENEMY
    description: str = ""
    behavior: dict[str, Any] = {}


class EntityTypeUpdateIn(Schema):
    """Partial update — omitted fields are left unchanged."""

    name: str | None = None
    glyph: str | None = None
    category: str | None = None
    description: str | None = None
    behavior: dict[str, Any] | None = None


class SceneOut(Schema):
    id: int
    name: str
    level_id: int
    level_name: str
    location_id: int | None = None


class SceneCreateIn(Schema):
    name: str = "New Scene"
    level_id: int
    location_id: int | None = None
    order: int | None = None  # None => appended after the level's current last scene


class SceneUpdateIn(Schema):
    """Partial update — omitted fields are left unchanged."""

    name: str | None = None
    location_id: int | None = None
    order: int | None = None


class LocationConnectionOut(Schema):
    """A way out of the location whose row this appears on, described *relative to it*:
    `other_id`/`other_name` is the place at the far end and `direction` says which way the
    edge was authored ("out" = from this location; "in" = a bidirectional connection
    authored from the other side, so it's still walkable from here)."""

    id: int
    from_location_id: int
    to_location_id: int
    other_id: int
    other_name: str
    direction: str  # "out" | "in"
    label: str = ""
    bidirectional: bool = True
    # Same bounded vocabulary as Dialogue.requirements (has_item / stat_check /
    # state_equals / remembered_choice) — the lock on this exit.
    requirements: list[dict[str, Any]] = []


class LocationOut(Schema):
    """A place within a level: its detail fields, reference image, cast, and exits."""

    id: int
    name: str
    description: str = ""
    order: int
    level_id: int
    kind: str = ""  # "interior" | "exterior" | ""
    scale: str = ""  # "cramped" | "room" | "open" | "vast" | ""
    mood: str = ""
    props: list[str] = []
    image_url: str = ""  # derived (presigned) from image_key at read time
    image_key: str = ""
    characters: list[CharacterOut] = []
    connections: list[LocationConnectionOut] = []


class LocationCreateIn(Schema):
    name: str = "New Location"
    description: str = ""
    order: int | None = None  # None => appended after the level's current last location
    level_id: int | None = None
    kind: str | None = None  # "interior" | "exterior"
    scale: str | None = None  # "cramped" | "room" | "open" | "vast"
    mood: str | None = None
    props: list[str] | None = None


class LocationUpdateIn(Schema):
    """Partial update — omitted fields are left unchanged."""

    name: str | None = None
    description: str | None = None
    order: int | None = None
    kind: str | None = None
    scale: str | None = None
    mood: str | None = None
    props: list[str] | None = None


class LocationCharacterIn(Schema):
    character_id: int


class LocationConnectionIn(Schema):
    """Connect this location to another one in the same level."""

    to_id: int
    label: str = ""
    bidirectional: bool = True
    requirements: list[dict[str, Any]] = []


class DialogueSummaryOut(Schema):
    """Lightweight dialogue used for root lists and response cards. `option_label` is the
    edge's player-facing choice text (falls back to `text` when the edge has none set)."""

    id: int
    title: str
    text: str
    option_label: str = ""
    character: CharacterOut | None = None
    requirements: list[dict[str, Any]] = []
    effects: list[dict[str, Any]] = []


class DialogueParentOut(Schema):
    """A node that links to the current one — powers the back-navigation picker when a
    node is reachable from more than one place."""

    id: int
    title: str
    text: str


class DialogueDetailOut(Schema):
    """The current dialogue plus its immediate responses (the wheel) and the node(s) that
    link to it (0 = scene root, 1 = normal back-nav, 2+ = picker)."""

    id: int
    title: str
    text: str
    scene_id: int | None = None
    parents: list[DialogueParentOut] = []
    character: CharacterOut | None = None
    requirements: list[dict[str, Any]] = []
    effects: list[dict[str, Any]] = []
    responses: list[DialogueSummaryOut] = []


class DialogueNodeOut(Schema):
    """A single node in a scene's flat dialogue list — enough to lay out the whole graph."""

    id: int
    title: str
    parent_ids: list[int] = []
    text: str
    character: CharacterOut | None = None
    requirements: list[dict[str, Any]] = []
    effects: list[dict[str, Any]] = []


class DialogueIn(Schema):
    """Payload to create a dialogue (optionally as a response of `parent_id`)."""

    scene_id: int | None = None
    parent_id: int | None = None
    character_id: int | None = None
    text: str = ""
    requirements: list[dict[str, Any]] | None = None
    effects: list[dict[str, Any]] | None = None


class DialogueUpdateIn(Schema):
    """Partial update — omitted fields are left unchanged."""

    character_id: int | None = None
    text: str | None = None
    requirements: list[dict[str, Any]] | None = None
    effects: list[dict[str, Any]] | None = None


class DialogueLinkIn(Schema):
    """Attach an existing node as an additional response of another existing node — the
    concrete "reuse/reconverge" action (no new Dialogue row, just a new edge)."""

    target_id: int
    option_label: str = ""


class YarnImportIn(Schema):
    text: str
    parent_id: int | None = None


class YarnImportOut(Schema):
    """Result of a Yarn import: how much landed, its new root(s), and anything skipped."""

    created: int
    root_ids: list[int] = []
    warnings: list[str] = []


class YarnExportOut(Schema):
    filename: str
    text: str


# --- Auth (placeholder) -----------------------------------------------------------------------
@api.post("/auth", response={400: Error}, summary="Authenticate the user (placeholder)")
def auth(request):
    """Placeholder for future authentication.

    Always returns HTTP 400 and is intentionally NOT called by the frontend yet.
    """
    return 400, {"error": "Authentication not implemented"}


# --- Current user (single default user — no real auth yet) ------------------------------------
def _current_user() -> User:
    """The app's single user. Created on first access since there's no auth/login."""
    user = User.objects.order_by("id").first()
    if user is None:
        user = User.objects.create()
    return user


@api.get("/user", response=UserOut, summary="Get the current user")
def get_current_user(request):
    return _current_user()


@api.patch("/user", response=UserOut, summary="Update the current user")
def update_current_user(request, payload: UserUpdateIn):
    user = _current_user()
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and data["name"]:
        user.name = data["name"]
    if "theme" in data and data["theme"] in VALID_THEMES:
        user.theme = data["theme"]
    user.save()
    return user


# --- Characters -------------------------------------------------------------------------------
def _related_for(character: Character) -> list[dict]:
    """Directed relationships: this character's *outgoing* edges (from → to)."""
    rels = (
        CharacterRelationship.objects.filter(from_character=character)
        .select_related("to_character")
        .order_by("to_character__name")
    )
    return [
        {
            "relationship_id": rel.id,
            "id": rel.to_character_id,
            "name": rel.to_character.name,
            "relationship": rel.relationship,
        }
        for rel in rels
    ]


def _portrait_key_prefix(character: Character) -> str:
    """S3 folder for a character's portraits: Characters/Project-<pid>/character-<cid>.

    Multiple images can live in this folder (each upload gets a unique filename).
    """
    project = f"Project-{character.project_id}" if character.project_id else "Project-none"
    return f"Characters/{project}/character-{character.id}"


def _character_detail(character: Character) -> dict:
    return {
        "id": character.id,
        "name": character.name,
        "description": character.description,
        "image_url": storage.view_url(character.image_key),
        "image_key": character.image_key,
        "project_id": character.project_id,
        "related": _related_for(character),
        "traits": character.traits or {},
    }


@api.get("/characters", response=list[CharacterOut], summary="List characters")
def list_characters(request, project_id: int | None = None):
    """All characters, or just one project's characters when `project_id` is given."""
    qs = Character.objects.all()
    if project_id is not None:
        qs = qs.filter(project_id=project_id)
    return list(qs)


@api.post("/characters", response={201: CharacterOut}, summary="Create a character")
def create_character(request, payload: CharacterCreateIn):
    character = Character.objects.create(
        name=payload.name, description=payload.description, project_id=payload.project_id
    )
    return 201, character


@api.get("/characters/{int:character_id}", response=CharacterDetailOut, summary="Get a character")
def get_character(request, character_id: int):
    return _character_detail(get_object_or_404(Character, id=character_id))


@api.patch("/characters/{int:character_id}", response=CharacterDetailOut, summary="Update a character")
def update_character(request, character_id: int, payload: CharacterUpdateIn):
    character = get_object_or_404(Character, id=character_id)
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and data["name"]:
        character.name = data["name"]
    if "description" in data and data["description"] is not None:
        character.description = data["description"]
    if "traits" in data and data["traits"] is not None:
        character.traits = data["traits"]
    character.save()
    return _character_detail(character)


@api.post(
    "/characters/{int:character_id}/relationships",
    response={201: CharacterDetailOut, 400: Error, 404: Error},
    summary="Add or update a relationship",
)
def add_relationship(request, character_id: int, payload: RelationshipCreateIn):
    """Directed: creates an edge from this character to `other_id`. Shows only on this
    character's page. If the same directed edge already exists, its label is updated."""
    character = get_object_or_404(Character, id=character_id)
    if payload.other_id == character_id:
        return 400, {"error": "A character cannot relate to itself"}
    other = Character.objects.filter(id=payload.other_id).first()
    if other is None:
        return 404, {"error": "Other character not found"}
    if other.project_id != character.project_id:
        return 400, {"error": "Characters must be in the same project"}

    CharacterRelationship.objects.update_or_create(
        from_character=character,
        to_character=other,
        defaults={"relationship": payload.relationship},
    )
    return 201, _character_detail(character)


@api.delete(
    "/characters/{int:character_id}/relationships/{int:relationship_id}",
    response={204: None},
    summary="Remove a relationship",
)
def delete_relationship(request, character_id: int, relationship_id: int):
    get_object_or_404(CharacterRelationship, id=relationship_id).delete()
    return 204, None


@api.post(
    "/characters/{int:character_id}/image",
    response={200: CharacterDetailOut, 400: Error, 503: Error},
    summary="Upload a character portrait",
)
def upload_character_image(request, character_id: int, file: UploadedFile = File(...)):
    """Upload an image file for the character; stores it in S3 and saves the public URL."""
    character = get_object_or_404(Character, id=character_id)
    content_type = file.content_type or ""
    if not content_type.startswith("image/"):
        return 400, {"error": "File must be an image."}
    try:
        _url, key = storage.upload_image(
            file.read(), content_type, key_prefix=_portrait_key_prefix(character)
        )
    except storage.StorageNotConfigured as exc:
        return 503, {"error": str(exc)}
    except storage.StorageError as exc:
        return 400, {"error": f"Upload failed: {exc}"}
    character.image_key = key
    character.save(update_fields=["image_key", "updated_at"])
    return 200, _character_detail(character)


@api.post(
    "/characters/{int:character_id}/generate-image",
    response={200: CharacterDetailOut, 400: Error, 503: Error},
    summary="Generate a character portrait with AI",
)
def generate_character_image(request, character_id: int, payload: GenerateImageIn):
    """Generate a portrait with FLUX (fal.ai), upload it to S3, and save the key on the character."""
    character = get_object_or_404(Character, id=character_id)
    prompt = (payload.prompt or "").strip() or imagegen.default_prompt(
        character.name, character.description
    )
    try:
        data, content_type = imagegen.generate_image(prompt)
        _url, key = storage.upload_image(
            data, content_type, key_prefix=_portrait_key_prefix(character)
        )
    except (imagegen.GenerationNotConfigured, storage.StorageNotConfigured) as exc:
        return 503, {"error": str(exc)}
    except (imagegen.GenerationError, storage.StorageError) as exc:
        return 400, {"error": str(exc)}
    character.image_key = key
    character.save(update_fields=["image_key", "updated_at"])
    return 200, _character_detail(character)


# --- Entity types (level palette: enemies, hazards, pickups, props) ---------------------------

VALID_ENTITY_CATEGORIES = {choice for choice, _ in EntityType.CATEGORY_CHOICES}


def _entity_key_prefix(entity: EntityType) -> str:
    """S3 folder for an entity's images: Entities/Project-<pid>/entity-<eid> (mirrors portraits)."""
    return f"Entities/Project-{entity.project_id}/entity-{entity.id}"


def _validate_entity_fields(
    project_id: int, glyph: str | None, category: str | None, *, exclude_pk: int | None = None
) -> str | None:
    if glyph is not None:
        if len(glyph) != 1 or glyph.isspace():
            return "glyph must be a single non-space character"
        if glyph in blueprint.BUILTIN_TILES:
            return f"glyph '{glyph}' is reserved (built-in tile)"
        qs = EntityType.objects.filter(project_id=project_id, glyph=glyph)
        if exclude_pk is not None:
            qs = qs.exclude(pk=exclude_pk)
        if qs.exists():
            return f"glyph '{glyph}' is already used in this project"
    if category is not None and category not in VALID_ENTITY_CATEGORIES:
        return f"category must be one of: {', '.join(sorted(VALID_ENTITY_CATEGORIES))}"
    return None


@api.get("/entities", response=list[EntityTypeOut], summary="List entity types")
def list_entity_types(request, project_id: int | None = None):
    qs = EntityType.objects.all()
    if project_id is not None:
        qs = qs.filter(project_id=project_id)
    return list(qs)


@api.post("/entities", response={201: EntityTypeOut, 400: Error}, summary="Create an entity type")
def create_entity_type(request, payload: EntityTypeCreateIn):
    get_object_or_404(Project, id=payload.project_id)
    error = _validate_entity_fields(payload.project_id, payload.glyph, payload.category)
    if error:
        return 400, {"error": error}
    entity = EntityType.objects.create(
        project_id=payload.project_id,
        name=payload.name,
        glyph=payload.glyph,
        category=payload.category,
        description=payload.description,
        behavior=payload.behavior,
    )
    return 201, entity


@api.patch(
    "/entities/{int:entity_id}",
    response={200: EntityTypeOut, 400: Error},
    summary="Update an entity type",
)
def update_entity_type(request, entity_id: int, payload: EntityTypeUpdateIn):
    entity = get_object_or_404(EntityType, id=entity_id)
    data = payload.model_dump(exclude_unset=True)
    error = _validate_entity_fields(
        entity.project_id, data.get("glyph"), data.get("category"), exclude_pk=entity.pk
    )
    if error:
        return 400, {"error": error}
    for field in ("name", "glyph", "category", "description", "behavior"):
        if field in data and data[field] is not None:
            setattr(entity, field, data[field])
    entity.save()
    return entity


@api.delete("/entities/{int:entity_id}", response={204: None}, summary="Delete an entity type")
def delete_entity_type(request, entity_id: int):
    get_object_or_404(EntityType, id=entity_id).delete()
    return 204, None


@api.post(
    "/entities/{int:entity_id}/image",
    response={200: EntityTypeOut, 400: Error, 503: Error},
    summary="Upload an entity sprite/concept image",
)
def upload_entity_image(request, entity_id: int, file: UploadedFile = File(...)):
    entity = get_object_or_404(EntityType, id=entity_id)
    content_type = file.content_type or ""
    if not content_type.startswith("image/"):
        return 400, {"error": "File must be an image."}
    try:
        _url, key = storage.upload_image(
            file.read(), content_type, key_prefix=_entity_key_prefix(entity)
        )
    except storage.StorageNotConfigured as exc:
        return 503, {"error": str(exc)}
    except storage.StorageError as exc:
        return 400, {"error": f"Upload failed: {exc}"}
    entity.image_key = key
    entity.save(update_fields=["image_key", "updated_at"])
    return 200, entity


@api.post(
    "/entities/{int:entity_id}/generate-image",
    response={200: EntityTypeOut, 400: Error, 503: Error},
    summary="Generate an entity image with AI",
)
def generate_entity_image(request, entity_id: int, payload: GenerateImageIn):
    entity = get_object_or_404(EntityType, id=entity_id)
    prompt = (payload.prompt or "").strip() or imagegen.default_prompt(
        entity.name, f"{entity.category}. {entity.description}"
    )
    try:
        data, content_type = imagegen.generate_image(prompt)
        _url, key = storage.upload_image(data, content_type, key_prefix=_entity_key_prefix(entity))
    except (imagegen.GenerationNotConfigured, storage.StorageNotConfigured) as exc:
        return 503, {"error": str(exc)}
    except (imagegen.GenerationError, storage.StorageError) as exc:
        return 400, {"error": str(exc)}
    entity.image_key = key
    entity.save(update_fields=["image_key", "updated_at"])
    return 200, entity


STARTER_ENTITIES = [
    {
        "name": "Walker",
        "glyph": "e",
        "category": EntityType.CATEGORY_ENEMY,
        "description": "A basic patrolling enemy. Turns around at edges and walls.",
        "behavior": {"pattern": "patrol", "speed": 3, "harmful_on_touch": True, "stompable": True},
    },
    {
        "name": "Spikes",
        "glyph": "^",
        "category": EntityType.CATEGORY_HAZARD,
        "description": "Stationary floor spikes. Hurt on touch; cannot be destroyed.",
        "behavior": {"pattern": "static", "harmful_on_touch": True, "stompable": False},
    },
    {
        "name": "Coin",
        "glyph": "o",
        "category": EntityType.CATEGORY_PICKUP,
        "description": "A collectible coin.",
        "behavior": {"pattern": "static", "harmful_on_touch": False, "stompable": False},
    },
]


@api.post(
    "/projects/{int:project_id}/seed-entities",
    response=list[EntityTypeOut],
    summary="Add the starter platformer palette",
)
def seed_entities(request, project_id: int):
    """Create the starter entity set (walker enemy, spikes, coin) for a project, skipping
    any whose glyph or name is already taken. Returns the project's full palette."""
    project = get_object_or_404(Project, id=project_id)
    for spec in STARTER_ENTITIES:
        taken = EntityType.objects.filter(project=project).filter(
            Q(glyph=spec["glyph"]) | Q(name=spec["name"])
        )
        if not taken.exists():
            EntityType.objects.create(project=project, **spec)
    return list(project.entity_types.all())


# --- Scenes (dialogue sidebars) ---------------------------------------------------------------


# --- Projects (top-level game container) ------------------------------------------------------
@api.get("/projects", response=list[ProjectOut], summary="List projects")
def list_projects(request):
    return list(Project.objects.all())


@api.post("/projects", response={201: ProjectOut}, summary="Create a project")
def create_project(request, payload: ProjectCreateIn):
    if payload.order is not None:
        order = payload.order
    else:
        last = Project.objects.order_by("-order").first()
        order = (last.order + 1) if last else 0
    project = Project.objects.create(name=payload.name, order=order)
    return 201, project


@api.get("/projects/{int:project_id}", response=ProjectOut, summary="Get a project")
def get_project(request, project_id: int):
    return get_object_or_404(Project, id=project_id)


@api.patch("/projects/{int:project_id}", response=ProjectOut, summary="Update a project")
def update_project(request, project_id: int, payload: ProjectUpdateIn):
    """Partial update: rename, Settings (dimension/genre), Systems, or Preview (hud_layout)."""
    project = get_object_or_404(Project, id=project_id)
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and data["name"]:
        project.name = data["name"]
    if "order" in data and data["order"] is not None:
        project.order = data["order"]
    if "dimension" in data and data["dimension"] is not None:
        project.dimension = data["dimension"]
    if "genre" in data and data["genre"] is not None:
        project.genre = data["genre"]
    if "systems" in data and data["systems"] is not None:
        project.systems = data["systems"]
    if "hud_layout" in data and data["hud_layout"] is not None:
        project.hud_layout = data["hud_layout"]
    if "state_schema" in data and data["state_schema"] is not None:
        project.state_schema = data["state_schema"]
    if "character_traits" in data and data["character_traits"] is not None:
        project.character_traits = data["character_traits"]
    project.save()
    return project


@api.get(
    "/projects/{int:project_id}/export",
    response=dict,
    summary="Export the project as a gameblueprint document",
)
def export_project(request, project_id: int):
    """The unified source-of-truth export (`gameblueprint/0.1`): systems + derived feel
    numbers, characters, entity palette, tile legend, and every level's layout grid,
    entity coordinates, transitions, and dialogue graphs. This is the document the MCP
    server and any engine codegen consume — schema contract in docs/blueprint-schema.md."""
    project = get_object_or_404(Project, id=project_id)
    return blueprint.build_blueprint(project)


# --- Abilities (the player's verb set) --------------------------------------------------------
@api.get("/abilities", response=list[AbilityOut], summary="List abilities")
def list_abilities(request, project_id: int | None = None):
    """All abilities, or just one project's when `project_id` is given — the verb set."""
    qs = Ability.objects.all()
    if project_id is not None:
        qs = qs.filter(project_id=project_id)
    return list(qs)


@api.post("/abilities", response={201: AbilityOut}, summary="Create an ability")
def create_ability(request, payload: AbilityCreateIn):
    """Add a verb to the project. `unlock_requirements` uses the same bounded vocabulary as
    dialogue requirements; empty means the player has it from the start."""
    if payload.order is not None:
        order = payload.order
    else:
        last = Ability.objects.filter(project_id=payload.project_id).order_by("-order").first()
        order = (last.order + 1) if last else 0
    ability = Ability.objects.create(
        project_id=payload.project_id,
        name=payload.name,
        description=payload.description,
        params=payload.params or {},
        unlock_requirements=payload.unlock_requirements or [],
        order=order,
    )
    return 201, ability


@api.patch("/abilities/{int:ability_id}", response=AbilityOut, summary="Update an ability")
def update_ability(request, ability_id: int, payload: AbilityUpdateIn):
    """Partial update — `params`/`unlock_requirements` replace the whole value when given."""
    ability = get_object_or_404(Ability, id=ability_id)
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and data["name"]:
        ability.name = data["name"]
    if "description" in data and data["description"] is not None:
        ability.description = data["description"]
    if "params" in data and data["params"] is not None:
        ability.params = data["params"]
    if "unlock_requirements" in data and data["unlock_requirements"] is not None:
        ability.unlock_requirements = data["unlock_requirements"]
    if "order" in data and data["order"] is not None:
        ability.order = data["order"]
    ability.save()
    return ability


@api.delete("/abilities/{int:ability_id}", response={204: None}, summary="Delete an ability")
def delete_ability(request, ability_id: int):
    """Plain delete — nothing references an `Ability` yet (progression rewards will, once
    they exist), so there is nothing to 409 on."""
    get_object_or_404(Ability, id=ability_id).delete()
    return 204, None


@api.get("/levels", response=list[LevelOut], summary="List levels")
def list_levels(request, project_id: int | None = None):
    """All levels, or just one project's levels when `project_id` is given."""
    qs = Level.objects.all()
    if project_id is not None:
        qs = qs.filter(project_id=project_id)
    return list(qs)


@api.post("/levels", response={201: LevelOut}, summary="Create a level")
def create_level(request, payload: LevelCreateIn):
    if payload.order is not None:
        order = payload.order
    else:
        last = Level.objects.order_by("-order").first()
        order = (last.order + 1) if last else 0
    level = Level.objects.create(
        name=payload.name, order=order, project_id=payload.project_id
    )
    return 201, level


@api.get("/levels/{int:level_id}", response=LevelOut, summary="Get a level")
def get_level(request, level_id: int):
    return get_object_or_404(Level, id=level_id)


def _validate_layout(layout: dict, project_id: int | None) -> str | None:
    """Check a Level.layout dict; returns an error message or None. Every row must match
    `width`, and every glyph must be a built-in tile or one of the project's entity glyphs."""
    rows = layout.get("rows")
    width, height = layout.get("width"), layout.get("height")
    if not isinstance(rows, list) or not all(isinstance(r, str) for r in rows):
        return "layout.rows must be a list of strings"
    if not isinstance(width, int) or not isinstance(height, int) or width < 1 or height < 1:
        return "layout.width and layout.height must be positive integers"
    if len(rows) != height or any(len(r) != width for r in rows):
        return "layout.rows must be exactly height rows of exactly width characters"
    known = set(blueprint.BUILTIN_TILES)
    if project_id is not None:
        known |= set(
            EntityType.objects.filter(project_id=project_id).values_list("glyph", flat=True)
        )
    unknown = {ch for row in rows for ch in row} - known
    if unknown:
        return f"Unknown glyphs in layout: {' '.join(sorted(unknown))} — add matching entity types first"
    return None


@api.patch("/levels/{int:level_id}", response={200: LevelOut, 400: Error}, summary="Update a level")
def update_level(request, level_id: int, payload: LevelUpdateIn):
    level = get_object_or_404(Level, id=level_id)
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and data["name"]:
        level.name = data["name"]
    if "order" in data and data["order"] is not None:
        level.order = data["order"]
    if "layout" in data and data["layout"] is not None:
        if data["layout"] != {}:
            error = _validate_layout(data["layout"], level.project_id)
            if error:
                return 400, {"error": error}
        level.layout = data["layout"]
    if "intro_scene_id" in data:
        if data["intro_scene_id"] is None:
            level.intro_scene = None
        else:
            scene = Scene.objects.filter(id=data["intro_scene_id"], level=level).first()
            if scene is None:
                return 400, {"error": "intro_scene_id must be one of this level's scenes"}
            level.intro_scene = scene
    level.save()
    return level


@api.get(
    "/levels/{int:level_id}/characters",
    response=list[LevelCharacterOut],
    summary="Characters in a level (deduced from dialogue)",
)
def level_characters(request, level_id: int):
    """The level's cast, deduced from which characters speak its dialogue, each with the
    lines they speak (across the level's scenes). Ordered by character name."""
    get_object_or_404(Level, id=level_id)
    dialogues = (
        Dialogue.objects.filter(scene__level_id=level_id, character__isnull=False)
        .select_related("character", "scene")
        .order_by("character__name", "scene__order", "id")
    )
    by_char: dict[int, dict] = {}
    for d in dialogues:
        c = d.character
        entry = by_char.get(c.id)
        if entry is None:
            entry = {
                "id": c.id,
                "name": c.name,
                "description": c.description,
                "image_url": storage.view_url(c.image_key),
                "lines": [],
            }
            by_char[c.id] = entry
        entry["lines"].append(
            {
                "id": d.id,
                "text": d.text,
                "scene_id": d.scene_id,
                "scene_name": d.scene.name if d.scene else "",
            }
        )
    return list(by_char.values())


def _scene_out(scene: Scene) -> dict:
    return {
        "id": scene.id,
        "name": scene.name,
        "level_id": scene.level_id,
        "level_name": scene.level.name,
        "location_id": scene.location_id,
    }


@api.get("/scenes", response=list[SceneOut], summary="List scenes")
def list_scenes(request):
    scenes = Scene.objects.select_related("level").all()
    return [_scene_out(s) for s in scenes]


@api.post("/scenes", response={201: SceneOut}, summary="Create a scene")
def create_scene(request, payload: SceneCreateIn):
    """Create a scene in a level (optionally at a location). Order auto-appends within the level."""
    level = get_object_or_404(Level, id=payload.level_id)
    if payload.order is not None:
        order = payload.order
    else:
        last = Scene.objects.filter(level_id=level.id).order_by("-order").first()
        order = (last.order + 1) if last else 0
    scene = Scene.objects.create(
        name=payload.name,
        level=level,
        location_id=payload.location_id,
        order=order,
    )
    scene.level = level  # ensure level_name resolves without a re-query
    return 201, _scene_out(scene)


@api.patch("/scenes/{int:scene_id}", response=SceneOut, summary="Update a scene")
def update_scene(request, scene_id: int, payload: SceneUpdateIn):
    """Partial update: rename, (re)assign to a location, or reorder."""
    scene = get_object_or_404(Scene.objects.select_related("level"), id=scene_id)
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and data["name"]:
        scene.name = data["name"]
    if "location_id" in data:
        scene.location_id = data["location_id"]
    if "order" in data and data["order"] is not None:
        scene.order = data["order"]
    scene.save()
    return _scene_out(scene)


# --- Locations (places within a level) --------------------------------------------------------
LOCATION_KINDS = {choice for choice, _ in Location.KIND_CHOICES} | {""}
LOCATION_SCALES = {choice for choice, _ in Location.SCALE_CHOICES} | {""}


def _location(location_id: int) -> Location:
    """Fetch a location with its characters and connections prefetched."""
    return get_object_or_404(
        Location.objects.prefetch_related(
            "characters", "connections_out__to_location", "connections_in__from_location"
        ),
        id=location_id,
    )


def _connection_out(conn: LocationConnection, *, from_here: bool) -> dict:
    """Serialize a connection relative to the location whose row it appears on."""
    other = conn.to_location if from_here else conn.from_location
    return {
        "id": conn.id,
        "from_location_id": conn.from_location_id,
        "to_location_id": conn.to_location_id,
        "other_id": other.id,
        "other_name": other.name,
        "direction": "out" if from_here else "in",
        "label": conn.label,
        "bidirectional": conn.bidirectional,
        "requirements": conn.requirements or [],
    }


def _connections_for(location: Location) -> list[dict]:
    """Every exit walkable from this location: the ones authored here, plus the
    bidirectional ones authored from the other end (a one-way edge shows only on its
    source)."""
    out = [_connection_out(c, from_here=True) for c in location.connections_out.all()]
    out += [
        _connection_out(c, from_here=False)
        for c in location.connections_in.all()
        if c.bidirectional
    ]
    return out


def _location_out(location: Location) -> dict:
    return {
        "id": location.id,
        "name": location.name,
        "description": location.description,
        "order": location.order,
        "level_id": location.level_id,
        "kind": location.kind,
        "scale": location.scale,
        "mood": location.mood,
        "props": location.props or [],
        "image_url": storage.view_url(location.image_key),
        "image_key": location.image_key,
        "characters": list(location.characters.all()),
        "connections": _connections_for(location),
    }


def _location_detail(location_id: int) -> dict:
    return _location_out(_location(location_id))


def _art_key_prefix(location: Location) -> str:
    """S3 folder for a location's reference images: Locations/Project-<pid>/location-<lid>.

    Multiple images can live in this folder (each upload gets a unique filename).
    """
    project_id = location.level.project_id if location.level_id else None
    project = f"Project-{project_id}" if project_id else "Project-none"
    return f"Locations/{project}/location-{location.id}"


@api.get("/locations", response=list[LocationOut], summary="List locations")
def list_locations(request, level_id: int | None = None):
    """All locations, or just one level's locations when `level_id` is given. Each row
    carries its detail fields, cast, and connections (its exits)."""
    qs = Location.objects.prefetch_related(
        "characters", "connections_out__to_location", "connections_in__from_location"
    )
    if level_id is not None:
        qs = qs.filter(level_id=level_id)
    return [_location_out(loc) for loc in qs]


@api.post("/locations", response={201: LocationOut, 400: Error}, summary="Create a location")
def create_location(request, payload: LocationCreateIn):
    kind = payload.kind or ""
    scale = payload.scale or ""
    if kind not in LOCATION_KINDS:
        return 400, {"error": f"kind must be one of {sorted(LOCATION_KINDS - {''})} or blank"}
    if scale not in LOCATION_SCALES:
        return 400, {"error": f"scale must be one of {sorted(LOCATION_SCALES - {''})} or blank"}
    if payload.order is not None:
        order = payload.order
    else:
        last = Location.objects.filter(level_id=payload.level_id).order_by("-order").first()
        order = (last.order + 1) if last else 0
    location = Location.objects.create(
        name=payload.name,
        description=payload.description,
        order=order,
        level_id=payload.level_id,
        kind=kind,
        scale=scale,
        mood=payload.mood or "",
        props=payload.props or [],
    )
    return 201, _location_detail(location.id)


@api.get("/locations/{int:location_id}", response=LocationOut, summary="Get a location")
def get_location(request, location_id: int):
    return _location_detail(location_id)


@api.patch(
    "/locations/{int:location_id}",
    response={200: LocationOut, 400: Error},
    summary="Update a location",
)
def update_location(request, location_id: int, payload: LocationUpdateIn):
    """Partial update: name/description/order plus the detail fields (kind, scale, mood, props)."""
    location = get_object_or_404(Location, id=location_id)
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and data["name"]:
        location.name = data["name"]
    if "description" in data and data["description"] is not None:
        location.description = data["description"]
    if "order" in data and data["order"] is not None:
        location.order = data["order"]
    if "kind" in data and data["kind"] is not None:
        if data["kind"] not in LOCATION_KINDS:
            return 400, {"error": f"kind must be one of {sorted(LOCATION_KINDS - {''})} or blank"}
        location.kind = data["kind"]
    if "scale" in data and data["scale"] is not None:
        if data["scale"] not in LOCATION_SCALES:
            return 400, {"error": f"scale must be one of {sorted(LOCATION_SCALES - {''})} or blank"}
        location.scale = data["scale"]
    if "mood" in data and data["mood"] is not None:
        location.mood = data["mood"]
    if "props" in data and data["props"] is not None:
        location.props = data["props"]
    location.save()
    return 200, _location_detail(location.id)


@api.delete("/locations/{int:location_id}", response={204: None}, summary="Delete a location")
def delete_location(request, location_id: int):
    get_object_or_404(Location, id=location_id).delete()
    return 204, None


@api.post(
    "/locations/{int:location_id}/characters",
    response={200: LocationOut, 400: Error, 404: Error},
    summary="Place a character at a location",
)
def add_location_character(request, location_id: int, payload: LocationCharacterIn):
    location = get_object_or_404(Location.objects.select_related("level"), id=location_id)
    character = Character.objects.filter(id=payload.character_id).first()
    if character is None:
        return 404, {"error": "Character not found"}
    if character.project_id != location.level.project_id:
        return 400, {"error": "Character must be in the same project as the level"}
    location.characters.add(character)
    return 200, _location_detail(location.id)


@api.delete(
    "/locations/{int:location_id}/characters/{int:character_id}",
    response={200: LocationOut},
    summary="Remove a character from a location",
)
def remove_location_character(request, location_id: int, character_id: int):
    location = get_object_or_404(Location, id=location_id)
    location.characters.remove(character_id)
    return 200, _location_detail(location.id)


@api.post(
    "/locations/{int:location_id}/connections",
    response={201: LocationOut, 400: Error, 404: Error},
    summary="Connect a location to another",
)
def add_location_connection(request, location_id: int, payload: LocationConnectionIn):
    """Add a labeled way from this location to another one *in the same level* — the
    world graph's edge. `bidirectional` (default) means it's walkable both ways, so it
    also shows on the far location. `requirements` locks the passage using the same
    vocabulary as dialogue requirements (e.g. `has_item` + `item_cellar_key`).
    Re-connecting the same ordered pair updates that connection instead of duplicating it.
    """
    location = get_object_or_404(Location, id=location_id)
    if payload.to_id == location_id:
        return 400, {"error": "A location cannot connect to itself"}
    other = Location.objects.filter(id=payload.to_id).first()
    if other is None:
        return 404, {"error": "Target location not found"}
    if other.level_id != location.level_id:
        return 400, {"error": "Locations must be in the same level"}

    LocationConnection.objects.update_or_create(
        from_location=location,
        to_location=other,
        defaults={
            "label": payload.label,
            "bidirectional": payload.bidirectional,
            "requirements": payload.requirements or [],
        },
    )
    return 201, _location_detail(location.id)


@api.delete(
    "/locations/{int:location_id}/connections/{int:connection_id}",
    response={200: LocationOut, 400: Error},
    summary="Remove a connection",
)
def delete_location_connection(request, location_id: int, connection_id: int):
    """Delete a connection from either end — the id comes from the location row's
    `connections`, which includes bidirectional edges authored from the other side."""
    location = get_object_or_404(Location, id=location_id)
    conn = get_object_or_404(LocationConnection, id=connection_id)
    if location_id not in (conn.from_location_id, conn.to_location_id):
        return 400, {"error": "That connection does not touch this location"}
    conn.delete()
    return 200, _location_detail(location.id)


@api.post(
    "/locations/{int:location_id}/image",
    response={200: LocationOut, 400: Error, 503: Error},
    summary="Upload a location reference image",
)
def upload_location_image(request, location_id: int, file: UploadedFile = File(...)):
    """Upload a reference image for the location; stores it in S3 and saves the key."""
    location = get_object_or_404(Location.objects.select_related("level"), id=location_id)
    content_type = file.content_type or ""
    if not content_type.startswith("image/"):
        return 400, {"error": "File must be an image."}
    try:
        _url, key = storage.upload_image(
            file.read(), content_type, key_prefix=_art_key_prefix(location)
        )
    except storage.StorageNotConfigured as exc:
        return 503, {"error": str(exc)}
    except storage.StorageError as exc:
        return 400, {"error": f"Upload failed: {exc}"}
    location.image_key = key
    location.save(update_fields=["image_key", "updated_at"])
    return 200, _location_detail(location.id)


@api.post(
    "/locations/{int:location_id}/generate-image",
    response={200: LocationOut, 400: Error, 503: Error},
    summary="Generate a location reference image with AI",
)
def generate_location_image(request, location_id: int, payload: GenerateImageIn):
    """Generate reference art with FLUX (fal.ai), upload it to S3, and save the key.

    Omit `prompt` to build one from the location's name, description, and mood/kind/scale.
    """
    location = get_object_or_404(Location.objects.select_related("level"), id=location_id)
    prompt = (payload.prompt or "").strip() or imagegen.default_location_prompt(
        location.name,
        location.description,
        mood=location.mood,
        kind=location.kind,
        scale=location.scale,
    )
    try:
        data, content_type = imagegen.generate_image(prompt)
        _url, key = storage.upload_image(
            data, content_type, key_prefix=_art_key_prefix(location)
        )
    except (imagegen.GenerationNotConfigured, storage.StorageNotConfigured) as exc:
        return 503, {"error": str(exc)}
    except (imagegen.GenerationError, storage.StorageError) as exc:
        return 400, {"error": str(exc)}
    location.image_key = key
    location.save(update_fields=["image_key", "updated_at"])
    return 200, _location_detail(location.id)


@api.get(
    "/scenes/{int:scene_id}/dialogues",
    response=list[DialogueNodeOut],
    summary="All dialogue nodes in a scene (flat, for the tree view)",
)
def scene_dialogue_tree(request, scene_id: int):
    """Every dialogue node in a scene as a flat list — the frontend builds the graph from
    `id`/`parent_ids`. One JOIN (no N+1); each node's character serializes like everywhere else
    (presigned image URL via CharacterOut)."""
    get_object_or_404(Scene, id=scene_id)
    nodes = Dialogue.objects.filter(scene_id=scene_id).select_related("character").prefetch_related(
        "incoming_edges"
    )
    return [
        {
            "id": n.id,
            "title": n.title,
            "parent_ids": [e.from_node_id for e in n.incoming_edges.all()],
            "text": n.text,
            "character": n.character,
            "requirements": n.requirements,
            "effects": n.effects,
        }
        for n in nodes
    ]


# --- Dialogues (branching graph) ---------------------------------------------------------------
def _summary_dict(d: Dialogue, option_label: str = "") -> dict:
    return {
        "id": d.id,
        "title": d.title,
        "text": d.text,
        "option_label": option_label,
        "character": d.character,
        "requirements": d.requirements,
        "effects": d.effects,
    }


@api.get("/dialogues", response=list[DialogueSummaryOut], summary="List root dialogues")
def list_root_dialogues(request, scene_id: int | None = None):
    """Root dialogues (no incoming edges). Pass `scene_id` to get the roots for one scene."""
    qs = Dialogue.objects.filter(incoming_edges__isnull=True).select_related("character")
    if scene_id is not None:
        qs = qs.filter(scene_id=scene_id)
    return [_summary_dict(d) for d in qs]


def _dialogue_detail(dialogue_id: int) -> dict:
    """Fetch a dialogue and build the dict DialogueDetailOut serializes."""
    dialogue = get_object_or_404(
        Dialogue.objects.select_related("character").prefetch_related(
            "outgoing_edges__to_node__character", "incoming_edges__from_node"
        ),
        id=dialogue_id,
    )
    responses = [
        _summary_dict(edge.to_node, edge.option_label) for edge in dialogue.outgoing_edges.all()
    ]
    parents = [
        {"id": edge.from_node.id, "title": edge.from_node.title, "text": edge.from_node.text}
        for edge in dialogue.incoming_edges.all()
    ]
    return {
        "id": dialogue.id,
        "title": dialogue.title,
        "text": dialogue.text,
        "scene_id": dialogue.scene_id,
        "parents": parents,
        "character": dialogue.character,
        "requirements": dialogue.requirements,
        "effects": dialogue.effects,
        "responses": responses,
    }


@api.get("/dialogues/{int:dialogue_id}", response=DialogueDetailOut, summary="Get a dialogue")
def get_dialogue(request, dialogue_id: int):
    """A dialogue with its character, immediate responses, and linking parent(s)."""
    return _dialogue_detail(dialogue_id)


@api.post("/dialogues", response={201: DialogueDetailOut}, summary="Create a dialogue")
def create_dialogue(request, payload: DialogueIn):
    """Create a dialogue node. Pass `parent_id` to attach it as a response of another node."""
    scene = get_object_or_404(Scene, id=payload.scene_id) if payload.scene_id else None
    parent = get_object_or_404(Dialogue, id=payload.parent_id) if payload.parent_id else None
    dialogue = Dialogue.create_node(
        scene=scene,
        parent=parent,
        character_id=payload.character_id,
        text=payload.text,
        requirements=payload.requirements,
        effects=payload.effects,
    )
    return 201, _dialogue_detail(dialogue.id)


@api.patch("/dialogues/{int:dialogue_id}", response=DialogueDetailOut, summary="Update a dialogue")
def update_dialogue(request, dialogue_id: int, payload: DialogueUpdateIn):
    """Partial update: only the fields present in the request body are changed."""
    dialogue = get_object_or_404(Dialogue, id=dialogue_id)
    data = payload.model_dump(exclude_unset=True)
    if "text" in data:
        dialogue.text = data["text"] or ""
    if "character_id" in data:
        dialogue.character_id = data["character_id"]
    if "requirements" in data and data["requirements"] is not None:
        dialogue.requirements = data["requirements"]
    if "effects" in data and data["effects"] is not None:
        dialogue.effects = data["effects"]
    dialogue.save()
    dialogue.sync_title_from_effects()
    return _dialogue_detail(dialogue.id)


@api.post(
    "/dialogues/{int:dialogue_id}/link",
    response={201: DialogueDetailOut, 400: Error},
    summary="Link an existing node as a response (reuse/reconverge)",
)
def link_dialogue(request, dialogue_id: int, payload: DialogueLinkIn):
    """Attach an existing node (`target_id`) as an additional response of `dialogue_id`,
    without creating a new node — how two branches converge back onto the same node."""
    if payload.target_id == dialogue_id:
        return 400, {"error": "A node cannot link to itself"}
    from_node = get_object_or_404(Dialogue, id=dialogue_id)
    to_node = get_object_or_404(Dialogue, id=payload.target_id)
    edge, created = DialogueEdge.objects.get_or_create(
        from_node=from_node,
        to_node=to_node,
        defaults={"order": from_node.outgoing_edges.count(), "option_label": payload.option_label},
    )
    if not created and payload.option_label and edge.option_label != payload.option_label:
        edge.option_label = payload.option_label
        edge.save(update_fields=["option_label"])
    return 201, _dialogue_detail(from_node.id)


@api.post(
    "/scenes/{int:scene_id}/import-yarn",
    response={201: YarnImportOut, 400: Error},
    summary="Import a Yarn script into a scene as dialogue nodes",
)
def import_yarn_view(request, scene_id: int, payload: YarnImportIn):
    """Parse a bounded subset of Yarn (see `services/yarn_import.py`) and materialize it as
    dialogue nodes/edges in this scene. Pass `parent_id` to attach the pasted content as a new
    response of that existing node instead of a freestanding root — continuing a branch that's
    already there. All-or-nothing: a bad jump target aborts the whole import rather than
    leaving orphaned nodes."""
    scene = get_object_or_404(Scene, id=scene_id)
    if payload.parent_id is not None:
        get_object_or_404(Dialogue, id=payload.parent_id)
    try:
        result = yarn_import.import_yarn(scene, payload.text, parent_id=payload.parent_id)
    except yarn_import.YarnImportError as exc:
        return 400, {"error": str(exc)}
    return 201, result


@api.get(
    "/scenes/{int:scene_id}/export-yarn",
    response=YarnExportOut,
    summary="Export a scene's dialogue graph as a Yarn script",
)
def export_yarn_view(request, scene_id: int):
    scene = get_object_or_404(Scene, id=scene_id)
    text = yarn_export.export_scene_to_yarn(scene)
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", scene.name or "").strip("-").lower() or f"scene-{scene.id}"
    return {"filename": f"{slug}.yarn", "text": text}
