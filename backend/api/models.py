import re

from django.db import models


class User(models.Model):
    """A user of the editor. No real auth yet — the app uses a single default user,
    which is where per-user settings (like the UI theme) are persisted."""

    THEME_NEON = "neon"
    THEME_AQUA = "aqua"
    THEME_LIGHT = "light"
    THEME_STUDIO = "studio"
    THEME_CHOICES = [
        (THEME_NEON, "Neon"),
        (THEME_AQUA, "Aqua"),
        (THEME_LIGHT, "Light"),
        (THEME_STUDIO, "Studio"),
    ]

    name = models.CharField(max_length=50, default="Player")
    theme = models.CharField(max_length=20, choices=THEME_CHOICES, default=THEME_NEON)

    def __str__(self) -> str:
        return self.name


class Project(models.Model):
    """A game project — the top-level container above Levels.

    Holds game-wide configuration captured by the Settings/Systems/Preview tabs:
    `dimension` and `genre` are first-class columns (stable, queryable), while the
    evolving per-system answers (`systems`) and HUD layout (`hud_layout`) live in JSONB
    because their shape is defined by frontend code and changes often.
    """

    name = models.CharField(max_length=100, default="New Project")
    order = models.PositiveIntegerField(default=0)
    dimension = models.CharField(max_length=2, blank=True, default="")  # "2d" | "3d" | ""
    genre = models.CharField(max_length=30, blank=True, default="")
    systems = models.JSONField(default=dict, blank=True)  # ArchitectState: per-system enabled+answers
    hud_layout = models.JSONField(default=dict, blank=True)  # HudLayout: {systemId: {x, y}}
    state_schema = models.JSONField(default=dict, blank=True)
    # The project's default character traits — a list of trait *definitions* that every character
    # in the project shows: [{key, label, type: number|text|toggle, min, max, step, unit, default}].
    # Unlike `systems` (answers only, definitions in code), the full definition is stored because
    # traits can be custom, so no code catalog can describe them.
    character_traits = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self) -> str:
        return self.name


class Ability(models.Model):
    """A verb in the player's vocabulary — what the player can actually *do*.

    Project-scoped data, not a questionnaire answer: the Systems architect tunes numbers
    (jump height, run speed) but never captures the identity-defining decision of which
    actions exist at all. `description` is plain-language behavior intent ("short burst,
    brief invulnerability") rather than implementation; `params` is a free-form
    `{key: number|string|bool}` bag of the knobs that matter for *this* verb (cooldown,
    distance, uses) — stored verbatim, validated in the frontend like `systems`/`traits`.

    `unlock_requirements` gates when the player gets it, using the *same* bounded
    vocabulary as `Dialogue.requirements` / `LocationConnection.requirements`
    (`has_item` / `stat_check` / `state_equals` / `remembered_choice`) — "unlocks when
    `flag_met_mentor`". An empty list means the ability is available from the start.
    """

    project = models.ForeignKey(
        Project, null=True, blank=True, on_delete=models.CASCADE, related_name="abilities"
    )
    name = models.CharField(max_length=100, default="New Ability")
    description = models.TextField(blank=True, default="")
    # {key: number|string|bool} — cooldown, distance, uses. Stored verbatim.
    params = models.JSONField(default=dict, blank=True)
    # Same bounded vocabulary as Dialogue.requirements; [] = available from the start.
    unlock_requirements = models.JSONField(default=list, blank=True)
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self) -> str:
        return self.name


class Level(models.Model):
    """A level in the game. Belongs to a project; contains an ordered set of scenes.

    `layout` is the level's 2D tile map as JSON: `{"width": W, "height": H, "rows": [str]}`,
    where each row is a string of W glyph characters. Built-in glyphs (see api.BUILTIN_TILES):
    "." empty, "#" solid ground, "=" one-way platform, "P" player start, "G" goal. Any other
    glyph must match an EntityType.glyph in the same project. Stored as ASCII rows on purpose —
    it's the most legible form for both humans and AI agents, and the export derives a
    coordinate list from it. `{}` = no layout drawn yet.

    `intro_scene` optionally points at one of this level's dialogue scenes to play when the
    level starts. Level completion advances to the next level by `order` within the project.
    """

    project = models.ForeignKey(
        Project, null=True, blank=True, on_delete=models.CASCADE, related_name="levels"
    )
    name = models.CharField(max_length=100)
    order = models.PositiveIntegerField(default=0)
    layout = models.JSONField(default=dict, blank=True)
    intro_scene = models.ForeignKey(
        "Scene", null=True, blank=True, on_delete=models.SET_NULL, related_name="intro_for_levels"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self) -> str:
        return self.name


