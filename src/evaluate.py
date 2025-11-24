import asyncio
from dataclasses import dataclass

from agents import Runner, SQLiteSession
from dotenv import load_dotenv

from .agents_setup import host_agent


@dataclass
class TestCase:
    name: str
    prompt: str
    expectation: str


TEST_CASES = [
    TestCase(
        name="Plan request routes to planner",
        prompt="I am in 10th standard and weak in algebra. Make a 5 day study plan.",
        expectation="Should handoff to Curriculum Planner and produce a day-wise plan."
    ),
    TestCase(
        name="Quiz request routes to quiz coach",
        prompt="Please give me a short quiz on fractions.",
        expectation="Should handoff to Quiz Coach and ask 3–5 questions."
    ),
    TestCase(
        name="Simple direct Q&A",
        prompt="What is a fraction in simple words?",
        expectation="Short direct explanation under ~200 words."
    ),
]


async def run_single_test(case: TestCase, session: SQLiteSession):
    print(f"\n=== Test: {case.name} ===")
    print(f"Prompt: {case.prompt}")
    print(f"Expectation: {case.expectation}")

    result = await Runner.run(
        host_agent,
        input=case.prompt,
        session=session,
    )

    output = str(result.final_output)
    print("\n--- Model output (truncated to 600 chars) ---")
    print(output[:600])
    print("\n--- Simple heuristic checks ---")

    # Simple heuristic: just check length & some keywords
    ok_length = len(output.split()) < 300
    print(f"- Length < 300 words? {'OK' if ok_length else 'TOO LONG'}")

    if "plan" in case.name.lower():
        has_day = any(word.lower().startswith("day") for word in output.split())
        print(f"- Mentions days (Day 1/Day 2 etc.)? {'OK' if has_day else 'MAYBE'}")

    if "quiz" in case.name.lower():
        question_marks = output.count("?")
        print(f"- Contains at least 3 questions? {'OK' if question_marks >= 3 else 'MAYBE'}")


async def main():
    load_dotenv()

    # Use a separate session for evaluation
    session = SQLiteSession("evaluation-session", "evaluation_sessions.db")

    for case in TEST_CASES:
        await run_single_test(case, session)


if __name__ == "__main__":
    asyncio.run(main())
