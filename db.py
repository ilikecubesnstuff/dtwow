from sqlalchemy import Integer, String, Float, DateTime, Enum, ForeignKey
from sqlalchemy import select, insert
from sqlalchemy.orm import DeclarativeBase, MappedAsDataclass, Mapped, mapped_column
from sqlalchemy.ext.asyncio import AsyncAttrs, create_async_engine, async_sessionmaker
import sqlalchemy.sql.functions as func

engine = create_async_engine("sqlite+aiosqlite:///twow_data.db")
session = async_sessionmaker(engine, expire_on_commit=False)


async def fetch_by_id(cls, id):
    async with session() as s:
        obj = await s.get(cls, id)
    return obj


import enum

class TwowState(enum.Enum):
    REGISTERING = enum.auto()
    RESPONDING = enum.auto()
    VOTING = enum.auto()
    IDLE = enum.auto()
    HIBERNATING = enum.auto()


class Base(AsyncAttrs, DeclarativeBase):
    pass


class Twow(Base):
    __tablename__ = "twows"

    id = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id = mapped_column(Integer)
    channel_id = mapped_column(ForeignKey('channels.id'))
    private_channel_id = mapped_column(Integer, nullable=True)
    current_message_id = mapped_column(Integer, nullable=True)
    current_round = mapped_column(Integer, default=0)
    state = mapped_column(Enum(TwowState))
    start_timestamp = mapped_column(DateTime(timezone=True), default=func.now())


class TwowChannel(Base):
    __tablename__ = "channels"

    id = mapped_column(Integer, primary_key=True, autoincrement='ignore_fk')
    host_id = mapped_column(Integer)
    current_twow_id = mapped_column(Integer, nullable=True)


class Prompt(Base):
    __tablename__ = "prompts"

    id = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id = mapped_column(Integer)
    content = mapped_column(String)
    timestamp = mapped_column(DateTime(timezone=True), default=func.now())


async def init():
    async with engine.begin() as conn:
        # await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