class EntityType(models.Model):
    """A placeable thing in a level that isn't a speaking character: enemies, hazards,
    pickups, props. Per-project, like Characters.

    `glyph` is the single character that represents this entity in Level.layout rows —
    unique per project, and must not collide with the built-in tile glyphs. `behavior` is a
    deliberately bounded typed dict (mirroring the requirements/effects philosophy):
    `{"pattern": "static"|"walk"|"patrol"|"fly", "speed": number (units/sec),
      "harmful_on_touch": bool, "stompable": bool}` — enough for an agent to implement a
    Mario-style entity without freeform prose being the only spec. `image_key` is an S3
    object key for the sprite/concept image (same pipeline as Character portraits).
    """

    CATEGORY_ENEMY = "enemy"
    CATEGORY_HAZARD = "hazard"
    CATEGORY_PICKUP = "pickup"
    CATEGORY_PROP = "prop"
    CATEGORY_CHOICES = [
        (CATEGORY_ENEMY, "Enemy"),
        (CATEGORY_HAZARD, "Hazard"),
        (CATEGORY_PICKUP, "Pickup"),
        (CATEGORY_PROP, "Prop"),
    ]

    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="entity_types"
    )
    name = models.CharField(max_length=50)
    glyph = models.CharField(max_length=1)
    category = models.CharField(max_length=10, choices=CATEGORY_CHOICES, default=CATEGORY_ENEMY)
    description = models.TextField(blank=True, default="")
    behavior = models.JSONField(default=dict, blank=True)
    image_key = models.CharField(max_length=500, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "id"]
        constraints = [
            models.UniqueConstraint(fields=["project", "glyph"], name="uniq_entity_glyph"),
            models.UniqueConstraint(fields=["project", "name"], name="uniq_entity_name"),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.glyph})"


class Character(models.Model):
    """A character in a project. Can appear in scenes, speak dialogue, and relate to others."""

    project = models.ForeignKey(
        "Project", null=True, blank=True, on_delete=models.CASCADE, related_name="characters"
    )
    name = models.CharField(max_length=30)
    description = models.TextField(blank=True, default="")
    # The portrait's S3 object key (path within the bucket), e.g.
    # "Characters/Project-1/character-2/<uuid>.png". Blank = none yet. The browser-facing URL is
    # derived from this at read time (a presigned GET URL) — see storage.view_url().
    image_key = models.CharField(max_length=500, blank=True, default="")
    # This character's traits: {"values": {key: value}, "own": [trait definition, ...]}.
    # `values` covers both the project's default traits (an override) and this character's own
    # ones; `own` holds definitions for traits only this character has. The project's defaults are
    # overlaid live at read time, so removing one there removes it everywhere.
    traits = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "id"]

    def __str__(self) -> str:
        return self.name


class CharacterRelationship(models.Model):
    """A directed, labeled relationship from one character to another (e.g. "mentor of").

    Unidirectional: it belongs to `from_character` and shows only on that character's page;
    the reverse (`to_character` → `from_character`) is a separate edge if wanted. One edge per
    ordered pair (`from_character`, `to_character`); a character's relationships are its
    `relationships_out`.
    """

    from_character = models.ForeignKey(
        Character, on_delete=models.CASCADE, related_name="relationships_out"
    )
    to_character = models.ForeignKey(
        Character, on_delete=models.CASCADE, related_name="relationships_in"
    )
    relationship = models.CharField(max_length=100, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["from_character", "to_character"], name="uniq_char_relationship"
            )
        ]

    def __str__(self) -> str:
        return f"{self.from_character.name} → {self.to_character.name}: {self.relationship}"


