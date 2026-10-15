import argparse

from chat_client import Client
from GUI import GUI
from local_ai import LocalAI


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", type=str, default=None)
    parser.add_argument("-m", "--model", type=str, default="phi3:mini")
    parser.add_argument("-p", "--personality", type=str, default="friendly")
    args = parser.parse_args()

    client = Client(args)
    client.init_chat()

    try:
        ai_bot = LocalAI(model=args.model, personality=args.personality)
        print("AI loaded")
    except Exception as e:
        print(f"AI not available: {e}")
        ai_bot = None

    gui = GUI(client.send, client.recv, client.sm, client.socket, ai_bot)
    gui.run()
    client.quit()


if __name__ == "__main__":
    main()