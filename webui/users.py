import re
import secrets
import uuid
from contextlib import asynccontextmanager

from fastapi.security import OAuth2PasswordRequestForm
from fastapi_users import BaseUserManager, InvalidPasswordException, UUIDIDMixin
from fastapi_users.db import SQLAlchemyBaseUserTableUUID, SQLAlchemyUserDatabase
from fastapi_users.exceptions import UserAlreadyExists
from fastapi_users.schemas import BaseUserCreate, BaseUserUpdate
from sqlalchemy import String, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

USERNAME = re.compile(r"^[a-z][a-z0-9_.-]{2,31}$")


def user_email(username):
    # ponytail: FastAPI Users requires e-mail; this app uses local usernames and sends no mail.
    return f"{username}@accounts.autodeploykit.invalid"


def validate_username(username):
    if not isinstance(username, str) or not USERNAME.fullmatch(username):
        raise ValueError("账号需为 3-32 位小写字母、数字、点、下划线或连字符，并以字母开头")
    return username


class Base(DeclarativeBase):
    pass


class User(SQLAlchemyBaseUserTableUUID, Base):
    username: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    session_version: Mapped[str] = mapped_column(String(32), default=lambda: secrets.token_hex(16), nullable=False)


class UserCreate(BaseUserCreate):
    email: str
    username: str


class UserUpdate(BaseUserUpdate):
    session_version: str | None = None


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    async def validate_password(self, password, user):
        if len(password) < 12:
            raise InvalidPasswordException(reason="口令至少需要 12 个字符")


class UserStore:
    def __init__(self, db):
        self.db = db
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{db.path.as_posix()}")
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def initialize(self):
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
            columns = await connection.run_sync(lambda sync: {col["name"] for col in inspect(sync).get_columns("user")})
            if "session_version" not in columns:
                await connection.execute(text("ALTER TABLE user ADD COLUMN session_version TEXT NOT NULL DEFAULT ''"))
                await connection.execute(text("UPDATE user SET session_version=:stamp WHERE session_version=''"), {"stamp": secrets.token_hex(16)})

    async def close(self):
        await self.engine.dispose()

    @asynccontextmanager
    async def manager(self):
        async with self.sessions() as session:
            yield UserManager(SQLAlchemyUserDatabase(session, User))

    async def any_users(self):
        async with self.sessions() as session:
            return (await session.scalar(select(User.id).limit(1))) is not None

    async def create(self, username, password, *, admin=False):
        username = validate_username(username)
        async with self.manager() as manager:
            try:
                return await manager.create(
                    UserCreate(
                        username=username,
                        email=user_email(username),
                        password=password,
                        is_active=True,
                        is_verified=True,
                        is_superuser=admin,
                    )
                )
            except IntegrityError as exc:
                raise UserAlreadyExists from exc

    async def authenticate(self, username, password):
        if not isinstance(username, str) or not USERNAME.fullmatch(username):
            return None
        credentials = OAuth2PasswordRequestForm(username=user_email(username), password=password)
        async with self.manager() as manager:
            user = await manager.authenticate(credentials)
            if user and user.is_active:
                return user
            if username != "admin" or user or not self.db.verify_admin(password):
                return None
            try:
                user = await manager.create(
                    UserCreate(
                        username="admin", email=user_email("admin"), password=password,
                        is_active=True, is_verified=True, is_superuser=True,
                    )
                )
            except (UserAlreadyExists, IntegrityError):
                await manager.user_db.session.rollback()
                return await manager.authenticate(credentials)
            self.db.clear_legacy_admin()
            return user

    async def verify(self, username, password):
        return await self.authenticate(username, password)

    async def list_users(self):
        async with self.sessions() as session:
            return list((await session.scalars(select(User).order_by(User.username))).all())

    async def get(self, user_id):
        async with self.manager() as manager:
            return await manager.get(uuid.UUID(user_id))

    async def update(self, user_id, **changes):
        async with self.manager() as manager:
            user = await manager.get(uuid.UUID(user_id))
            return await manager.update(UserUpdate(session_version=secrets.token_hex(16), **changes), user)


def public_user(user):
    return {
        "id": str(user.id),
        "username": user.username,
        "is_active": user.is_active,
        "is_admin": user.is_superuser,
    }
