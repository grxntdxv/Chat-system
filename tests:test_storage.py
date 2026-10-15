import os
import tempfile

from storage import Store, hash_pw, verify_pw


def test_password_hashing():
    h, s = hash_pw("secret")
    assert verify_pw("secret", h, s)
    assert not verify_pw("wrong", h, s)


def test_user_crud():
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "t.db")
        s = Store(db)
        assert not s.user_exists("alice")
        assert s.create_user("alice", "pw", "Q?", "a")
        assert s.user_exists("alice")
        assert s.check_login("alice", "pw")
        assert not s.check_login("alice", "bad")
        assert s.get_security_question("alice") == "Q?"
        assert s.check_security_answer("alice", "A")
        s.reset_password("alice", "new")
        assert s.check_login("alice", "new")
        s.close()


def test_messages():
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "t.db")
        s = Store(db)
        s.ensure_room("room-1")
        s.log_message("room-1", "alice", "hi")
        s.log_message("room-1", "bob", "hello")
        rows = s.recent_messages("room-1", 10)
        assert [r["body"] for r in rows] == ["hi", "hello"]
        found = s.search_messages("room-1", "hello")
        assert len(found) == 1
        s.close()