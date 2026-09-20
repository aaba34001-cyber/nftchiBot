import html
from decimal import Decimal
from database import utcnow


def fmt_price(price, currency: str) -> str:
    p = Decimal(str(price))
    if currency == "UZS":
        return f"{p:,.0f}".replace(",", " ")
    s = f"{p:f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


def time_left(expires_at) -> str:
    if not expires_at:
        return "—"
    diff = expires_at - utcnow()
    if diff.total_seconds() <= 0:
        return "Muddati tugadi"
    return f"{diff.days} kun {diff.seconds // 3600} soat"


def esc(s) -> str:
    return html.escape(str(s or ""))


def commission_pct() -> str:
    from config import config
    return f"{(config.COMMISSION_RATE * 100).normalize():f}"
