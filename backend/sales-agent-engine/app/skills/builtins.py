"""The built-in skills: SKILL.md files in ``builtin/``, loaded once. Their order is the order shown in the app.

A new version of a built-in ships with the code. A workspace that customized one keeps its own copy
(``skill.builtin_key``) until an admin resets it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.skills.model import SkillContent, SkillContentError
from app.skills.skillmd import parse_skill_md, read_frontmatter

_DIRECTORY = Path(__file__).resolve().parent / "builtin"


class _AnyTool:
    """Built-ins are checked against the full tool set by a test, not against whichever tools this process has."""

    def __contains__(self, item: object) -> bool:
        return True


@dataclass(frozen=True, slots=True)
class BuiltinSkill:
    key: str
    version: int
    content: SkillContent


def _load(path: Path) -> BuiltinSkill:
    text = path.read_text(encoding="utf-8")
    meta, _ = read_frontmatter(text)
    parsed = parse_skill_md(text, known_tools=_AnyTool())
    key = str(meta.get("name") or "")
    if not key or parsed.warnings:
        raise SkillContentError(f"built-in skill {path.name} is malformed: {', '.join(parsed.warnings) or 'no name'}")
    version = int((meta.get("metadata") or {}).get("version") or 1)
    content = SkillContent(
        name=parsed.name,
        description=parsed.description,
        instructions=parsed.instructions,
        category=parsed.category,
        tools=parsed.tools,
    )
    return BuiltinSkill(key=key, version=version, content=content)


BUILTIN_SKILLS: tuple[BuiltinSkill, ...] = tuple(_load(path) for path in sorted(_DIRECTORY.glob("*.md")))
BUILTIN_BY_KEY: dict[str, BuiltinSkill] = {skill.key: skill for skill in BUILTIN_SKILLS}
