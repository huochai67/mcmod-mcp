from __future__ import annotations

import asyncio
import re
from pathlib import Path

from mcmod.mcp_server import build_server

SKILL_PATH = Path(__file__).parents[1] / ".claude" / "skills" / "mcmod" / "SKILL.md"


def test_skill_frontmatter_and_tool_coverage() -> None:
    text = SKILL_PATH.read_text(encoding="utf-8")
    assert text.startswith("---\nname: mcmod\n")
    assert "description:" in text
    assert len(text.splitlines()) < 500

    async def tool_names() -> set[str]:
        server = build_server(client=object())
        return {tool.name for tool in await server.list_tools()}

    documented = set(re.findall(r"`(mcmod_[a-z_]+)`", text))
    assert documented == asyncio.run(tool_names())
