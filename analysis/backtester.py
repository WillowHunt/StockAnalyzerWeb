import pandas as pd
from database.connection import get_session
from database.models import Stock, Signal


def generate_signals(ticker: str) -> int:
    from data.fetcher import load_prices
    df = load_prices(ticker)
    if df.empty:
        return 0

    session = get_session()
    try:
        stock = session.query(Stock).filter_by(ticker=ticker).first()
        if not stock:
            return 0

        session.query(Signal).filter_by(stock_id=stock.id).delete()

        signals = []
        signals += _macd_signals(df, stock.id)
        signals += _rsi_signals(df, stock.id)
        signals += _sma_cross_signals(df, stock.id)
        signals += _ema_cross_signals(df, stock.id)
        signals += _stoch_signals(df, stock.id)

        session.bulk_save_objects(signals)
        session.commit()
        return len(signals)
    finally:
        session.close()


def run_atr_backtest(ticker: str, atr_mult: float = 2.0, max_days: int = 60) -> tuple[dict, list]:
    session = get_session()
    try:
        stock = session.query(Stock).filter_by(ticker=ticker).first()
        if not stock:
            return {}, []

        from data.fetcher import load_prices
        prices = load_prices(ticker).set_index("date")

        buy_signals = session.query(Signal).filter_by(stock_id=stock.id, signal_type="BUY").all()
        results = []
        details = []

        for sig in buy_signals:
            if sig.date not in prices.index:
                continue
            future_dates = [d for d in prices.index if d >= sig.date]
            if len(future_dates) < 2:
                continue

            entry_price = prices.loc[sig.date, "close"]
            atr0 = prices.loc[sig.date, "atr_14"]
            if not atr0 or pd.isna(atr0):
                continue

            highest_close = entry_price
            trailing_stop = entry_price - atr_mult * atr0
            exit_price = None
            exit_date = None

            for d in future_dates[1:max_days + 1]:
                close = prices.loc[d, "close"]
                atr = prices.loc[d, "atr_14"]
                if close <= trailing_stop:
                    exit_price = close
                    exit_date = d
                    break
                if close > highest_close:
                    highest_close = close
                if atr and not pd.isna(atr):
                    trailing_stop = max(trailing_stop, highest_close - atr_mult * atr)

            if exit_price is None:
                last = future_dates[min(max_days, len(future_dates) - 1)]
                exit_price = prices.loc[last, "close"]
                exit_date = last

            pct = ((exit_price - entry_price) / entry_price) * 100
            is_success = pct > 0
            indicator_key = sig.indicator + "+ATR"

            results.append({"type": "BUY", "indicator": indicator_key, "pct": pct, "success": is_success})
            details.append({
                "date": str(sig.date),
                "signal_type": "BUY",
                "indicator": indicator_key,
                "price": entry_price,
                "outcome_date": str(exit_date),
                "outcome_pct": round(pct, 4),
                "is_success": is_success,
            })

        if not results:
            return {}, []

        df = pd.DataFrame(results)
        summary = {}
        for (stype, ind), group in df.groupby(["type", "indicator"]):
            total = len(group)
            success = group["success"].sum()
            summary[f"{stype}_{ind}"] = {
                "total": total,
                "success": int(success),
                "fail": total - int(success),
                "success_rate": round(success / total * 100, 1),
                "avg_pct": round(group["pct"].mean(), 2),
            }
        return summary, details
    finally:
        session.close()


def load_signal_details(ticker: str) -> list:
    session = get_session()
    try:
        stock = session.query(Stock).filter_by(ticker=ticker).first()
        if not stock:
            return []
        rows = session.query(Signal).filter_by(stock_id=stock.id).order_by(Signal.date).all()
        return [
            {
                "date": str(sig.date),
                "signal_type": sig.signal_type,
                "indicator": sig.indicator,
                "price": sig.price_at_signal,
                "outcome_date": str(sig.outcome_date) if sig.outcome_date else "",
                "outcome_pct": sig.outcome_pct,
                "is_success": sig.is_success,
            }
            for sig in rows
        ]
    finally:
        session.close()


