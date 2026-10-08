"""Brokers. Paper is the default; Zerodha Kite Connect is the live one.

The live broker can only place and cancel intraday (MIS) cash-equity orders on NSE in the owner's
own account. Kite Connect has no API for withdrawing or transferring funds, and MATT calls none:
money can't leave the owner's demat account through MATT.

What Zerodha needs (stated in the UI too): a Kite Connect developer app (the free "Personal" plan
places orders; live quotes need the paid plan, which MATT doesn't use because it reads prices from
free feeds), and a fresh login every trading day, because Kite access tokens expire each morning.
"""

import hashlib
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Protocol

import httpx

KITE_API = "https://api.kite.trade"
KITE_LOGIN = "https://kite.zerodha.com/connect/login?v=3&api_key={api_key}"
TICK = Decimal("0.05")


class BrokerError(RuntimeError):
    pass


class Broker(Protocol):
    live: bool

    def enter(self, symbol: str, side: str, qty: int, stop: float) -> dict[str, Any]: ...

    def exit(self, symbol: str, side: str, qty: int, orders: dict[str, Any]) -> dict[str, Any]: ...


class PaperBroker:
    """Fills at the price MATT sees; nothing leaves this server."""

    live = False

    def enter(self, symbol: str, side: str, qty: int, stop: float) -> dict[str, Any]:
        return {}

    def exit(self, symbol: str, side: str, qty: int, orders: dict[str, Any]) -> dict[str, Any]:
        return {}


def tick_round(price: float) -> float:
    return float((Decimal(str(price)) / TICK).quantize(Decimal("1"), ROUND_HALF_UP) * TICK)


class KiteClient:
    def __init__(
        self, api_key: str, access_token: str | None = None, http: httpx.Client | None = None
    ) -> None:
        self.api_key, self.access_token = api_key, access_token
        self.http = http or httpx.Client(base_url=KITE_API, timeout=15)

    def _headers(self) -> dict[str, str]:
        h = {"X-Kite-Version": "3"}
        if self.access_token:
            h["Authorization"] = f"token {self.api_key}:{self.access_token}"
        return h

    def _call(self, method: str, path: str, data: dict[str, Any] | None = None) -> Any:
        try:
            r = self.http.request(method, path, data=data, headers=self._headers())
            body = r.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise BrokerError(f"Zerodha unreachable: {exc}") from exc
        if r.status_code >= 400 or body.get("status") != "success":
            raise BrokerError(str(body.get("message") or f"Zerodha error {r.status_code}"))
        return body.get("data")

    def create_session(self, request_token: str, api_secret: str) -> str:
        checksum = hashlib.sha256((self.api_key + request_token + api_secret).encode()).hexdigest()
        data = self._call(
            "POST",
            "/session/token",
            {"api_key": self.api_key, "request_token": request_token, "checksum": checksum},
        )
        self.access_token = str(data["access_token"])
        return self.access_token

    def funds(self) -> float:
        data = self._call("GET", "/user/margins/equity")
        return float((data.get("available") or {}).get("live_balance") or data.get("net") or 0)

    def place(self, symbol: str, txn: str, qty: int, *, trigger: float | None = None) -> str:
        form = {
            "tradingsymbol": symbol,
            "exchange": "NSE",
            "transaction_type": txn,
            "quantity": str(qty),
            "product": "MIS",
            "validity": "DAY",
            "order_type": "MARKET" if trigger is None else "SL-M",
        }
        if trigger is not None:
            form["trigger_price"] = f"{tick_round(trigger):.2f}"
        return str(self._call("POST", "/orders/regular", form)["order_id"])

    def cancel(self, order_id: str) -> None:
        self._call("DELETE", f"/orders/regular/{order_id}")

    def fill(self, order_id: str) -> float | None:
        history = self._call("GET", f"/orders/{order_id}") or []
        if not history:
            return None
        last = history[-1]
        if last.get("status") == "REJECTED":
            raise BrokerError(f"Order rejected: {last.get('status_message') or 'no reason given'}")
        price = last.get("average_price")
        return float(price) if price else None


class KiteBroker:
    """Live intraday orders. Each entry is paired with a stop-loss order held at Zerodha, so the
    stop protects the position even if MATT's server goes to sleep."""

    live = True

    def __init__(self, client: KiteClient) -> None:
        self.client = client

    def enter(self, symbol: str, side: str, qty: int, stop: float) -> dict[str, Any]:
        buy = side == "long"
        entry_id = self.client.place(symbol, "BUY" if buy else "SELL", qty)
        fill = self.client.fill(entry_id)
        try:
            stop_id = self.client.place(symbol, "SELL" if buy else "BUY", qty, trigger=stop)
        except BrokerError:
            # No protective stop: get straight back out rather than hold an unprotected position.
            self.client.place(symbol, "SELL" if buy else "BUY", qty)
            raise
        return {"entry_order": entry_id, "stop_order": stop_id, "fill_price": fill}

    def exit(self, symbol: str, side: str, qty: int, orders: dict[str, Any]) -> dict[str, Any]:
        stop_id = orders.get("stop_order")
        if stop_id:
            try:
                self.client.cancel(str(stop_id))
            except BrokerError:
                # Usually means the stop already filled at Zerodha: nothing left to close.
                return {"exit_order": stop_id, "fill_price": self.client.fill(str(stop_id))}
        exit_id = self.client.place(symbol, "SELL" if side == "long" else "BUY", qty)
        return {"exit_order": exit_id, "fill_price": self.client.fill(exit_id)}