class Location(models.Model):
    """A place within a level. Characters can be present here; scenes can take place here.

    Belongs to a level (like a scene). Its `characters` M2M is the manually-assigned cast
    "present at" this location; a location's scenes are its `scenes` (Scene.location).

    Beyond the narrative grouping, a location carries the detail an agent would otherwise
    invent — `kind`/`scale`/`mood`/`props` (what the place *is*, how big it feels, how it
    reads, and what's in it) and a reference image (`image_key`, same S3 pipeline as
    character portraits). `LocationConnection`s turn the flat list into a world graph.
    """

    KIND_CHOICES = [("interior", "Interior"), ("exterior", "Exterior")]
    SCALE_CHOICES = [
        ("cramped", "Cramped"),
        ("room", "Room"),
        ("open", "Open"),
        ("vast", "Vast"),
    ]

    level = models.ForeignKey(Level, on_delete=models.CASCADE, related_name="locations")
    name = models.CharField(max_length=100, default="New Location")
    description = models.TextField(blank=True, default="")
    order = models.PositiveIntegerField(default=0)
    # "interior" | "exterior" | "" (unset)
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, blank=True, default="")
    # "cramped" | "room" | "open" | "vast" | "" (unset)
    scale = models.CharField(max_length=20, choices=SCALE_CHOICES, blank=True, default="")
    # Free text: "smoky, candle-lit, too quiet".
    mood = models.CharField(max_length=200, blank=True, default="")
    # A plain list of strings — the things in the room ("bar counter", "trapdoor behind the
    # barrels"). Where the creator's mental image lives; stored verbatim, no validation.
    props = models.JSONField(default=list, blank=True)
    # The reference image's S3 object key, e.g. "Locations/Project-1/location-2/<uuid>.png".
    # Browser-facing URLs are presigned from this at read time — see storage.view_url().
    image_key = models.CharField(max_length=500, blank=True, default="")
    # Characters present at this location (manually assigned, editable on the Locations page).
    characters = models.ManyToManyField(Character, related_name="locations", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self) -> str:
        return f"{self.level.name} / {self.name}"


class LocationConnection(models.Model):
    """A labeled way from one location to another — the room-and-exit graph.

    Structurally the same idea as `DialogueEdge`: a directed edge with a label, one per
    ordered pair. `bidirectional` (the default) means the exit works both ways, so the
    connection also shows on `to_location`'s card. `requirements` gates the passage using
    the *same* bounded vocabulary as `Dialogue.requirements` (`has_item` / `stat_check` /
    `state_equals` / `remembered_choice`) — "locked until `item_cellar_key`" — so a
    lock-and-key world reads the same way a gated dialogue choice does.
    """

    from_location = models.ForeignKey(
        Location, on_delete=models.CASCADE, related_name="connections_out"
    )
    to_location = models.ForeignKey(
        Location, on_delete=models.CASCADE, related_name="connections_in"
    )
    label = models.CharField(max_length=100, blank=True, default="")
    bidirectional = models.BooleanField(default=True)
    requirements = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["from_location", "to_location"], name="uniq_location_connection"
            )
        ]

    def __str__(self) -> str:
        arrow = "<->" if self.bidirectional else "->"
        return f"{self.from_location.name} {arrow} {self.to_location.name}: {self.label}"


class Scene(models.Model):
    """A scene within a level. Contains the characters present in it."""

    level = models.ForeignKey(Level, on_delete=models.CASCADE, related_name="scenes")
    # The location this scene takes place at (optional). SET_NULL so deleting a location
    # doesn't delete its scenes; nullable so scenes created from the Dialogue editor need none.
    location = models.ForeignKey(
        "Location", null=True, blank=True, on_delete=models.SET_NULL, related_name="scenes"
    )
    name = models.CharField(max_length=100)
    order = models.PositiveIntegerField(default=0)
    # A character can appear in many scenes, so this is many-to-many.
    characters = models.ManyToManyField(Character, related_name="scenes", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self) -> str:
        return f"{self.level.name} / {self.name}"


