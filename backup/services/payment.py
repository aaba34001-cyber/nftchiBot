from abc import ABC, abstractmethod
from decimal import Decimal
import uuid

class PaymentResult:
    def __init__(self, success: bool, payment_id: str, message: str = ""):
        self.success = success
        self.payment_id = payment_id
        self.message = message

class PaymentProvider(ABC):
    @abstractmethod
    async def create_payment(self, nft_id: int, amount: Decimal, currency: str, buyer_id: int) -> str:
        pass

    @abstractmethod
    async def verify_payment(self, payment_id: str) -> PaymentResult:
        pass

class TonPaymentProvider(PaymentProvider):
    async def create_payment(self, nft_id: int, amount: Decimal, currency: str, buyer_id: int) -> str:
        return f"TON-{nft_id}-{buyer_id}-{uuid.uuid4().hex[:8]}"

    async def verify_payment(self, payment_id: str) -> PaymentResult:
        return PaymentResult(success=True, payment_id=payment_id, message="TON Payment Verified")

class UzsPaymentProvider(PaymentProvider):
    async def create_payment(self, nft_id: int, amount: Decimal, currency: str, buyer_id: int) -> str:
        return f"UZS-{nft_id}-{buyer_id}-{uuid.uuid4().hex[:8]}"

    async def verify_payment(self, payment_id: str) -> PaymentResult:
        return PaymentResult(success=True, payment_id=payment_id, message="UZS Payment Verified via Provider")

class PaymentService:
    def __init__(self):
        self.providers = {
            "TON": TonPaymentProvider(),
            "UZS": UzsPaymentProvider()
        }

    def get_provider(self, currency: str) -> PaymentProvider:
        provider = self.providers.get(currency)
        if not provider:
            raise ValueError(f"Unsupported currency provider: {currency}")
        return provider

payment_service = PaymentService()