def run_backtest(ticker: str, hold_days: int = 20) -> dict:
    session = get_session()
    try:
        stock = session.query(Stock).filter_by(ticker=ticker).first()
        if not stock:
            return {}

        from data.fetcher import load_prices
        prices = load_prices(ticker).set_index("date")

        raw_signals = session.query(Signal).filter_by(stock_id=stock.id).all()
        results = []
        for sig in raw_signals:
            if sig.date not in prices.index:
                continue
            future_dates = [d for d in prices.index if d > sig.date]
            if len(future_dates) < hold_days:
                continue
            outcome_date = future_dates[hold_days - 1]
            entry = prices.loc[sig.date, "close"]
            exit_ = prices.loc[outcome_date, "close"]
            pct = ((exit_ - entry) / entry) * 100
            is_success = pct > 0 if sig.signal_type == "BUY" else pct < 0

            sig.outcome_date = outcome_date
            sig.outcome_price = exit_
            sig.outcome_pct = round(pct, 4)
            sig.is_success = is_success
            results.append({"type": sig.signal_type, "indicator": sig.indicator, "pct": pct, "success": is_success})

        session.commit()

        if not results:
            return {}

        df = pd.DataFrame(results)
        summary = {}
        for (stype, ind), group in df.groupby(["type", "indicator"]):
            total = len(group)
            success = group["success"].sum()
            summary[f"{stype}_{ind}"] = {
                "total": total,
                "success": int(success),
                "fail": total - int(success),
                "success_rate": round(success / total * 100, 1),
                "avg_pct": round(group["pct"].mean(), 2),
            }
        return summary
    finally:
        session.close()


def run_regime_analysis(ticker: str, hold_days: int = 20) -> dict:
    from data.fetcher import load_prices
    session = get_session()
    try:
        stock = session.query(Stock).filter_by(ticker=ticker).first()
        if not stock:
            return {}

        prices    = load_prices(ticker).set_index("date")
        med_atr   = prices["atr_14"].dropna().median()
        all_dates = list(prices.index)

        raw_signals = session.query(Signal).filter_by(stock_id=stock.id).all()
        rows = []
        for sig in raw_signals:
            if sig.date not in prices.index:
                continue
            future = [d for d in all_dates if d > sig.date]
            if len(future) < hold_days:
                continue

            p     = prices.loc[sig.date]
            entry = p["close"]
            exit_ = prices.loc[future[hold_days - 1], "close"]
            pct   = (exit_ - entry) / entry * 100
            ok    = pct > 0 if sig.signal_type == "BUY" else pct < 0

            sma200 = p.get("sma_200")
            atr    = p.get("atr_14")
            regime = "Bull" if (sma200 and not pd.isna(sma200) and entry > sma200) else "Bear"
            vol    = "Høj"  if (atr    and not pd.isna(atr)    and atr > med_atr)  else "Lav"

            rows.append({
                "indicator": sig.indicator, "signal_type": sig.signal_type,
                "pct": pct, "success": ok, "regime": regime, "volatility": vol,
            })

        if not rows:
            return {}

        df2 = pd.DataFrame(rows)

        def _summarise(df_grp, group_col):
            out = []
            for (ind, stype, ctx), grp in df_grp.groupby(["indicator", "signal_type", group_col]):
                n = len(grp); s = int(grp["success"].sum())
                out.append({
                    "indicator": ind, "signal_type": stype, group_col: ctx,
                    "total": n, "success": s, "fail": n - s,
                    "success_rate": round(s / n * 100, 1),
                    "avg_pct": round(grp["pct"].mean(), 2),
                })
            return sorted(out, key=lambda r: (r["signal_type"], r["indicator"], r[group_col]))

        return {
            "regime":     _summarise(df2, "regime"),
            "volatility": _summarise(df2, "volatility"),
        }
    finally:
        session.close()


