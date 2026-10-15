import asyncio
import logging
import time

import chat_protocol as proto
import chat_group as grp
import indexer
from chat_utils import SERVER, MAX_MSG_BYTES
from storage import Store

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    handlers=[logging.FileHandler("server.log"), logging.StreamHandler()],
)
log = logging.getLogger("server")

ALLOWED_BOTS = {"Chatbot", "ChatBot"}


class RateLimiter:
    def __init__(self, rate=8, per=60.0):
        self.rate = rate
        self.per = per
        self.buckets = {}

    def allow(self, key):
        now = time.time()
        tokens, last = self.buckets.get(key, (self.rate, now))
        tokens = min(self.rate, tokens + (now - last) * self.rate / self.per)
        if tokens < 1:
            self.buckets[key] = (tokens, now)
            return False
        self.buckets[key] = (tokens - 1, now)
        return True


class Client:
    __slots__ = ("reader", "writer", "name", "is_bot", "addr")

    def __init__(self, reader, writer, addr):
        self.reader = reader
        self.writer = writer
        self.name = None
        self.is_bot = False
        self.addr = addr


class Server:
    def __init__(self, host=None, port=None, db_path="chat.db"):
        self.host = host or SERVER[0]
        self.port = port or SERVER[1]
        self.store = Store(db_path)
        self.rooms = grp.RoomManager()
        self.clients = {}
        self.name_to_client = {}
        self.indices = {}
        self.limiter = RateLimiter()

        try:
            self.sonnet = indexer.PIndex("AllSonnets.txt")
            log.info("Loaded AllSonnets.txt")
        except Exception as e:
            log.warning("Sonnet index unavailable: %s", e)
            self.sonnet = None

        self.server = None

    async def start(self):
        self.server = await asyncio.start_server(
            self.handle_client, self.host, self.port)
        addrs = ", ".join(str(s.getsockname()) for s in self.server.sockets)
        log.info("Server listening on %s", addrs)
        async with self.server:
            await self.server.serve_forever()

    async def handle_client(self, reader, writer):
        addr = writer.get_extra_info("peername")
        client = Client(reader, writer, addr)
        self.clients[writer] = client
        log.info("New connection from %s", addr)
        try:
            ok = await self.handle_auth(client)
            if not ok:
                return
            while True:
                raw = await self.read_frame(reader)
                if raw is None:
                    break
                if not self.limiter.allow(client.name or str(addr)):
                    await self.reply(client, raw, "error",
                                     message="Rate limit exceeded")
                    continue
                await self.dispatch(client, raw)
        except (asyncio.IncompleteReadError, ConnectionResetError):
            pass
        except Exception as e:
            log.exception("Client handler error: %s", e)
        finally:
            await self.cleanup(client)

    async def cleanup(self, client):
        if client.name:
            log.info("Disconnecting %s", client.name)
            self.rooms.leave_server(client.name)
            self.name_to_client.pop(client.name, None)
            self.indices.pop(client.name, None)
        self.clients.pop(client.writer, None)
        try:
            client.writer.close()
            await client.writer.wait_closed()
        except Exception:
            pass

    async def read_frame(self, reader):
        try:
            header = await reader.readexactly(5)
            size = int(header.decode("ascii"))
            if size < 0 or size > MAX_MSG_BYTES:
                return None
            body = await reader.readexactly(size)
            return body.decode("utf-8", "replace")
        except (asyncio.IncompleteReadError, ValueError, OSError):
            return None

    async def send(self, writer, payload):
        try:
            data = payload.encode("utf-8")
            header = f"{len(data):05d}".encode("ascii")
            writer.write(header + data)
            await writer.drain()
            return True
        except Exception:
            return False

    async def reply(self, client, raw, status="ok", **extra):
        d = proto.parse(raw) or {}
        msg = proto.make_reply(d.get("id", ""), status=status, **extra)
        await self.send(client.writer, msg)

    async def handle_auth(self, client):
        raw = await self.read_frame(client.reader)
        if raw is None:
            return False
        msg = proto.parse(raw)
        if not msg:
            await self.send(client.writer, proto.make_reply("", "error",
                            message="bad json"))
            return False
        action = msg.get("action")
        if action == "login":
            return await self.do_login(client, msg)
        if action == "register":
            return await self.do_register(client, msg)
        if action == "reset_request":
            return await self.do_reset_request(client, msg)
        if action == "reset_confirm":
            return await self.do_reset_confirm(client, msg)
        await self.send(client.writer, proto.make_reply(
            msg["id"], "error", message="auth required"))
        return False

    async def do_login(self, client, msg):
        name = (msg.get("name") or "").strip()
        password = msg.get("password") or ""
        is_bot = bool(msg.get("is_bot"))
        if not name:
            await self.reply(client, msg["id"], "invalid")
            return False
        if is_bot:
            if name not in ALLOWED_BOTS:
                await self.reply(client, msg["id"], "invalid")
                return False
        else:
            if not self.store.check_login(name, password):
                await self.reply(client, msg["id"], "invalid")
                return False
        if name in self.name_to_client:
            await self.reply(client, msg["id"], "duplicate")
            return False
        client.name = name
        client.is_bot = is_bot
        self.name_to_client[name] = client
        self.rooms.join_server(name)
        self.indices[name] = indexer.Index(name)
        await self.send(client.writer, proto.make_reply(
            msg["id"], "ok", name=name, is_bot=is_bot))
        log.info("Login OK: %s%s", name, " (bot)" if is_bot else "")
        return True

    async def do_register(self, client, msg):
        name = (msg.get("name") or "").strip()
        password = msg.get("password") or ""
        question = msg.get("security_q") or ""
        answer = (msg.get("security_a") or "").strip()
        if not name or not password:
            await self.reply(client, msg["id"], "invalid")
            return False
        if self.store.user_exists(name):
            await self.reply(client, msg["id"], "exists")
            return False
        ok = self.store.create_user(name, password, question, answer)
        await self.reply(client, msg["id"], "ok" if ok else "error")
        return False

    async def do_reset_request(self, client, msg):
        name = (msg.get("name") or "").strip()
        q = self.store.get_security_question(name)
        if q is None:
            await self.reply(client, msg["id"], "no_user")
        else:
            await self.reply(client, msg["id"], "ok", question=q)
        return False

    async def do_reset_confirm(self, client, msg):
        name = (msg.get("name") or "").strip()
        answer = (msg.get("answer") or "").strip()
        new_pw = msg.get("new_password") or ""
        if not new_pw:
            await self.reply(client, msg["id"], "invalid")
            return False
        if not self.store.check_security_answer(name, answer):
            await self.reply(client, msg["id"], "wrong_answer")
            return False
        self.store.reset_password(name, new_pw)
        await self.reply(client, msg["id"], "ok")
        return False

    async def dispatch(self, client, raw):
        msg = proto.parse(raw)
        if not msg:
            return
        action = msg.get("action")
        handler = {
            "connect": self.do_connect,
            "exchange": self.do_exchange,
            "disconnect": self.do_disconnect,
            "list": self.do_list,
            "poem": self.do_poem,
            "time": self.do_time,
            "search": self.do_search,
            "history": self.do_history,
            "rooms": self.do_rooms,
            "ping": self.do_ping,
        }.get(action)
        if handler is None:
            await self.reply(client, raw, "error", message="unknown action")
            return
        await handler(client, msg)

    async def do_ping(self, client, msg):
        await self.reply(client, msg["id"], "ok")

    async def do_connect(self, client, msg):
        target = (msg.get("target") or "").strip()
        if not target or target == client.name:
            await self.reply(client, msg["id"], "self")
            return
        if not self.rooms.is_member(target):
            await self.reply(client, msg["id"], "no-user")
            return
        rid = self.rooms.connect(client.name, target)
        self.store.ensure_room(rid)
        await self.reply(client, msg["id"], "success", room=rid, peer=target)
        peer = self.name_to_client.get(target)
        if peer:
            await self.send(peer.writer, proto.make(
                "connect", status="request",
                **{"from": client.name, "room": rid}))

    async def do_exchange(self, client, msg):
        text = (msg.get("message") or "").strip()
        if not text:
            return
        room = self.rooms.get_room(client.name)
        if room is None:
            await self.reply(client, msg["id"], "error", message="not in a room")
            return
        said = f"[{client.name}] {text}"
        self.store.log_message(room, client.name, text)
        if client.name in self.indices:
            self.indices[client.name].add_msg_and_index(said)
        for member in self.rooms.members_of(client.name):
            if member == client.name:
                continue
            peer = self.name_to_client.get(member)
            if not peer:
                continue
            await self.send(peer.writer, proto.make(
                "exchange", **{"from": f"[{client.name}]",
                               "message": text, "room": room}))

    async def do_disconnect(self, client, msg):
        rid, others = self.rooms.disconnect(client.name)
        await self.reply(client, msg["id"], "ok")
        for other in others:
            peer = self.name_to_client.get(other)
            if peer:
                await self.send(peer.writer, proto.make(
                    "disconnect", **{"from": client.name}))

    async def do_list(self, client, msg):
        await self.reply(client, msg["id"], "ok",
                         results=self.rooms.list_all())

    async def do_rooms(self, client, msg):
        await self.reply(client, msg["id"], "ok",
                         results=self.rooms.list_all())

    async def do_poem(self, client, msg):
        if self.sonnet is None:
            await self.reply(client, msg["id"], "ok",
                             results="Poem feature unavailable")
            return
        try:
            idx = int(msg.get("target", ""))
        except (ValueError, TypeError):
            await self.reply(client, msg["id"], "error",
                             message="invalid poem number")
            return
        try:
            poem = "\n".join(self.sonnet.get_poem(idx)).strip()
        except Exception as e:
            poem = f"Error fetching poem: {e}"
        await self.reply(client, msg["id"], "ok", results=poem)

    async def do_time(self, client, msg):
        ctime = time.strftime("%d.%m.%y,%H:%M", time.localtime())
        await self.reply(client, msg["id"], "ok", results=ctime)

    async def do_search(self, client, msg):
        term = (msg.get("target") or "").strip()
        room = self.rooms.get_room(client.name)
        if not term or room is None:
            await self.reply(client, msg["id"], "ok",
                             results="No messages found")
            return
        rows = self.store.search_messages(room, term)
        if not rows:
            await self.reply(client, msg["id"], "ok",
                             results=f"No messages containing '{term}'")
            return
        lines = [f"{sender}: {body}" for sender, body, _ in rows]
        await self.reply(client, msg["id"], "ok", results="\n".join(lines))

    async def do_history(self, client, msg):
        try:
            n = int(msg.get("count", 30))
        except (ValueError, TypeError):
            n = 30
        n = max(1, min(n, 200))
        room = self.rooms.get_room(client.name)
        if room is None:
            await self.reply(client, msg["id"], "ok", results="")
            return
        rows = self.store.recent_messages(room, n)
        lines = [f"{sender}: {body}" for sender, body, _ in rows]
        await self.reply(client, msg["id"], "ok", results="\n".join(lines))


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Chat server")
    parser.add_argument("--host", default=SERVER[0])
    parser.add_argument("--port", type=int, default=SERVER[1])
    parser.add_argument("--db", default="chat.db")
    args = parser.parse_args()
    server = Server(args.host, args.port, args.db)
    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        log.info("Server shutting down...")
    finally:
        server.store.close()


if __name__ == "__main__":
    main()