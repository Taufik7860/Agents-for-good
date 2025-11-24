import os

from agents import Agent, WebSearchTool, ModelSettings
from dotenv import load_dotenv

from .tools import get_local_tip

# Load environment variables (OPENAI_API_KEY, etc.)
load_dotenv()

# Optional: you can switch to another cheap model name if your course suggests one
DEFAULT_MODEL = os.getenv("STUDYPATH_MODEL", "gpt-4.1-mini")

# --- Specialist Agents -----------------------------------------------------


planner_agent = Agent(
    name="Curriculum Planner",
    instructions=(
        "You are a curriculum planner for students in under-resourced communities.\n"
        "- Create short, realistic study plans (3–7 days) for a specific topic.\n"
        "- Focus on low-bandwidth, low-cost resources (text, PDFs, simple websites).\n"
        "- When useful, call tools to get local tips and web links.\n"
        "- Output format:\n"
        "  1. Short encouragement (1–2 sentences)\n"
        "  2. A table-like plan with Day 1, Day 2, ...\n"
        "  3. 2–3 suggested FREE resources with brief notes."
    ),
    model=DEFAULT_MODEL,
    tools=[
        WebSearchTool(),  # hosted tool: web search
        get_local_tip     # custom local function tool
    ],
    model_settings=ModelSettings(
        temperature=0.6
    ),
)


quiz_agent = Agent(
    name="Quiz Coach",
    instructions=(
        "You are a patient quiz coach for the same educational topics.\n"
        "- Generate 3–5 short questions per turn.\n"
        "- Prefer multiple choice or very short answers.\n"
        "- Keep language simple and friendly.\n"
        "- After questions, WAIT for the learner's answers.\n"
        "- When they answer, explain correct answers clearly and kindly.\n"
        "- Emphasize growth mindset and encouragement."
    ),
    model=DEFAULT_MODEL,
    model_settings=ModelSettings(
        temperature=0.7
    ),
)

# --- Orchestrator Agent with Handoffs -------------------------------------


host_agent = Agent(
    name="StudyPath Orchestrator",
    instructions=(
        "You are StudyPath, an AI tutor for students in under-resourced communities.\n\n"
        "Your job is to understand the user's request, then either:\n"
        "- HANDOFF to the Curriculum Planner agent for plans/roadmaps/resources, OR\n"
        "- HANDOFF to the Quiz Coach agent for practice questions/quizzes, OR\n"
        "- Answer directly if it is a simple question.\n\n"
        "Guidelines:\n"
        "- If user says 'plan', 'roadmap', 'schedule', 'how to study', 'explain topic' "
        "  → handoff to Curriculum Planner.\n"
        "- If user says 'quiz', 'practice', 'test me', 'questions' "
        "  → handoff to Quiz Coach.\n"
        "- Otherwise, give a short direct answer (under 200 words) yourself.\n"
        "- Always be supportive, motivational, and clear.\n"
        "- Assume limited internet/data, so avoid sending too many links."
    ),
    model=DEFAULT_MODEL,
    handoffs=[planner_agent, quiz_agent],
    model_settings=ModelSettings(
        temperature=0.5
    ),
)
