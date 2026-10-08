"""Realistic trading costs, so paper results aren't flattered.

NSE intraday (Zerodha-style MIS): brokerage 0.03% or ₹20 per order, whichever is lower; STT
0.025% on the sell side; exchange 0.00297%; SEBI ₹10 per crore; stamp duty 0.003% on the buy
side; GST 18% on brokerage, exchange and SEBI charges. Crypto spot: 0.1% per side. (India also
withholds 1% TDS on crypto sales; it is a tax credit, not a cost, so it is not deducted here.)
"""


def nse_fees(buy_value: float, sell_value: float) -> float:
    brokerage = min(20.0, buy_value * 0.0003) + min(20.0, sell_value * 0.0003)
    exchange = (buy_value + sell_value) * 0.0000297
    sebi = (buy_value + sell_value) * 0.000001
    stt = sell_value * 0.00025
    stamp = buy_value * 0.00003
    return brokerage + exchange + sebi + stt + stamp + 0.18 * (brokerage + exchange + sebi)


def crypto_fees(buy_value: float, sell_value: float) -> float:
    return (buy_value + sell_value) * 0.001


def round_trip(market: str, entry_value: float, exit_value: float) -> float:
    fn = crypto_fees if market == "crypto" else nse_fees
    return fn(entry_value, exit_value)


def round_trip_pct(market: str) -> float:
    """Approximate round-trip cost as a fraction of trade value, for backtests."""
    return round_trip(market, 1000.0, 1000.0) / 1000.0