def _macd_signals(df: pd.DataFrame, stock_id: int) -> list:
    signals = []
    prev_hist = None
    for _, row in df.iterrows():
        hist = row.get("macd_hist")
        if prev_hist is not None and hist is not None and not pd.isna(hist):
            if prev_hist < 0 < hist:
                signals.append(Signal(stock_id=stock_id, date=row["date"], signal_type="BUY",
                                      indicator="MACD", price_at_signal=row["close"]))
            elif prev_hist > 0 > hist:
                signals.append(Signal(stock_id=stock_id, date=row["date"], signal_type="SELL",
                                      indicator="MACD", price_at_signal=row["close"]))
        prev_hist = hist
    return signals


def _rsi_signals(df: pd.DataFrame, stock_id: int) -> list:
    signals = []
    prev_rsi = None
    for _, row in df.iterrows():
        rsi = row.get("rsi_14")
        if prev_rsi is not None and rsi is not None and not pd.isna(rsi):
            if prev_rsi < 30 and rsi >= 30:
                signals.append(Signal(stock_id=stock_id, date=row["date"], signal_type="BUY",
                                      indicator="RSI", price_at_signal=row["close"]))
            elif prev_rsi > 70 and rsi <= 70:
                signals.append(Signal(stock_id=stock_id, date=row["date"], signal_type="SELL",
                                      indicator="RSI", price_at_signal=row["close"]))
        prev_rsi = rsi
    return signals


def _stoch_signals(df: pd.DataFrame, stock_id: int) -> list:
    signals = []
    prev_row = None
    for _, row in df.iterrows():
        if prev_row is not None:
            k, d = row.get("stoch_k"), row.get("stoch_d")
            pk, pd_ = prev_row.get("stoch_k"), prev_row.get("stoch_d")
            if None not in (k, d, pk, pd_) and not any(pd.isna(x) for x in [k, d, pk, pd_]):
                if pk < pd_ and k >= d and k < 20:
                    signals.append(Signal(stock_id=stock_id, date=row["date"], signal_type="BUY",
                                          indicator="STOCH", price_at_signal=row["close"]))
                elif pk > pd_ and k <= d and k > 80:
                    signals.append(Signal(stock_id=stock_id, date=row["date"], signal_type="SELL",
                                          indicator="STOCH", price_at_signal=row["close"]))
        prev_row = row
    return signals


def _ema_cross_signals(df: pd.DataFrame, stock_id: int) -> list:
    signals = []
    prev_row = None
    for _, row in df.iterrows():
        if prev_row is not None:
            e12, e26 = row.get("ema_12"), row.get("ema_26")
            pe12, pe26 = prev_row.get("ema_12"), prev_row.get("ema_26")
            if None not in (e12, e26, pe12, pe26) and not any(pd.isna(x) for x in [e12, e26, pe12, pe26]):
                if pe12 < pe26 and e12 >= e26:
                    signals.append(Signal(stock_id=stock_id, date=row["date"], signal_type="BUY",
                                          indicator="EMA_CROSS", price_at_signal=row["close"]))
                elif pe12 > pe26 and e12 <= e26:
                    signals.append(Signal(stock_id=stock_id, date=row["date"], signal_type="SELL",
                                          indicator="EMA_CROSS", price_at_signal=row["close"]))
        prev_row = row
    return signals


def _sma_cross_signals(df: pd.DataFrame, stock_id: int) -> list:
    signals = []
    prev_row = None
    for _, row in df.iterrows():
        if prev_row is not None:
            s20, s50 = row.get("sma_20"), row.get("sma_50")
            p20, p50 = prev_row.get("sma_20"), prev_row.get("sma_50")
            if None not in (s20, s50, p20, p50) and not any(pd.isna(x) for x in [s20, s50, p20, p50]):
                if p20 < p50 and s20 >= s50:
                    signals.append(Signal(stock_id=stock_id, date=row["date"], signal_type="BUY",
                                          indicator="SMA_CROSS", price_at_signal=row["close"]))
                elif p20 > p50 and s20 <= s50:
                    signals.append(Signal(stock_id=stock_id, date=row["date"], signal_type="SELL",
                                          indicator="SMA_CROSS", price_at_signal=row["close"]))
        prev_row = row
    return signals
