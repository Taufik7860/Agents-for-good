import json
from pathlib import Path
from typing import List

from agents import function_tool


DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "topics.json"


@function_tool
def get_local_tip(topic: str) -> str:
    """
    Get short, practical teaching/learning tips for a given topic from a local file.

    Args:
        topic: A short topic key like 'fractions', 'algebra_basics',
               'english_vocab', or 'science_environment'.

    The tool is designed for low-resource education contexts.
    It should return 2–4 bullet points that can be read offline.
    """
    if not DATA_PATH.exists():
        return "No local tips database found."

    try:
        with DATA_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return f"Error reading local tips: {e}"

    key = topic.strip().lower()
    if key not in data:
        available = ", ".join(sorted(data.keys()))
        return (
            f"Sorry, I don't have local tips for '{topic}'. "
            f"Available topics: {available}"
        )

    tips: List[str] = data[key]
    bullets = "\n".join(f"- {t}" for t in tips)
    return f"Practical local tips for **{topic}**:\n{bullets}"
