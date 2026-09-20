"""Champion kit prose, cleaned for the labelling prompt.

Deliberately crude. The point of champion_patch.raw is that this can be
rewritten and re-run against stored entries without refetching a patch, so v0
only has to be good enough to get raw into the database.

Uses each ability's `description`, not its `tooltip`: tooltips carry unresolved
{{ qdamage }} placeholders and damage-type markup, descriptions are prose.
"""

import html
import re
from typing import Any

SLOTS = ("Q", "W", "E", "R")

# Riot ships HTML-ish markup in descriptions: mostly <br> and <font>, plus
# custom tags like <magicDamage> and <keywordMajor>. All of it is presentation.
_TAG = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"\s+")


def _clean(text: str) -> str:
    return _WHITESPACE.sub(" ", html.unescape(_TAG.sub(" ", text))).strip()


def build(entry: dict[str, Any]) -> str:
    """Render one Data Dragon entry as passive + QWER prose.

    Abilities are labelled by slot because the slot carries meaning the prose
    does not — an ultimate is not just another ability.
    """
    passive = entry["passive"]
    lines = [f"Passive ({passive['name']}): {_clean(passive['description'])}"]
    # strict: every champion ships exactly 4 spells today, and a champion that
    # ever does not should fail loudly rather than lose an ability.
    for slot, spell in zip(SLOTS, entry["spells"], strict=True):
        lines.append(f"{slot} ({spell['name']}): {_clean(spell['description'])}")
    return "\n".join(lines)
