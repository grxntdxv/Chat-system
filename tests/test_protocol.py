import socket
import select
import threading

import chat_protocol as proto
from chat_utils import mysend, myrecv, FramedReader


def test_roundtrip():
    a, b = socket.socketpair()
    try:
        assert mysend(a, "hello")
        assert myrecv(b) == "hello"
    finally:
        a.close()
        b.close()


def test_protocol_roundtrip():
    raw = proto.make("ping", value=42)
    d = proto.parse(raw)
    assert d["action"] == "ping"
    assert d["value"] == 42
    assert d["v"] == proto.PROTOCOL_VERSION


def test_partial_read():
    a, b = socket.socketpair()
    try:
        payload = b"x" * 2000

        def send():
            a.sendall(b"02000" + payload)

        threading.Thread(target=send).start()
        assert myrecv(b) == "x" * 2000
    finally:
        a.close()
        b.close()


def test_framed_reader():
    a, b = socket.socketpair()
    try:
        body1 = b'{"action":"x"}'
        body2 = b'{"action":"y"}'
        a.sendall(b"00014" + body1)
        a.sendall(b"00014" + body2)
        b.setblocking(False)
        rlist, _, _ = select.select([b], [], [], 1.0)
        assert rlist, "no data arrived"
        r = FramedReader(b)
        msgs, disc = r.read_available()
        assert not disc
        assert len(msgs) == 2
        assert '"x"' in msgs[0]
        assert '"y"' in msgs[1]
    finally:
        a.close()
        b.close()


def test_bad_size_header():
    a, b = socket.socketpair()
    try:
        a.sendall(b"XXXXX")
        a.close()
        assert myrecv(b) == ""
    finally:
        b.close()