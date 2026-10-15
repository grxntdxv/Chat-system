import socket
import client_state_machine as csm
from chat_utils import SERVER, CHAT_PORT, mysend, myrecv


class Client:
    def __init__(self, args):
        self.args = args
        self.name = ""
        self.socket = None
        self.sm = None

    def init_chat(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        svr = SERVER if self.args.d is None else (self.args.d, CHAT_PORT)
        self.socket.connect(svr)
        self.sm = csm.ClientSM(self.socket)

    def send(self, msg):
        return mysend(self.socket, msg)

    def recv(self):
        return myrecv(self.socket)

    def quit(self):
        try:
            if self.socket:
                self.socket.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        try:
            if self.socket:
                self.socket.close()
        except Exception:
            pass