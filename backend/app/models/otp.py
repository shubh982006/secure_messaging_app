from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UTCDateTime, new_uuid, utcnow


class OtpRequest(Base):
    """Mocked OTP challenge.

    The code is always settings.mock_otp_code, but the row is real: it expires,
    it is single use, and verify-otp checks it. Swapping in Twilio means
    replacing one function, not the flow.
    """

    __tablename__ = "otp_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    phone_number: Mapped[str] = mapped_column(String(32), index=True)
    code: Mapped[str] = mapped_column(String(8))
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    consumed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
