"""Skills without a database: the built-in playbooks, SKILL.md import and export, and content checks."""

from __future__ import annotations

import re

import pytest

from app.core.enums import SkillCategory
from app.skills.builtins import BUILTIN_SKILLS
from app.skills.model import (
    DESCRIPTION_CHARS,
    SLUG_PATTERN,
    Skill,
    SkillContent,
    SkillContentError,
    SkillSource,
    clean_content,
    humanize,
    slugify,
)
from app.skills.skillmd import parse_skill_md, render_skill_md
from tests.unit.test_registry_and_config import _full_registry

KNOWN = frozenset({"search_deals", "recall", "send_email", "research_prospect"})
INSTRUCTIONS = "# Follow-up\n\n1. Check the deal with `search_deals`.\n2. Draft the email and send it with `send_email`."


def test_ten_built_in_skills_ship_and_name_only_real_tools():
    tools = {definition.name for definition in _full_registry().all()}
    assert len(BUILTIN_SKILLS) == 10
    assert len({skill.key for skill in BUILTIN_SKILLS}) == 10
    for skill in BUILTIN_SKILLS:
        assert re.match(SLUG_PATTERN, skill.key), skill.key
        assert skill.content.description.startswith("Use when"), skill.key
        assert set(skill.content.tools) <= tools, (skill.key, set(skill.content.tools) - tools)
        # Every tool a playbook tells the agent to use is one it lists (so the app can say which apps it needs).
        named = set(re.findall(r"`([a-z_]+)`", skill.content.instructions)) & tools
        assert named <= set(skill.content.tools), (skill.key, named - set(skill.content.tools))
    assert {skill.content.category for skill in BUILTIN_SKILLS} >= {
        SkillCategory.PROSPECT, SkillCategory.QUALIFY, SkillCategory.ENGAGE, SkillCategory.CLOSE, SkillCategory.PIPELINE
    }


def test_a_skill_survives_export_and_import_unchanged():
    content = SkillContent(
        name="Renewal follow-up", description="Use when a customer's renewal is due within 60 days.",
        instructions=INSTRUCTIONS, category=SkillCategory.PIPELINE, tools=("search_deals", "send_email"),
    )
    skill = Skill(ref="x", slug="renewal-follow-up", source=SkillSource.WORKSPACE, content=content, version=3)

    text = render_skill_md(skill)
    parsed = parse_skill_md(text, known_tools=KNOWN)

    assert text.startswith("---\nname: renewal-follow-up\n")
    assert (parsed.name, parsed.description, parsed.instructions, parsed.category, parsed.tools) == (
        content.name, content.description, content.instructions, content.category, content.tools
    )
    assert parsed.warnings == ()


def test_a_skill_from_another_agent_comes_in_with_what_fits_and_says_what_was_left_out():
    file = (
        "﻿---\r\nname: pdf-summaries\r\n"
        f"description: {'Summarize long PDFs for the rep. ' * 20}\r\n"
        "allowed-tools: Bash, Read, recall\r\n"
        "license: MIT\r\n---\r\n\r\n# PDF summaries\r\n\r\nRead the file, then write five bullet points and a one-line takeaway.\r\n"
    )

    parsed = parse_skill_md(file, known_tools=KNOWN)

    # Named from the file's own heading, which keeps the author's spelling ("PDF", not "Pdf").
    assert parsed.name == "PDF summaries" and parsed.category is SkillCategory.OTHER
    assert parsed.tools == ("recall",)
    assert len(parsed.description) <= DESCRIPTION_CHARS[1] and parsed.description.endswith("…")
    assert parsed.instructions.startswith("# PDF summaries")
    assert any("shortened" in warning for warning in parsed.warnings)
    assert any("Bash, Read" in warning for warning in parsed.warnings)


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("# Just markdown, no header\n\nSteps...", "starts with a block"),
        ("---\nname: [unclosed\n---\nbody", "isn't valid YAML"),
        ("---\n- a list\n---\nbody", "must hold fields"),
        ("---\nname: tiny\ndescription: Use when testing short bodies.\n---\nToo short.", "instructions needs at least"),
        ("x" * 70_000, "at most 64 KB"),
    ],
    ids=["no-header", "bad-yaml", "not-fields", "short-instructions", "too-big"],
)
def test_unusable_skill_files_are_refused_with_the_reason(text, message):
    with pytest.raises(SkillContentError, match=message):
        parse_skill_md(text, known_tools=KNOWN)


def test_a_models_answer_wrapped_in_a_code_fence_still_reads():
    fenced = f"```markdown\n---\nname: follow-up\ndescription: Use when a meeting just ended.\n---\n{INSTRUCTIONS}\n```"
    assert parse_skill_md(fenced, known_tools=KNOWN).name == "Follow-up"


@pytest.mark.parametrize(
    ("body", "name"),
    [
        ("# Meeting follow-up\n\n", "Meeting follow-up"),  # the heading spells the id: keep its hyphen
        ("# Wrap-up\n\n", "Meeting follow up"),  # a heading about something else doesn't rename the skill
        ("", "Meeting follow up"),
    ],
    ids=["heading-matches", "heading-differs", "no-heading"],
)
def test_an_imported_skill_is_named_from_its_heading_only_when_it_spells_the_id(body, name):
    steps = INSTRUCTIONS.removeprefix("# Follow-up\n\n")
    file = f"---\nname: meeting-follow-up\ndescription: Use when a meeting just ended.\n---\n{body}{steps}"
    assert parse_skill_md(file, known_tools=KNOWN).name == name


def test_content_is_tidied_and_checked():
    content = clean_content(
        name="  Renewal   follow-up ", description="Use when\na renewal is due.", instructions=f"\r\n{INSTRUCTIONS}\r\n",
        category="pipeline", tools=["send_email", "send_email", " recall "], known_tools=KNOWN,
    )
    assert (content.name, content.description, content.category, content.tools) == (
        "Renewal follow-up", "Use when a renewal is due.", SkillCategory.PIPELINE, ("send_email", "recall")
    )
    assert "\r" not in content.instructions and not content.instructions.startswith("\n")

    for overrides, message in [
        ({"tools": ["delete_everything"]}, "no tool called delete_everything"),
        ({"category": "MARKETING"}, "not a skill category"),
        ({"name": "ab"}, "name needs at least 3"),
        ({"instructions": "y" * 12_001}, "at most 12,000 characters"),
    ]:
        arguments = {"name": "Renewal", "description": "Use when a renewal is due.", "instructions": INSTRUCTIONS,
                     "category": "OTHER", "tools": [], "known_tools": KNOWN} | overrides
        with pytest.raises(SkillContentError, match=message):
            clean_content(**arguments)


def test_skill_ids_are_readable_words():
    assert slugify("Discovery Call Prep (EMEA) — v2!") == "discovery-call-prep-emea-v2"
    assert slugify("Café démo") == "cafe-demo"
    assert slugify("✨") == "skill"
    assert len(slugify("word " * 40)) <= 60
    assert humanize("discovery-call-prep") == "Discovery call prep"
