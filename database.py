import enum
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import BigInteger, Integer, String, Numeric, Enum, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from config import config


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


engine = create_async_engine(config.DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class NFTStatus(str, enum.Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    SOLD = "SOLD"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    DELETED = "DELETED"


class Currency(str, enum.Enum):
    TON = "TON"
    UZS = "UZS"


class User(Base):
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    full_name: Mapped[str] = mapped_column(String(128))
    invited_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    referral_count: Mapped[int] = mapped_column(Integer, default=0)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class NFT(Base):
    __tablename__ = "nfts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    seller_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id"))
    nft_link: Mapped[str] = mapped_column(Text)
    price: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    currency: Mapped[Currency] = mapped_column(Enum(Currency))
    status: Mapped[NFTStatus] = mapped_column(Enum(NFTStatus), default=NFTStatus.PENDING)
    clicks: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_ad_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    seller: Mapped["User"] = relationship("User")
    ads: Mapped[list["AdLog"]] = relationship("AdLog", back_populates="nft", cascade="all, delete-orphan")


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nft_id: Mapped[int] = mapped_column(Integer, ForeignKey("nfts.id"))
    seller_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id"))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    currency: Mapped[Currency] = mapped_column(Enum(Currency))
    commission: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    seller_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AdLog(Base):
    __tablename__ = "ad_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nft_id: Mapped[int] = mapped_column(Integer, ForeignKey("nfts.id"))
    group_id: Mapped[int] = mapped_column(BigInteger)
    message_id: Mapped[int] = mapped_column(BigInteger)
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    nft: Mapped["NFT"] = relationship("NFT", back_populates="ads")


class Group(Base):
    __tablename__ = "chat_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    title: Mapped[str] = mapped_column(String(256))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    added_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ListingMessage(Base):
    __tablename__ = "listing_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(BigInteger)
    message_id: Mapped[int] = mapped_column(BigInteger)
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
