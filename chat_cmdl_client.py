import argparse
import select
import sys

from chat_client import Client
import chat_protocol as proto
from chat_utils import S_LOGGEDIN, S_OFFLINE, menu


def prompt_login(send, recv):
    while True:
        print("\n1) Login   2) Register   3) Reset password   4) Quit")
        choice = input("Choose: ").strip()
        if choice == "1":
            name = input("Name: ").strip()
            pw = input("Password: ").strip()
            send(proto.make("login", name=name, password=pw))
            r = proto.parse(recv())
            if r and r.get("status") == "ok":
                return name
            print("Login failed:", r.get("status") if r else "no response")
        elif choice == "2":
            name = input("New username: ").strip()
            pw = input("New password: ").strip()
            q = input("Security question: ").strip()
            a = input("Answer: ").strip()
            send(proto.make("register", name=name, password=pw,
                            security_q=q, security_a=a))
            r = proto.parse(recv())
            print("Registered" if r and r.get("status") == "ok"
                  else f"failed: {r.get('status') if r else 'no response'}")
            raise SystemExit(0)
        elif choice == "3":
            name = input("Username: ").strip()
            send(proto.make("reset_request", name=name))
            r = proto.parse(recv())
            if not r or r.get("status") != "ok":
                print("no such user")
                continue
            print("Q:", r.get("question", ""))
            ans = input("Answer: ").strip()
            new_pw = input("New password: ").strip()
            send(proto.make("reset_confirm", name=name,
                            answer=ans, new_password=new_pw))
            r = proto.parse(recv())
            print("reset" if r and r.get("status") == "ok" else "wrong answer")
            raise SystemExit(0)
        else:
            raise SystemExit(0)


def main():
    parser = argparse.ArgumentParser(description="CLI chat client")
    parser.add_argument("-d", type=str, default=None, help="server IP")
    args = parser.parse_args()

    client = Client(args)
    client.init_chat()
    try:
        name = prompt_login(client.send, client.recv)
    except SystemExit:
        client.quit()
        return

    client.name = name
    client.sm.set_state(S_LOGGEDIN)
    client.sm.set_myname(name)
    print(menu)

    try:
        while client.sm.get_state() != S_OFFLINE:
            rlist, _, _ = select.select([client.socket, sys.stdin], [], [], 0.2)

            if client.socket in rlist:
                raw = client.recv()
                if not raw:
                    print("server disconnected")
                    break
                out = client.sm.proc("", raw)
                if out:
                    print(out)

            if sys.stdin in rlist:
                my_msg = sys.stdin.readline().strip()
                if not my_msg:
                    continue
                out = client.sm.proc(my_msg, "")
                if out:
                    print(out)
    except KeyboardInterrupt:
        print("\nshutting down...")
    finally:
        client.quit()


if __name__ == "__main__":
    main()