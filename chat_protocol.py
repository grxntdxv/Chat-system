import json
import time
import uuid

PROTOCOL_VERSION = "2.0"


def make(action, **payload):
    return json.dumps({
        "v": PROTOCOL_VERSION,
        "id": uuid.uuid4().hex[:12],
        "ts": time.time(),
        "action": action,
        **payload,
    })


def make_reply(original_id, status="ok", **payload):
    return json.dumps({
        "v": PROTOCOL_VERSION,
        "id": uuid.uuid4().hex[:12],
        "ts": time.time(),
        "reply_to": original_id,
        "status": status,
        **payload,
    })


def parse(raw):
    if not raw:
        return None
    try:
        d = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(d, dict):
        return None
    if d.get("v") != PROTOCOL_VERSION:
        d["_legacy"] = True
    d.setdefault("id", uuid.uuid4().hex[:12])
    return d
