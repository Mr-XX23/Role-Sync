"""SKILL.md files: the Anthropic Agent Skills format, for import and export.

    ---
    name: discovery-call-prep
    description: Use when the rep has a discovery call coming up.
    metadata:
      display_name: Discovery call prep
      category: ENGAGE
      tools: [list_calendar_events, recall]
    ---
    # Discovery call prep
    ...instructions...

Only the file's instructions come in: a skill folder's scripts and other files are never read or run.
Tools this agent doesn't have are dropped with a warning (``allowed-tools`` of other agents name
other tools), and so are over-long descriptions.
"""

from __future__ import annotations

import re
from collections.abc import Collection
from typing import Any

import yaml

from app.core.enums import SkillCategory
from app.skills.model import DESCRIPTION_CHARS, MAX_TOOLS, ParsedSkill, Skill, SkillContentError, clean_content, humanize

MAX_FILE_BYTES = 64 * 1024
_FRONTMATTER = re.compile(r"\A---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)(.*)\Z", re.DOTALL)


def read_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """(the fields between the --- lines, the rest of the file), or ``SkillContentError``."""
    if len(text.encode("utf-8")) > MAX_FILE_BYTES:
        raise SkillContentError(f"A SKILL.md file can be at most {MAX_FILE_BYTES // 1024} KB")
    text = text.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n").strip()
    # A model's answer may wrap the file in a code fence.
    fenced = re.fullmatch(r"```[a-zA-Z]*\n(.*)\n```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    match = _FRONTMATTER.match(text)
    if match is None:
        raise SkillContentError("A SKILL.md file starts with a block between --- lines holding its name and description")
    try:
        meta = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as exc:
        raise SkillContentError(f"The block between the --- lines isn't valid YAML: {str(exc).splitlines()[0]}") from exc
    if not isinstance(meta, dict):
        raise SkillContentError("The block between the --- lines must hold fields such as name and description")
    return meta, match.group(2)


def parse_skill_md(text: str, *, known_tools: Collection[str]) -> ParsedSkill:
    """The skill a SKILL.md file describes, or ``SkillContentError`` saying what is wrong with it."""
    meta, body = read_frontmatter(text)
    extra = meta.get("metadata") if isinstance(meta.get("metadata"), dict) else {}
    warnings: list[str] = []

    raw_name = _text(extra.get("display_name")) or humanize(_text(meta.get("name")))
    description = " ".join(_text(meta.get("description")).split())
    if len(description) > DESCRIPTION_CHARS[1]:
        cut = description[: DESCRIPTION_CHARS[1] - 1].rsplit(" ", 1)[0].rstrip(",;:") + "…"
        warnings.append(f"The description was shortened to {DESCRIPTION_CHARS[1]} characters")
        description = cut
    category = _text(extra.get("category") or meta.get("category")).upper() or SkillCategory.OTHER.value
    if category not in {item.value for item in SkillCategory}:
        warnings.append(f"Unknown category '{category}' was replaced with OTHER")
        category = SkillCategory.OTHER.value

    listed = _tool_list(extra.get("tools") or meta.get("tools") or meta.get("allowed-tools"))
    kept = [tool for tool in listed if tool in known_tools][:MAX_TOOLS]
    dropped = [tool for tool in listed if tool not in known_tools]
    if dropped:
        warnings.append(f"Tools this agent doesn't have were left out: {', '.join(dropped[:10])}")

    content = clean_content(
        name=raw_name,
        description=description,
        instructions=body,
        category=category,
        tools=kept,
        known_tools=None,
    )
    return ParsedSkill(
        name=content.name,
        description=content.description,
        instructions=content.instructions,
        category=content.category,
        tools=content.tools,
        warnings=tuple(warnings),
    )


def render_skill_md(skill: Skill) -> str:
    """The skill as a SKILL.md file another workspace (or agent) can import."""
    front: dict[str, Any] = {
        "name": skill.slug,
        "description": skill.content.description,
        "metadata": {
            "display_name": skill.content.name,
            "category": skill.content.category.value,
            "tools": list(skill.content.tools),
            "version": skill.version,
            "source": "RoleSync sales agent",
        },
    }
    header = yaml.safe_dump(front, sort_keys=False, allow_unicode=True, width=1000).strip()
    return f"---\n{header}\n---\n\n{skill.content.instructions.strip()}\n"


def _text(value: Any) -> str:
    return str(value).strip() if isinstance(value, str | int | float) else ""


def _tool_list(value: Any) -> list[str]:
    if isinstance(value, str):
        items = re.split(r"[,\s]+", value)
    elif isinstance(value, list):
        items = [item for item in value if isinstance(item, str)]
    else:
        items = []
    return list(dict.fromkeys(item.strip() for item in items if item.strip()))
