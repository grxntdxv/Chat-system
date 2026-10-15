import chat_protocol as proto
from chat_utils import (
    S_OFFLINE, S_LOGGEDIN, S_CHATTING, menu,
    mysend, myrecv,
)


class ClientSM:
    def __init__(self, s):
        self.state = S_OFFLINE
        self.peer = ""
        self.me = ""
        self.out_msg = ""
        self.s = s

    def set_state(self, state):
        self.state = state

    def get_state(self):
        return self.state

    def set_myname(self, name):
        self.me = name

    def get_myname(self):
        return self.me

    def send(self, action, **payload):
        return mysend(self.s, proto.make(action, **payload))

    def recv_json(self):
        raw = myrecv(self.s)
        if not raw:
            return None
        return proto.parse(raw)

    def connect_to(self, peer):
        self.send("connect", target=peer)
        r = self.recv_json()
        if not r:
            self.out_msg += "Server error during connect\n"
            return False
        st = r.get("status")
        if st == "success":
            self.peer = peer
            return True
        if st == "self":
            self.out_msg += "Cannot talk to yourself.\n"
        elif st == "no-user":
            self.out_msg += "User is not online.\n"
        elif st == "duplicate":
            self.out_msg += "User already in another chat.\n"
        else:
            self.out_msg += "Connection failed.\n"
        return False

    def disconnect(self):
        self.send("disconnect")
        self.out_msg += f"You are disconnected from {self.peer}\n"
        self.peer = ""
        self.state = S_LOGGEDIN

    def proc(self, my_msg, peer_msg):
        self.out_msg = ""
        if self.state == S_LOGGEDIN:
            self.proc_logged_in(my_msg)
            self.proc_peer_generic(peer_msg)
        elif self.state == S_CHATTING:
            self.proc_chatting(my_msg)
            self.proc_peer_chat(peer_msg)
        else:
            self.out_msg += "You are offline.\n"
        return self.out_msg

    def proc_logged_in(self, my_msg):
        if not my_msg:
            return
        cmd, _, arg = my_msg.partition(" ")
        cmd = cmd.strip()
        if cmd == "q":
            self.out_msg += "See you next time!\n"
            self.state = S_OFFLINE
        elif cmd == "time":
            self.send("time")
            r = self.recv_json() or {}
            self.out_msg += "Time: " + r.get("results", "?")
        elif cmd == "who":
            self.send("list")
            r = self.recv_json() or {}
            self.out_msg += r.get("results", "")
        elif cmd == "c":
            if self.connect_to(arg):
                self.state = S_CHATTING
                self.out_msg += f"Connected to {arg}. Chat away!\n"
        elif cmd == "?":
            self.send("search", target=arg)
            r = self.recv_json() or {}
            self.out_msg += r.get("results", "")
        elif cmd == "p" and arg.isdigit():
            self.send("poem", target=arg)
            r = self.recv_json() or {}
            self.out_msg += r.get("results", "")
        elif cmd == "/history":
            n = arg.strip() if arg.strip().isdigit() else "30"
            self.send("history", count=n)
            r = self.recv_json() or {}
            self.out_msg += r.get("results", "") or "No history."
        elif cmd == "/rooms":
            self.send("rooms")
            r = self.recv_json() or {}
            self.out_msg += r.get("results", "")
        else:
            self.out_msg += menu

    def proc_peer_generic(self, peer_msg):
        d = proto.parse(peer_msg)
        if not d:
            return
        if d.get("action") == "connect":
            who = d.get("from", "someone")
            self.peer = who
            self.out_msg += f"{who} started a chat with you.\n"
            self.state = S_CHATTING

    def proc_chatting(self, my_msg):
        if not my_msg:
            return
        if my_msg == "bye":
            self.disconnect()
        elif my_msg == "q":
            if self.peer:
                self.disconnect()
            self.state = S_OFFLINE
            self.out_msg += "Quitting...\n"
        elif my_msg.startswith("c "):
            new_peer = my_msg[2:].strip()
            self.send("connect", target=new_peer)
            self.out_msg += f"Requesting to add {new_peer}...\n"
        elif my_msg.startswith("? "):
            term = my_msg[2:].strip()
            self.send("search", target=term)
            r = self.recv_json() or {}
            self.out_msg += r.get("results", "")
        else:
            self.send("exchange", message=my_msg)
            self.out_msg += f"[{self.me}] {my_msg}\n"

    def proc_peer_chat(self, peer_msg):
        d = proto.parse(peer_msg)
        if not d:
            return
        action = d.get("action")
        if action == "connect":
            who = d.get("from", "someone")
            if not self.peer:
                self.peer = who
            self.out_msg += f"({who} joined the chat)\n"
        elif action == "disconnect":
            self.state = S_LOGGEDIN
            self.out_msg += "Chat ended.\n"
            self.out_msg += menu
        elif action == "exchange":
            self.out_msg += f"{d.get('from','?')}: {d.get('message','')}\n"