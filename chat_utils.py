import socket
import time

CHAT_IP = "127.0.0.1"
CHAT_PORT = 1112
SERVER = (CHAT_IP, CHAT_PORT)

SIZE_SPEC = 5
MAX_MSG_BYTES = 64 * 1024
CHAT_WAIT = 0.2

S_OFFLINE = 0
S_CONNECTED = 1
S_LOGGEDIN = 2
S_CHATTING = 3

menu = (
    "\n++++ Choose one of the following commands\n"
    "  @Chatbot <msg>      talk to the chatbot (must be in your room)\n"
    "  @ai <msg>           chat with your local AI\n"
    "  /aipic: <prompt>    generate an image from text\n"
    "  /summary            summarize recent chat\n"
    "  /keywords           extract keywords from recent chat\n"
    "  /history [n]        show last n messages (default 30)\n"
    "  /rooms              list active rooms\n"
    "  time                system time\n"
    "  who                 list users and rooms\n"
    "  ? <term>            search your chat logs\n"
    "  p <#>               get sonnet #<#>\n"
    "  bye                 leave current chat\n"
    "  q                   quit\n\n"
)


def print_state(state):
    names = {S_OFFLINE: "Offline", S_CONNECTED: "Connected",
             S_LOGGEDIN: "Logged in", S_CHATTING: "Chatting"}
    print(f"**** State: {names.get(state, 'Unknown')} ****")


def mysend(s, msg):
    if isinstance(msg, str):
        msg = msg.encode("utf-8")
    if len(msg) > MAX_MSG_BYTES:
        raise ValueError(f"message too large: {len(msg)} bytes")
    header = f"{len(msg):0{SIZE_SPEC}d}".encode("ascii")
    packet = header + msg
    total = 0
    while total < len(packet):
        try:
            sent = s.send(packet[total:])
        except OSError as e:
            print(f"send error: {e}")
            return False
        if sent == 0:
            return False
        total += sent
    return True


def myrecv(s):
    size_bytes = b""
    while len(size_bytes) < SIZE_SPEC:
        try:
            chunk = s.recv(SIZE_SPEC - len(size_bytes))
        except OSError:
            return ""
        if not chunk:
            return ""
        size_bytes += chunk
    try:
        size = int(size_bytes.decode("ascii"))
    except ValueError:
        return ""
    if size < 0 or size > MAX_MSG_BYTES:
        return ""
    body = b""
    while len(body) < size:
        try:
            chunk = s.recv(size - len(body))
        except OSError:
            return ""
        if not chunk:
            return ""
        body += chunk
    return body.decode("utf-8", errors="replace")


class FramedReader:
    def __init__(self, sock):
        self.sock = sock
        self.buf = b""
        self.expected = None

    def read_available(self):
        try:
            chunk = self.sock.recv(8192)
        except BlockingIOError:
            return [], False
        except OSError:
            return [], True
        if not chunk:
            return [], True
        self.buf += chunk
        messages = []
        while True:
            if self.expected is None:
                if len(self.buf) < SIZE_SPEC:
                    break
                try:
                    self.expected = int(self.buf[:SIZE_SPEC].decode("ascii"))
                except ValueError:
                    return [], True
                if self.expected < 0 or self.expected > MAX_MSG_BYTES:
                    return [], True
                self.buf = self.buf[SIZE_SPEC:]
            if len(self.buf) < self.expected:
                break
            messages.append(self.buf[:self.expected].decode("utf-8", "replace"))
            self.buf = self.buf[self.expected:]
            self.expected = None
        return messages, False


def text_proc(text, user):
    ctime = time.strftime("%d.%m.%y,%H:%M", time.localtime())
    return f"({ctime}) {user} : {text}"