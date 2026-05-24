import datetime
import yfinance as yf
import pandas as pd
from database.connection import get_session
from database.models import Stock, Price
from analysis.indicators import add_indicators

_regime_cache: dict = {}


def fetch_market_regime(index_ticker: str, start_date, end_date) -> dict:
    """Hent et indeks og beregn ±20% bull/bear regime. Returnerer {date: is_bull}."""
    lookback_start = start_date - datetime.timedelta(days=365)
    cache_key = (index_ticker, lookback_start, end_date)
    if cache_key in _regime_cache:
        return _regime_cache[cache_key]

    try:
        df = yf.download(
            index_ticker,
            start=lookback_start.strftime("%Y-%m-%d"),
            end=(end_date + datetime.timedelta(days=1)).strftime("%Y-%m-%d"),
            auto_adjust=True,
            progress=False,
        )
        if df.empty:
            return {}
        df = df.reset_index()
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        closes = df["Close"].values
        dates = [d.date() if hasattr(d, "date") else d for d in df["Date"]]

        is_bull = [True] * len(closes)
        current_bull = True
        extremum = float(closes[0])
        for i in range(1, len(closes)):
            c = float(closes[i])
            if current_bull:
                if c > extremum:
                    extremum = c
                elif c <= extremum * 0.80:
                    current_bull = False
                    extremum = c
            else:
                if c < extremum:
                    extremum = c
                elif c >= extremum * 1.20:
                    current_bull = True
                    extremum = c
            is_bull[i] = current_bull

        result = dict(zip(dates, is_bull))
        _regime_cache[cache_key] = result
        return result
    except Exception:
        return {}


def fetch_and_store(ticker: str, period: str = "1y", interval: str = "1d") -> int:
    df = yf.download(ticker, period=period, interval=interval, auto_adjust=True, progress=False)
    if df.empty:
        raise ValueError(f"No data returned for {ticker}")

    df = df.reset_index()
    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    df = add_indicators(df)

    info = yf.Ticker(ticker).info
    name = info.get("longName") or info.get("shortName") or ticker
    exchange = info.get("exchange", "")
    currency = info.get("currency", "USD")

    session = get_session()
    try:
        stock = session.query(Stock).filter_by(ticker=ticker).first()
        if not stock:
            stock = Stock(ticker=ticker, name=name, exchange=exchange, currency=currency)
            session.add(stock)
            session.flush()

        existing_dates = {p.date for p in session.query(Price.date).filter_by(stock_id=stock.id)}

        new_prices = []
        for _, row in df.iterrows():
            date = row["Date"].date() if hasattr(row["Date"], "date") else row["Date"]
            if date in existing_dates:
                continue
            new_prices.append(Price(
                stock_id=stock.id,
                date=date,
                open=_f(row.get("Open")),
                high=_f(row.get("High")),
                low=_f(row.get("Low")),
                close=_f(row.get("Close")),
                volume=_f(row.get("Volume")),
                sma_20=_f(row.get("sma_20")),
                sma_50=_f(row.get("sma_50")),
                sma_200=_f(row.get("sma_200")),
                ema_12=_f(row.get("ema_12")),
                ema_26=_f(row.get("ema_26")),
                rsi_14=_f(row.get("rsi_14")),
                macd=_f(row.get("macd")),
                macd_signal=_f(row.get("macd_signal")),
                macd_hist=_f(row.get("macd_hist")),
                bb_upper=_f(row.get("bb_upper")),
                bb_middle=_f(row.get("bb_middle")),
                bb_lower=_f(row.get("bb_lower")),
                atr_14=_f(row.get("atr_14")),
                stoch_k=_f(row.get("stoch_k")),
                stoch_d=_f(row.get("stoch_d")),
            ))

        session.bulk_save_objects(new_prices)
        session.commit()
        return len(new_prices)
    finally:
        session.close()


def list_stored_tickers() -> list:
    from sqlalchemy import func
    session = get_session()
    try:
        stocks = session.query(Stock).order_by(Stock.ticker).all()
        result = []
        for s in stocks:
            row = session.query(
                func.min(Price.date), func.max(Price.date)
            ).filter_by(stock_id=s.id).one()
            min_date, max_date = row
            if min_date and max_date:
                years = (max_date - min_date).days / 365.25
                span = f"{years:.1f}y" if years >= 1 else f"{int(years * 12)}m"
            else:
                span = None
            result.append((s.ticker, s.name or s.ticker, span))
        return result
    finally:
        session.close()


def load_prices(ticker: str) -> pd.DataFrame:
    session = get_session()
    try:
        stock = session.query(Stock).filter_by(ticker=ticker).first()
        if not stock:
            return pd.DataFrame()
        rows = (session.query(Price)
                .filter_by(stock_id=stock.id)
                .filter(Price.close.isnot(None))
                .order_by(Price.date)
                .all())
        return pd.DataFrame([{
            "date": r.date, "open": r.open, "high": r.high, "low": r.low,
            "close": r.close, "volume": r.volume,
            "sma_20": r.sma_20, "sma_50": r.sma_50, "sma_200": r.sma_200,
            "ema_12": r.ema_12, "ema_26": r.ema_26,
            "rsi_14": r.rsi_14, "macd": r.macd, "macd_signal": r.macd_signal,
            "macd_hist": r.macd_hist, "bb_upper": r.bb_upper, "bb_lower": r.bb_lower,
            "atr_14": r.atr_14, "stoch_k": r.stoch_k, "stoch_d": r.stoch_d,
        } for r in rows])
    finally:
        session.close()


def _f(val):
    try:
        return float(val) if val is not None and not pd.isna(val) else None
    except Exception:
        return None
