from chat_group import RoomManager, S_ALONE, S_TALKING


def test_connect_new_room():
    rm = RoomManager()
    rm.join_server("a")
    rm.join_server("b")
    rid = rm.connect("a", "b")
    assert rid is not None
    assert set(rm.members_of("a")) == {"a", "b"}
    assert rm.status["a"] == S_TALKING


def test_merge_rooms():
    rm = RoomManager()
    for n in "abcd":
        rm.join_server(n)
    rm.connect("a", "b")
    rm.connect("c", "d")
    rm.connect("a", "c")
    assert set(rm.members_of("a")) == {"a", "b", "c", "d"}
    assert len(rm.rooms) == 1


def test_disconnect():
    rm = RoomManager()
    rm.join_server("a")
    rm.join_server("b")
    rm.connect("a", "b")
    rid, others = rm.disconnect("a")
    assert "b" in others
    assert rm.get_room("a") is None
    assert rm.status["b"] == S_ALONE


def test_leave_server():
    rm = RoomManager()
    rm.join_server("a")
    rm.join_server("b")
    rm.connect("a", "b")
    rm.leave_server("a")
    assert not rm.is_member("a")
    assert rm.status["b"] == S_ALONE