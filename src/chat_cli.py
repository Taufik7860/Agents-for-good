import asyncio

from agents import Runner, SQLiteSession
from dotenv import load_dotenv

from .agents_setup import host_agent


async def chat():
    load_dotenv()

    # Session with persistent memory across turns
    session = SQLiteSession(
        session_id="demo-student-1",
        db_path="study_sessions.db"
    )

    print("=== StudyPath – Agents for Good (Education) ===")
    print("Multi-agent tutor using OpenAI Agents SDK")
    print("Type 'exit' or 'quit' to end.\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if user_input.lower() in {"exit", "quit"}:
            print("Goodbye! Keep learning ✨")
            break

        if not user_input:
            continue

        # Run the multi-agent workflow
        result = await Runner.run(
            host_agent,
            input=user_input,
            session=session,
        )

        print(f"\nStudyPath: {result.final_output}\n")


def main():
    asyncio.run(chat())


if __name__ == "__main__":
    main()
