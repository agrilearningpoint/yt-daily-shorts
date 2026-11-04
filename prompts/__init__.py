"""Prompt templates loader and Jinja2 rendering utility."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict
from jinja2 import Environment, FileSystemLoader

_PROMPTS_DIR = Path(__file__).parent


def render_prompt(template_relative_path: str, context: Dict[str, Any]) -> str:
    """Render a Jinja2 prompt template relative to the prompts directory."""
    env = Environment(loader=FileSystemLoader(str(_PROMPTS_DIR)), autoescape=False)
    template = env.get_template(template_relative_path)
    return template.render(**context)
