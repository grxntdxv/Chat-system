import argparse
import select
import socket
import time

import chat_protocol as proto
from chat_utils import SERVER, CHAT_PORT, mysend, myrecv, S_LOGGEDIN
from local_ai import LocalAI


class ChatBotClient:
    def __init__(self, args, personality="friendly", model="phi4-mini:latest"):
        self.args = args
        self.bot_name = "Chatbot"
        self.personality = personality
        self.model = model
        self.bot = LocalAI(model=model, personality=personality)
        self.socket = None
        self.room = None
        self.bot_online = False
        self.recent_turns = []
        self.max_turns = 20

    def send(self, payload):
        return mysend(self.socket, payload)

    def recv(self):
        return myrecv(self.socket)

    def init_chat(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        svr = SERVER if self.args.d is None else (self.args.d, CHAT_PORT)
        self.socket.connect(svr)

    def login_bot(self):
        self.send(proto.make("login", name=self.bot_name,
                             password="", is_bot=True))
        r = proto.parse(self.recv())
        if r and r.get("status") == "ok":
            self.bot_online = True
            print(f"{self.bot_name} logged in")
            return True
        print(f"login failed: {r}")
        return False

    def fetch_history(self, count=20):
        self.send(proto.make("history", count=count))
        deadline = time.time() + 3
        while time.time() < deadline:
            r = proto.parse(self.recv())
            if not r:
                break
            if r.get("action") == "history" or r.get("results") is not None:
                return r.get("results", "")
        return ""

    def respond(self, from_user, question):
        context = ""
        try:
            history = self.fetch_history(15)
            if history:
                context = "Recent room chat:\n" + history
        except Exception:
            pass

        turns = list(self.recent_turns[-10:])
        turns.append({
            "role": "user",
            "content": f"{from_user} says: {question}\n"
                       f"Reply as {self.bot_name}, addressing {from_user}."
        })
        reply = self.bot.chat_with_history(self.bot_name, context, turns)
        self.recent_turns.append({"role": "user", "content": question})
        self.recent_turns.append({"role": "assistant", "content": reply})
        if len(self.recent_turns) > self.max_turns:
            self.recent_turns = self.recent_turns[-self.max_turns:]
        return reply

    def process_incoming(self, raw):
        if not raw:
            return
        d = proto.parse(raw)
        if not d:
            return
        action = d.get("action")

        if action == "connect":
            who = d.get("from", "someone")
            self.room = d.get("room")
            print(f"{who} opened a chat (room={self.room})")
            self.send(proto.make("connect", target=who))

        elif action == "exchange":
            from_user = (d.get("from") or "").strip("[]")
            message = d.get("message") or ""
            if from_user == self.bot_name:
                return
            mention = f"@{self.bot_name}"
            if mention.lower() in message.lower():
                question = message.replace(mention, "").strip() or "Hello!"
                print(f"{from_user}: {question}")
                reply = self.respond(from_user, question)
                self.send(proto.make("exchange", message=reply))
                print("replied")

        elif action == "disconnect":
            print("peer disconnected")

    def quit(self):
        self.bot_online = False
        try:
            if self.socket:
                self.socket.close()
        except Exception:
            pass

    def run_chat(self):
        self.init_chat()
        if not self.login_bot():
            self.quit()
            return
        print("bot listening... ctrl+c to stop")
        try:
            while self.bot_online:
                r, _, _ = select.select([self.socket], [], [], 0.1)
                if self.socket in r:
                    raw = self.recv()
                    if not raw:
                        break
                    self.process_incoming(raw)
        except KeyboardInterrupt:
            print("\nbot shutting down")
        finally:
            self.quit()


def main():
    parser = argparse.ArgumentParser(description="ChatBot Client")
    parser.add_argument("-d", type=str, default=None, help="server IP")
    parser.add_argument("-p", "--personality", type=str, default="friendly",
                        choices=["friendly", "professional", "sarcastic",
                                 "poetic", "shakespeare"])
    parser.add_argument("-m", "--model", type=str, default="phi4-mini:latest")
    args = parser.parse_args()

    bot = ChatBotClient(args, personality=args.personality, model=args.model)
    bot.run_chat()


if __name__ == "__main__":
    main()