class Dialogue(models.Model):
    """A node in a branching dialogue *graph* (a Yarn-style node).

    Nodes are linked by `DialogueEdge` rather than a single `parent` FK, so a node can be
    reached from multiple points (reuse/reconvergence) or even form a loop — both ordinary
    Yarn features. A node with no `incoming_edges` is a scene root. `title` is a stable,
    project-wide-unique, Yarn-friendly identifier: auto-generated from the parent's title (or
    the scene, for a root) + a running number, unless the node carries a `remember_choice`
    effect, in which case the title tracks that effect's `state_key` instead (see
    `sync_title_from_effects`). Edges reference nodes by FK, so renaming/regenerating a title
    never breaks a jump.
    """

    scene = models.ForeignKey(
        Scene, null=True, blank=True, on_delete=models.CASCADE, related_name="dialogues"
    )
    title = models.CharField(max_length=100, unique=True)
    character = models.ForeignKey(
        Character, null=True, blank=True, on_delete=models.SET_NULL, related_name="dialogues"
    )
    text = models.TextField(blank=True, default="")
    requirements = models.JSONField(default=list, blank=True)
    effects = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        speaker = self.character.name if self.character else "—"
        return f"{speaker}: {self.text[:40]}"

    @staticmethod
    def _slugify(value: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", value or "").strip("_").lower()
        return slug or "node"

    @classmethod
    def _unique_title(cls, base: str, *, exclude_pk: int | None = None) -> str:
        """`base` if free, else `base_2`, `base_3`, ... — no forced numeric suffix on the first try."""
        qs = cls.objects.all() if exclude_pk is None else cls.objects.exclude(pk=exclude_pk)
        if not qs.filter(title=base).exists():
            return base
        n = 2
        while qs.filter(title=f"{base}_{n}").exists():
            n += 1
        return f"{base}_{n}"

    @classmethod
    def _generate_title(cls, base: str) -> str:
        """Always-numbered auto title: `base_1`, `base_2`, ... (the default naming scheme)."""
        n = 1
        while cls.objects.filter(title=f"{base}_{n}").exists():
            n += 1
        return f"{base}_{n}"

    @classmethod
    def create_node(
        cls,
        *,
        scene: "Scene | None",
        parent: "Dialogue | None" = None,
        character_id: int | None = None,
        text: str = "",
        requirements: list | None = None,
        effects: list | None = None,
    ) -> "Dialogue":
        """Create a node and, if `parent` is given, the edge attaching it as a response."""
        base = parent.title if parent is not None else cls._slugify(scene.name if scene else "scene")
        node = cls.objects.create(
            scene=scene,
            character_id=character_id,
            text=text,
            title=cls._generate_title(base),
            requirements=requirements or [],
            effects=effects or [],
        )
        node.sync_title_from_effects()
        if parent is not None:
            DialogueEdge.objects.create(
                from_node=parent, to_node=node, order=parent.outgoing_edges.count()
            )
        return node

    def sync_title_from_effects(self) -> None:
        """If a `remember_choice` effect is present, the node's title tracks its state_key —
        the one case where a human needs a stable, meaningful name for this node."""
        remember = next(
            (e for e in (self.effects or []) if e.get("type") == "remember_choice"), None
        )
        if not remember:
            return
        base = self._slugify(remember.get("state_key") or remember.get("label") or self.title)
        new_title = self._unique_title(base, exclude_pk=self.pk)
        if new_title != self.title:
            self.title = new_title
            self.save(update_fields=["title"])


class DialogueEdge(models.Model):
    """A directed edge in the dialogue graph: `from_node` presents this as a response that
    leads to `to_node`. `option_label` optionally overrides the response's displayed text
    (Yarn's shortcut-option-text-vs-body distinction); blank falls back to `to_node.text`.
    A node with no incoming edges is a scene root.
    """

    from_node = models.ForeignKey(Dialogue, on_delete=models.CASCADE, related_name="outgoing_edges")
    to_node = models.ForeignKey(Dialogue, on_delete=models.CASCADE, related_name="incoming_edges")
    option_label = models.CharField(max_length=200, blank=True, default="")
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["from_node", "to_node"], name="uniq_dialogue_edge")
        ]

    def __str__(self) -> str:
        return f"{self.from_node.title} -> {self.to_node.title}"


