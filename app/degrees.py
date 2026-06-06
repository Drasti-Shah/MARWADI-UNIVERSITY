"""Load the scraped degree dataset and expose a compact view for the LLM."""
import json
from functools import lru_cache

from . import config


@lru_cache(maxsize=1)
def load_degrees() -> list[dict]:
    with open(config.DATA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["degrees"]


def catalog_for_llm() -> str:
    """A compact English catalog injected into the system prompt.

    Kept small so the model stays fast and grounded only in real data.
    """
    lines = []
    for d in load_degrees():
        lines.append(
            f"- id={d['id']} | {d['degree_name']} | level={d['level']} | "
            f"for={'/'.join(d['suitable_for'])} | duration={d['duration']} | "
            f"fees={d['fees']} | eligibility={d['eligibility']} | "
            f"documents={', '.join(d['required_documents'])} | note={d.get('highlights','')}"
        )
    return "\n".join(lines)
