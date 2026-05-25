import yfinance as yf
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from data.fetcher import fetch_and_store, list_stored_tickers, load_prices

router = APIRouter(prefix="/api/stocks", tags=["stocks"])


@router.get("")
def get_stocks():
    rows = list_stored_tickers()
    return [{"ticker": t, "name": n, "span": s} for t, n, s in rows]


@router.post("/{ticker}/fetch")
def fetch_stock(
    ticker: str,
    period: str = Query("1y"),
    interval: str = Query("1d"),
):
    try:
        new_rows = fetch_and_store(ticker.upper(), period=period, interval=interval)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"ticker": ticker.upper(), "new_rows": new_rows}


@router.get("/{ticker}/recommendations")
def get_recommendations(ticker: str):
    try:
        t    = yf.Ticker(ticker.upper())
        info = t.info or {}
        summary = t.recommendations_summary
        if summary is not None and not summary.empty:
            row        = summary[summary["period"] == "0m"]
            row        = row.iloc[0] if not row.empty else summary.iloc[0]
            strong_buy = int(row.get("strongBuy", 0))
            buy        = int(row.get("buy", 0))
            hold       = int(row.get("hold", 0))
            sell       = int(row.get("sell", 0))
            strong_sell = int(row.get("strongSell", 0))
        else:
            strong_buy = buy = hold = sell = strong_sell = 0

        key_map = {
            "strong_buy": "Stærkt Køb", "buy": "Køb",
            "hold": "Hold",
            "sell": "Sælg", "strong_sell": "Stærkt Sælg",
        }
        consensus = key_map.get(info.get("recommendationKey", ""), "—")
        return {
            "consensus":   consensus,
            "strong_buy":  strong_buy,
            "buy":         buy,
            "hold":        hold,
            "sell":        sell,
            "strong_sell": strong_sell,
            "total":       strong_buy + buy + hold + sell + strong_sell,
        }
    except Exception:
        return {"consensus": "—", "strong_buy": 0, "buy": 0, "hold": 0, "sell": 0, "strong_sell": 0, "total": 0}


@router.get("/{ticker}/prices")
def get_prices(ticker: str, limit: int = Query(default=0, ge=0)):
    df = load_prices(ticker.upper())
    if df.empty:
        raise HTTPException(status_code=404, detail=f"{ticker} ikke fundet i databasen")
    if limit:
        df = df.tail(limit)
    df["date"] = df["date"].astype(str)
    return Response(content=df.to_json(orient="records"), media_type="application/json")
