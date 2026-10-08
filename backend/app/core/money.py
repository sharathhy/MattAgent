"""MAIN RULE (owner's instruction): money only ever flows IN, to the owner's own UPI account.

MATT never holds funds and has no code path that sends, transfers, withdraws, refunds or debits
money. Customers pay the owner directly through a UPI payment request (link and QR addressed
to ``MATT_UPI_ID``). MATT cannot see the owner's PhonePe account, so a payment counts as revenue
only after the owner confirms it arrived. This sits above the approval gates: an outbound money
request is refused outright, even if someone would approve it.
"""

import re

from app.services.errors import ServiceError

DIRECTION = "receive_only"

_MONEY = r"(?:money|funds?|cash|₹|rs\.?|inr|rupees?|amount|payment|upi|salary|fees?)"
_ALWAYS_OUT = re.compile(
    r"\b(?:payouts?|pay\s*out|withdraw(?:al|s)?|debit(?:ed|s)?|refund(?:ed|s)?|chargeback)\b", re.I
)
_SEND_MONEY = re.compile(
    rf"\b(?:send|transfer|wire|remit|pay|move|disburse)\b(?:\s+\S+){{0,4}}?\s+{_MONEY}\b", re.I
)
#: Asking a customer for money is inbound ("send a payment request", "send the invoice").
_INBOUND = re.compile(r"\b(?:invoice|request|collect|receiv\w*|link|qr|bill)\b", re.I)
REFUSAL = (
    "Main rule: MATT only receives money, into your own UPI account. It never sends, transfers, "
    "withdraws, refunds or debits money, so it won't do that."
)


class OutboundMoneyBlocked(ServiceError):
    """Raised for any request that would move money out."""

    status_code = 403


def is_outbound(text: str) -> bool:
    if _ALWAYS_OUT.search(text):
        return True
    return bool(_SEND_MONEY.search(text)) and not _INBOUND.search(text)


def refuse_outbound(text: str) -> None:
    if is_outbound(text):
        raise OutboundMoneyBlocked(REFUSAL)
