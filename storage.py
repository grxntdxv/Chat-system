import hashlib
import hmac
import secrets
import sqlite3
import time


def hash_pw(password, salt=None):
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200_000)
    return h.hex(), salt


def verify_pw(password, stored_hash, salt):
    h, _ = hash_pw(password, salt)
    return hmac.compare_digest(h, stored_hash)


class Store:
    def __init__(self, path="chat.db"):
        self.path = path
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.migrate()

    def migrate(self):
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            name       TEXT PRIMARY KEY,
            pw_hash    TEXT NOT NULL,
            salt       TEXT NOT NULL,
            question   TEXT DEFAULT '',
            answer_hash TEXT DEFAULT '',
            answer_salt TEXT DEFAULT '',
            created    REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS rooms (
            id         TEXT PRIMARY KEY,
            created    REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS messages (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            room       TEXT NOT NULL,
            sender     TEXT NOT NULL,
            body       TEXT NOT NULL,
            ts         REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_messages_room_ts
            ON messages(room, ts);
        """)
        self.db.commit()

    def user_exists(self, name):
        cur = self.db.execute("SELECT 1 FROM users WHERE name=?", (name,))
        return cur.fetchone() is not None

    def create_user(self, name, password, question="", answer=""):
        pw_hash, salt = hash_pw(password)
        ans_hash, ans_salt = ("", "") if not answer else hash_pw(answer.lower())
        try:
            self.db.execute(
                "INSERT INTO users(name, pw_hash, salt, question, answer_hash, answer_salt, created) "
                "VALUES(?,?,?,?,?,?,?)",
                (name, pw_hash, salt, question, ans_hash, ans_salt, time.time()),
            )
            self.db.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def check_login(self, name, password):
        cur = self.db.execute("SELECT pw_hash, salt FROM users WHERE name=?", (name,))
        row = cur.fetchone()
        if not row:
            return False
        return verify_pw(password, row["pw_hash"], row["salt"])

    def get_security_question(self, name):
        cur = self.db.execute("SELECT question FROM users WHERE name=?", (name,))
        row = cur.fetchone()
        return row["question"] if row else None

    def check_security_answer(self, name, answer):
        cur = self.db.execute(
            "SELECT answer_hash, answer_salt FROM users WHERE name=?", (name,)
        )
        row = cur.fetchone()
        if not row or not row["answer_hash"]:
            return False
        return verify_pw(answer.lower(), row["answer_hash"], row["answer_salt"])

    def reset_password(self, name, new_password):
        pw_hash, salt = hash_pw(new_password)
        self.db.execute(
            "UPDATE users SET pw_hash=?, salt=? WHERE name=?",
            (pw_hash, salt, name),
        )
        self.db.commit()

    def ensure_room(self, room_id):
        self.db.execute(
            "INSERT OR IGNORE INTO rooms(id, created) VALUES(?, ?)",
            (room_id, time.time()),
        )
        self.db.commit()

    def log_message(self, room, sender, body):
        self.db.execute(
            "INSERT INTO messages(room, sender, body, ts) VALUES(?,?,?,?)",
            (room, sender, body, time.time()),
        )
        self.db.commit()

    def recent_messages(self, room, limit=50):
        cur = self.db.execute(
            "SELECT sender, body, ts FROM messages WHERE room=? "
            "ORDER BY ts DESC LIMIT ?",
            (room, limit),
        )
        return list(reversed(cur.fetchall()))

    def search_messages(self, room, term, limit=50):
        like = f"%{term}%"
        cur = self.db.execute(
            "SELECT sender, body, ts FROM messages WHERE room=? AND body LIKE ? "
            "ORDER BY ts DESC LIMIT ?",
            (room, like, limit),
        )
        return list(cur.fetchall())

    def close(self):
        try:
            self.db.close()
        except Exception:
            pass