from app.agent import TravelzyncAgent
from app.db.init_db import init_database


def main():
    print("=" * 60)
    print("Travelzync AI Agent")
    print("Type 'exit' to stop.")
    print("=" * 60)

    # Creates the feedback table and leaves the existing route
    # table unchanged.
    init_database()

    agent = TravelzyncAgent()

    history = []

    while True:
        try:
            user_message = input("\nYou: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break

        if not user_message:
            continue

        if user_message.lower() in {"exit", "quit"}:
            print("Goodbye!")
            break

        try:
            answer = agent.chat(
                user_message=user_message,
                history=history,
            )

            print(f"\nTravelzync: {answer}")

            # Keep only normal conversation turns in history.
            # Tool messages are internal to each agent call.
            history.append(
                {
                    "role": "user",
                    "content": user_message,
                }
            )
            history.append(
                {
                    "role": "assistant",
                    "content": answer,
                }
            )

            # Prevent unbounded memory growth.
            history = history[-12:]

        except Exception as exc:
            print(f"\nTravelzync error: {exc}")


if __name__ == "__main__":
    main()
