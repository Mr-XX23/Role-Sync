"""What a skill is, its limits, and how its content is checked."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Collection, Iterable
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from app.core.enums import SkillCategory

NAME_CHARS = (3, 80)
DESCRIPTION_CHARS = (10, 240)
INSTRUCTIONS_CHARS = (50, 12_000)
MAX_TOOLS = 20
MAX_ENABLED = 30  # switched on at once per rep: every one is a line in the agent's instructions
MAX_WORKSPACE_SKILLS = 40
MAX_PRIVATE_SKILLS = 20
SLUG_CHARS = 60
SLUG_PATTERN = r"^[a-z0-9][a-z0-9-]{1,79}$"

# Apps a tool needs connected, so the app can say "uses Gmail" on a skill.
TOOL_APPS: dict[str, str] = {
    "search_emails": "Gmail",
    "read_email_thread": "Gmail",
    "send_email": "Gmail",
    "list_calendar_events": "Google Calendar",
    "create_calendar_event": "Google Calendar",
    "search_slack_messages": "Slack",
    "send_slack_message": "Slack",
    "search_notion": "Notion",
    "read_notion_page": "Notion",
    "create_notion_page": "Notion",
}


class SkillSource(StrEnum):
    BUILTIN = "BUILTIN"  # ships with the code (possibly customized by the workspace)
    WORKSPACE = "WORKSPACE"  # written by the workspace's owners or admins, for everyone
    PRIVATE = "PRIVATE"  # written by a rep, for their own agent


class SkillContentError(ValueError):
    """The skill's name, description, instructions, category or tools are unusable; the message says why."""


@dataclass(frozen=True, slots=True)
class SkillContent:
    name: str
    description: str
    instructions: str
    category: SkillCategory
    tools: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Skill:
    """A skill as one rep's agent sees it: a built-in (maybe customized), a workspace skill or their own."""

    ref: str  # stable handle: a built-in's key, else the skill id
    slug: str  # what the agent calls it by in use_skill
    source: SkillSource
    content: SkillContent
    version: int
    id: UUID | None = None  # the database row (custom skills and customized built-ins)
    builtin_key: str | None = None
    owner_id: UUID | None = None
    updated_by: UUID | None = None
    updated_at: datetime | None = None
    archived_at: datetime | None = None

    @property
    def name(self) -> str:
        return self.content.name

    @property
    def customized(self) -> bool:
        return self.builtin_key is not None and self.id is not None


@dataclass(frozen=True, slots=True)
class SkillState:
    """Whether a skill is switched on for a rep, and why."""

    enabled: bool
    personal: bool | None  # the rep's own switch; None = never changed (on by default)
    workspace_enabled: bool  # an admin's switch for everyone (always True for private skills)


@dataclass(frozen=True, slots=True)
class SkillUsage:
    total: int = 0
    mine: int = 0
    auto: int = 0
    picked: int = 0
    delegated: int = 0
    last_used_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ParsedSkill:
    """A skill read from a SKILL.md file or drafted by a model, not yet saved."""

    name: str
    description: str
    instructions: str
    category: SkillCategory
    tools: tuple[str, ...]
    warnings: tuple[str, ...] = field(default_factory=tuple)


def slugify(name: str) -> str:
    """'Discovery call prep' → 'discovery-call-prep': how the agent refers to a skill."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    slug = "-".join(re.findall(r"[a-z0-9]+", ascii_name))[:SLUG_CHARS].strip("-")
    return slug if len(slug) >= 2 else "skill"


def humanize(slug: str) -> str:
    """'discovery-call-prep' → 'Discovery call prep' (a SKILL.md name is written like a slug)."""
    words = re.split(r"[-_\s]+", slug.strip())
    text = " ".join(word for word in words if word)
    return text[:1].upper() + text[1:]


def clean_content(
    *,
    name: str,
    description: str,
    instructions: str,
    category: str,
    tools: Iterable[str],
    known_tools: Collection[str] | None,
) -> SkillContent:
    """Normalized content, or ``SkillContentError``. ``known_tools=None`` skips the tool check (built-ins)."""
    name = " ".join(name.split())
    description = " ".join(description.split())
    instructions = instructions.replace("\r\n", "\n").replace("\r", "\n").strip()
    _length("The name", name, NAME_CHARS)
    _length("The description", description, DESCRIPTION_CHARS)
    _length("The instructions", instructions, INSTRUCTIONS_CHARS)
    try:
        chosen = SkillCategory(str(category).strip().upper())
    except ValueError as exc:
        raise SkillContentError(f"'{category}' is not a skill category ({', '.join(c.value for c in SkillCategory)})") from exc
    listed = list(dict.fromkeys(str(tool).strip() for tool in tools if str(tool).strip()))
    if len(listed) > MAX_TOOLS:
        raise SkillContentError(f"A skill can name at most {MAX_TOOLS} tools")
    if known_tools is not None:
        unknown = [tool for tool in listed if tool not in known_tools]
        if unknown:
            raise SkillContentError(f"The agent has no tool called {', '.join(unknown)}")
    return SkillContent(name=name, description=description, instructions=instructions, category=chosen, tools=tuple(listed))


def _length(what: str, value: str, limits: tuple[int, int]) -> None:
    low, high = limits
    if len(value) < low:
        raise SkillContentError(f"{what} needs at least {low} characters")
    if len(value) > high:
        raise SkillContentError(f"{what} can be at most {high:,} characters (it has {len(value):,})")
