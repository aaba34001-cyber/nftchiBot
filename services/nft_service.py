from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from database import NFT, NFTStatus, Transaction, Currency, User, utcnow
from config import config


class NFTService:
    @staticmethod
    def day_start_utc() -> datetime:
        tz = ZoneInfo(config.TIMEZONE)
        now_local = datetime.now(tz)
        start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        return start_local.astimezone(timezone.utc).replace(tzinfo=None)

    @staticmethod
    async def get_limits(session: AsyncSession, user_id: int) -> dict:
        user = await session.get(User, user_id)
        refs = user.referral_count if user else 0
        bonus = refs * config.REFERRAL_BONUS
        active = (await session.execute(
            select(func.count()).select_from(NFT).where(
                NFT.seller_id == user_id,
                NFT.status.in_([NFTStatus.PENDING, NFTStatus.ACTIVE]),
            )
        )).scalar_one()
        today = (await session.execute(
            select(func.count()).select_from(NFT).where(
                NFT.seller_id == user_id,
                NFT.created_at >= NFTService.day_start_utc(),
            )
        )).scalar_one()
        return {
            "active": active,
            "max_active": config.BASE_MAX_ACTIVE + bonus,
            "today": today,
            "daily": config.BASE_DAILY_LIMIT + bonus,
            "referrals": refs,
        }

    @staticmethod
    async def check_can_post(session: AsyncSession, user_id: int) -> str | None:
        if not config.LIMITS_ENABLED:
            return None
        lim = await NFTService.get_limits(session, user_id)
        if lim["active"] >= lim["max_active"]:
            return (
                f"❌ Sizda {lim['active']}/{lim['max_active']} ta faol NFT bor.\n"
                "Muddati tugagach yoki sotilgach yangisini qo'ya olasiz.\n"
                "Yoki do'st taklif qiling: har bir do'st limitni oshiradi (👥 Do'st taklif qilish)."
            )
        if lim["today"] >= lim["daily"]:
            return (
                f"❌ Bugungi limit tugadi ({lim['today']}/{lim['daily']}).\n"
                "Ertaga qayta urinib ko'ring yoki do'st taklif qiling (👥 Do'st taklif qilish)."
            )
        return None

    @staticmethod
    async def create_nft(session: AsyncSession, seller_id: int, nft_link: str, price: Decimal, currency: Currency) -> NFT:
        nft = NFT(
            seller_id=seller_id,
            nft_link=nft_link,
            price=price,
            currency=currency,
            status=NFTStatus.PENDING,
        )
        session.add(nft)
        await session.commit()
        await session.refresh(nft)
        return nft

    @staticmethod
    async def mark_sold(session: AsyncSession, nft: NFT) -> Transaction:
        total = Decimal(str(nft.price))
        commission = (total * config.COMMISSION_RATE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        nft.status = NFTStatus.SOLD
        tx = Transaction(
            nft_id=nft.id,
            seller_id=nft.seller_id,
            amount=total,
            currency=nft.currency,
            commission=commission,
            seller_amount=total - commission,
        )
        session.add(tx)
        await session.commit()
        await session.refresh(tx)
        return tx

    @staticmethod
    async def get_commission_stats(session: AsyncSession):
        today_start = NFTService.day_start_utc()
        now_local = datetime.now(ZoneInfo(config.TIMEZONE))
        week_start = today_start - timedelta(days=now_local.weekday())
        month_start = today_start - timedelta(days=now_local.day - 1)

        async def calc(since=None):
            stmt = select(Transaction.currency, func.sum(Transaction.commission))
            if since:
                stmt = stmt.where(Transaction.created_at >= since)
            stmt = stmt.group_by(Transaction.currency)
            res = await session.execute(stmt)
            data = {"TON": Decimal("0"), "UZS": Decimal("0")}
            for curr, val in res.all():
                if val:
                    data[curr.value] = Decimal(str(val))
            return data

        return {
            "today": await calc(today_start),
            "week": await calc(week_start),
            "month": await calc(month_start),
            "total": await calc(),
        }

    @staticmethod
    async def get_overview(session: AsyncSession):
        users = (await session.execute(select(func.count()).select_from(User))).scalar_one()
        rows = (await session.execute(select(NFT.status, func.count()).group_by(NFT.status))).all()
        by_status = {s.value: c for s, c in rows}
        vol_rows = (await session.execute(
            select(Transaction.currency, func.sum(Transaction.amount)).group_by(Transaction.currency)
        )).all()
        volume = {"TON": Decimal("0"), "UZS": Decimal("0")}
        for curr, val in vol_rows:
            if val:
                volume[curr.value] = Decimal(str(val))
        return {"users": users, "status": by_status, "volume": volume}
