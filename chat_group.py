S_ALONE = 0
S_TALKING = 1


class Room:
    def __init__(self, rid):
        self.id = rid
        self.members = set()


class RoomManager:
    def __init__(self):
        self.rooms = {}
        self.user_to_room = {}
        self.status = {}

    def join_server(self, name):
        self.status[name] = S_ALONE

    def leave_server(self, name):
        self.disconnect(name)
        self.status.pop(name, None)

    def is_member(self, name):
        return name in self.status

    def new_room(self):
        n = 1
        while f"room-{n}" in self.rooms:
            n += 1
        rid = f"room-{n}"
        self.rooms[rid] = Room(rid)
        return rid

    def get_room(self, user):
        return self.user_to_room.get(user)

    def leave_room(self, user):
        rid = self.user_to_room.pop(user, None)
        if not rid:
            return None
        room = self.rooms.get(rid)
        if room:
            room.members.discard(user)
            if not room.members:
                del self.rooms[rid]
        self.status[user] = S_ALONE
        return rid

    def connect(self, me, peer):
        me_rid = self.user_to_room.get(me)
        peer_rid = self.user_to_room.get(peer)

        if me_rid and peer_rid and me_rid == peer_rid:
            return me_rid

        if me_rid and not peer_rid:
            target = me_rid
        elif peer_rid and not me_rid:
            target = peer_rid
        elif me_rid and peer_rid:
            target = me_rid
            self.merge(me_rid, peer_rid)
        else:
            target = self.new_room()

        room = self.rooms.setdefault(target, Room(target))
        for u in (me, peer):
            if self.user_to_room.get(u) not in (None, target):
                self.leave_room(u)
            room.members.add(u)
            self.user_to_room[u] = target
            self.status[u] = S_TALKING
        return target

    def merge(self, keep, drop):
        if keep == drop:
            return
        drop_room = self.rooms.pop(drop, None)
        if not drop_room:
            return
        keep_room = self.rooms.setdefault(keep, Room(keep))
        for u in list(drop_room.members):
            keep_room.members.add(u)
            self.user_to_room[u] = keep

    def disconnect(self, user):
        rid = self.user_to_room.get(user)
        if not rid:
            return None, []
        room = self.rooms.get(rid)
        others = []
        if room:
            others = [u for u in room.members if u != user]
        self.leave_room(user)
        if room and len(room.members) == 1:
            last = next(iter(room.members))
            self.status[last] = S_ALONE
        return rid, others

    def members_of(self, user):
        rid = self.user_to_room.get(user)
        if not rid:
            return [user] if self.is_member(user) else []
        room = self.rooms.get(rid)
        if not room:
            return [user]
        return [user] + [u for u in room.members if u != user]

    def list_all(self):
        lines = ["Users: ------------"]
        for u, st in sorted(self.status.items()):
            tag = "chatting" if st == S_TALKING else "idle"
            lines.append(f"  {u} [{tag}]")
        lines.append("Rooms: -----------")
        for rid, room in sorted(self.rooms.items()):
            lines.append(f"  {rid}: {sorted(room.members)}")
        return "\n".join(lines)

    def list_me(self, user):
        return self.members_of(user)