class DesignAddress(models.Model):
    """A stable, readable name for a design object — the shared word the platform, the
    creator, and a building agent all use for the same thing.

    Identity and name are deliberately separate. The object's numeric `id` is its identity
    and never changes; the *address* (`entity:goomba`) is a name derived from the object's
    own name, so renaming "Walker" to "Goomba" changes the address — and a building agent
    should rename `Walker.tscn` to `Goomba.tscn` to match. A rename is a change to
    propagate, not a break to survive.

    Retired addresses are kept (`is_current=False`) so a reference an agent wrote down
    earlier still resolves, and the answer can say "that's now called X". Resolution
    prefers a current address: if a *new* object later takes a freed name, the live one
    wins and the retired row only answers when nothing current holds it.

    Rows are assigned lazily, when the export or manifest is built — nothing needs an
    address before something reads the design, so no create endpoint has to know about it.
    """

    ENTITY = "entity"
    LEVEL = "level"
    LOCATION = "location"
    SCENE = "scene"
    CHARACTER = "character"
    ABILITY = "ability"
    OBJECT_TYPES = [ENTITY, LEVEL, LOCATION, SCENE, CHARACTER, ABILITY]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="addresses")
    object_type = models.CharField(max_length=20)
    object_id = models.PositiveIntegerField()
    slug = models.CharField(max_length=120)
    is_current = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            # Only one object may hold a given name at a time; retired rows are exempt so
            # the history can keep as many former names as it likes.
            models.UniqueConstraint(
                fields=["project", "object_type", "slug"],
                condition=models.Q(is_current=True),
                name="uniq_current_design_address",
            )
        ]
        indexes = [
            models.Index(fields=["project", "object_type", "object_id", "is_current"]),
            models.Index(fields=["project", "object_type", "slug"]),
        ]

    @property
    def address(self) -> str:
        return f"{self.object_type}:{self.slug}"

    def __str__(self) -> str:
        return self.address if self.is_current else f"{self.address} (retired)"


class BuildRecord(models.Model):
    """What an agent reported building, and which version of the design it built from.

    The write half of the design→build→design loop. The platform has no view into an engine
    project (no daemons, no plugins — agent-mediated only), so this is the only way it
    learns that something exists. A build nobody reported is indistinguishable from one that
    was never made.

    `built_hash` is the point of the whole thing: it records the design's content hash at
    the moment the object was built, so when the designer later edits that object its hash
    changes and the build is detectably **stale** — with no engine access and no reconcile
    pass. Staleness is derived at read time rather than stored, so it can never itself go
    stale.

    Identity is stored twice on purpose. `object_type`/`object_id` is the durable key and
    survives renames; `address` is what was reported and is kept so a rename can be surfaced
    as "the artifact needs renaming too". Types with no row of their own (`system:`,
    `state:`) resolve to a null `object_id` and are matched on address, which for those
    types never changes.
    """

    IN_PROGRESS = "in_progress"
    BUILT = "built"
    VERIFIED = "verified"
    STATUS_CHOICES = [
        (IN_PROGRESS, "In progress"),
        (BUILT, "Built"),
        (VERIFIED, "Verified"),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="build_records")
    engine = models.CharField(max_length=30, default="godot")
    address = models.CharField(max_length=200)
    object_type = models.CharField(max_length=20)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    engine_path = models.CharField(max_length=500, blank=True, default="")
    built_hash = models.CharField(max_length=64, blank=True, default="")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=BUILT)
    note = models.TextField(blank=True, default="")
    reported_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["address"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "engine", "address"], name="uniq_build_record_address"
            )
        ]
        indexes = [models.Index(fields=["project", "engine", "object_type", "object_id"])]

    def __str__(self) -> str:
        return f"{self.address} -> {self.engine_path or '(no path)'} [{self.status}]"
