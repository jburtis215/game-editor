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


class Level(models.Model):
    """A level in the game. Belongs to a project; contains an ordered set of scenes."""

    project = models.ForeignKey(
        Project, null=True, blank=True, on_delete=models.CASCADE, related_name="levels"
    )
    name = models.CharField(max_length=100)
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self) -> str:
        return self.name


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
    """

    level = models.ForeignKey(Level, on_delete=models.CASCADE, related_name="locations")
    name = models.CharField(max_length=100, default="New Location")
    description = models.TextField(blank=True, default="")
    order = models.PositiveIntegerField(default=0)
    # Characters present at this location (manually assigned, editable on the Locations page).
    characters = models.ManyToManyField(Character, related_name="locations", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self) -> str:
        return f"{self.level.name} / {self.name}"


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
