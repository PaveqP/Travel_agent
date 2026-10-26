import asyncio
import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime, timezone
from uuid import uuid4

from psycopg.errors import UniqueViolation
from psycopg_pool import AsyncConnectionPool
from pydantic import BaseModel, ConfigDict, Field, field_validator


class AccountInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=80)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=10, max_length=128)

    @field_validator("email")
    @classmethod
    def email_address(cls, value: str) -> str:
        if value.count("@") != 1 or "." not in value.rsplit("@", 1)[1] or any(c.isspace() for c in value):
            raise ValueError("Укажите корректный email")
        return value.lower()


class LoginInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class AccountProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=80)
    phone: str = Field(default="", max_length=30, pattern=r"^[+()\d\s-]*$")
    city: str = Field(default="", max_length=100)
    interests: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("interests")
    @classmethod
    def valid_interests(cls, value: list[str]) -> list[str]:
        if any(not x.strip() or len(x) > 100 for x in value):
            raise ValueError("Каждый интерес должен содержать от 1 до 100 символов")
        return value


def password_hash(password: str, salt: str) -> str:
    return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class Accounts:
    def __init__(self, pool: AsyncConnectionPool):
        self.pool = pool
        self.lock = asyncio.Lock()

    async def setup(self) -> None:
        async with self.pool.connection() as db:
            await db.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                id TEXT PRIMARY KEY, email TEXT UNIQUE, salt TEXT, password TEXT,
                profile TEXT NOT NULL, telegram_id BIGINT UNIQUE, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                digest TEXT PRIMARY KEY, owner TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                expires DOUBLE PRECISION NOT NULL
            );
            CREATE TABLE IF NOT EXISTS portal_trips (
                id TEXT PRIMARY KEY, owner TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL, snapshot TEXT NOT NULL,
                progress TEXT NOT NULL DEFAULT '{}'
            );
            CREATE INDEX IF NOT EXISTS portal_trips_owner ON portal_trips(owner, updated_at);
            CREATE TABLE IF NOT EXISTS telegram_links (
                digest TEXT PRIMARY KEY, owner TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                expires DOUBLE PRECISION NOT NULL
            );
            CREATE TABLE IF NOT EXISTS telegram_state (
                telegram_id BIGINT PRIMARY KEY, trip_id TEXT, action TEXT
            );
            CREATE TABLE IF NOT EXISTS web_login_links (
                digest TEXT PRIMARY KEY, owner TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                expires DOUBLE PRECISION NOT NULL
            );
            CREATE TABLE IF NOT EXISTS bot_cursor (id INTEGER PRIMARY KEY CHECK(id=1), position BIGINT NOT NULL);
        """)

    async def one(self, query: str, args: tuple = ()) -> tuple | None:
        async with self.pool.connection() as db:
            cursor = await db.execute(query, args)
            return await cursor.fetchone()

    async def account(self, owner: str) -> dict | None:
        row = await self.one("SELECT id,email,profile,telegram_id FROM accounts WHERE id=%s", (owner,))
        if row is None:
            return None
        return {"id": row[0], "email": row[1], **json.loads(row[2]), "telegram_linked": row[3] is not None}

    async def register(self, data: AccountInput) -> str:
        salt = secrets.token_hex(16)
        hashed = await asyncio.to_thread(password_hash, data.password, salt)
        owner = str(uuid4())
        async with self.lock, self.pool.connection() as db, db.transaction():
            try:
                await db.execute(
                    "INSERT INTO accounts(id,email,salt,password,profile,created_at) VALUES(%s,%s,%s,%s,%s,%s)",
                    (owner, data.email, salt, hashed, AccountProfile(name=data.name).model_dump_json(), datetime.now(timezone.utc).isoformat()),
                )
            except UniqueViolation:
                raise ValueError("Этот email уже зарегистрирован") from None
        return owner

    async def login(self, data: LoginInput) -> str | None:
        row = await self.one("SELECT id,salt,password FROM accounts WHERE email=%s", (data.email.lower(),))
        salt = row[1] if row else "0" * 32
        hashed = await asyncio.to_thread(password_hash, data.password, salt)
        return row[0] if row and hmac.compare_digest(hashed, row[2]) else None

    async def session(self, owner: str) -> str:
        token = secrets.token_urlsafe(32)
        async with self.lock, self.pool.connection() as db, db.transaction():
            await db.execute("DELETE FROM sessions WHERE expires<%s", (time.time(),))
            await db.execute("INSERT INTO sessions VALUES(%s,%s,%s)", (token_hash(token), owner, time.time() + 30 * 86400))
            return token

    async def authenticate(self, token: str) -> str | None:
        row = await self.one("SELECT owner FROM sessions WHERE digest=%s AND expires>%s", (token_hash(token), time.time()))
        return row[0] if row else None

    async def revoke(self, token: str) -> None:
        async with self.lock, self.pool.connection() as db, db.transaction():
            await db.execute("DELETE FROM sessions WHERE digest=%s", (token_hash(token),))

    async def update(self, owner: str, profile: AccountProfile) -> dict:
        async with self.lock, self.pool.connection() as db, db.transaction():
            await db.execute("UPDATE accounts SET profile=%s WHERE id=%s", (profile.model_dump_json(), owner))
        return await self.account(owner)

    async def delete(self, owner: str) -> None:
        async with self.lock, self.pool.connection() as db, db.transaction():
            await db.execute("DELETE FROM telegram_state WHERE telegram_id=(SELECT telegram_id FROM accounts WHERE id=%s)", (owner,))
            await db.execute("DELETE FROM accounts WHERE id=%s", (owner,))

    async def sync_trip(self, owner: str, trip_id: str, snapshot: dict) -> None:
        now = datetime.now(timezone.utc).isoformat()
        async with self.lock, self.pool.connection() as db, db.transaction():
            await db.execute(
                "INSERT INTO portal_trips(id,owner,created_at,updated_at,snapshot) VALUES(%s,%s,%s,%s,%s) "
                "ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at,snapshot=excluded.snapshot WHERE portal_trips.owner=excluded.owner",
                (trip_id, owner, now, now, json.dumps(snapshot, ensure_ascii=False)),
            )

    async def owns(self, owner: str, trip_id: str) -> bool:
        return await self.one("SELECT id FROM portal_trips WHERE owner=%s AND id=%s", (owner, trip_id)) is not None

    async def trips(self, owner: str) -> list[dict]:
        async with self.pool.connection() as db:
            cursor = await db.execute("SELECT id,created_at,updated_at,snapshot,progress FROM portal_trips WHERE owner=%s ORDER BY updated_at DESC", (owner,))
            rows = await cursor.fetchall()
        return [{"trip_id": r[0], "created_at": r[1], "updated_at": r[2], "state": json.loads(r[3]), "progress": json.loads(r[4])} for r in rows]

    async def progress(self, owner: str, trip_id: str, progress: dict[str, bool]) -> None:
        async with self.lock, self.pool.connection() as db, db.transaction():
            await db.execute("UPDATE portal_trips SET progress=%s WHERE owner=%s AND id=%s", (json.dumps(progress), owner, trip_id))

    async def link(self, owner: str) -> str:
        token = secrets.token_urlsafe(24)
        async with self.lock, self.pool.connection() as db, db.transaction():
            await db.execute("DELETE FROM telegram_links WHERE owner=%s OR expires<%s", (owner, time.time()))
            await db.execute("INSERT INTO telegram_links VALUES(%s,%s,%s)", (token_hash(token), owner, time.time() + 600))
            return token

    async def telegram_owner(self, telegram_id: int, name: str, link: str | None = None) -> str:
        async with self.lock, self.pool.connection() as db, db.transaction():
            existing = await self.one("SELECT id FROM accounts WHERE telegram_id=%s", (telegram_id,))
            if link:
                target = await self.one("SELECT owner FROM telegram_links WHERE digest=%s AND expires>%s", (token_hash(link), time.time()))
                if not target:
                    raise ValueError("Ссылка устарела. Создайте новую в личном кабинете сайта.")
                owner = target[0]
                linked = await self.one("SELECT telegram_id FROM accounts WHERE id=%s", (owner,))
                if (existing and existing[0] != owner) or (linked and linked[0] not in (None, telegram_id)):
                    raise ValueError("Аккаунт уже связан. Сначала отключите Telegram в личном кабинете.")
                await db.execute("UPDATE accounts SET telegram_id=%s WHERE id=%s", (telegram_id, owner))
                await db.execute("DELETE FROM telegram_links WHERE digest=%s", (token_hash(link),))
            elif existing:
                return existing[0]
            else:
                owner = str(uuid4())
                await db.execute("INSERT INTO accounts(id,profile,telegram_id,created_at) VALUES(%s,%s,%s,%s)", (owner, AccountProfile(name=name[:80] or "Путешественник").model_dump_json(), telegram_id, datetime.now(timezone.utc).isoformat()))
            return owner

    async def unlink(self, owner: str) -> None:
        async with self.lock, self.pool.connection() as db, db.transaction():
            await db.execute("DELETE FROM telegram_state WHERE telegram_id=(SELECT telegram_id FROM accounts WHERE id=%s)", (owner,))
            await db.execute("UPDATE accounts SET telegram_id=NULL WHERE id=%s", (owner,))
            await db.execute("DELETE FROM telegram_links WHERE owner=%s", (owner,))

    async def bot_state(self, telegram_id: int, trip_id: str | None = None, action: str | None = None, *, write: bool = False) -> tuple[str | None, str | None]:
        if write:
            async with self.lock, self.pool.connection() as db, db.transaction():
                await db.execute("INSERT INTO telegram_state VALUES(%s,%s,%s) ON CONFLICT(telegram_id) DO UPDATE SET trip_id=excluded.trip_id,action=excluded.action", (telegram_id, trip_id, action))
        row = await self.one("SELECT trip_id,action FROM telegram_state WHERE telegram_id=%s", (telegram_id,))
        return row if row else (None, None)

    async def bot_offset(self, position: int | None = None) -> int:
        if position is not None:
            async with self.pool.connection() as db:
                await db.execute("INSERT INTO bot_cursor VALUES(1,%s) ON CONFLICT(id) DO UPDATE SET position=excluded.position", (position,))
        row = await self.one("SELECT position FROM bot_cursor WHERE id=1")
        return row[0] if row else 0

    async def web_login_link(self, owner: str) -> str:
        token = secrets.token_urlsafe(24)
        async with self.lock, self.pool.connection() as db, db.transaction():
            await db.execute("DELETE FROM web_login_links WHERE owner=%s OR expires<%s", (owner, time.time()))
            await db.execute("INSERT INTO web_login_links VALUES(%s,%s,%s)", (token_hash(token), owner, time.time() + 600))
        return token

    async def consume_web_login(self, token: str) -> str | None:
        async with self.pool.connection() as db:
            cursor = await db.execute("DELETE FROM web_login_links WHERE digest=%s AND expires>%s RETURNING owner", (token_hash(token), time.time()))
            row = await cursor.fetchone()
        return row[0] if row else None
