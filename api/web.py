from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from data.fetcher import list_stored_tickers
from analysis.backtester import load_signal_details, run_backtest, run_atr_backtest, run_regime_analysis
from data.news import load_from_db

templates = Jinja2Templates(directory="templates")
router = APIRouter(tags=["web"])


@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    stocks = list_stored_tickers()
    return templates.TemplateResponse(request, "index.html", {"stocks": stocks})


@router.get("/view/{ticker}", response_class=HTMLResponse)
def stock_view(request: Request, ticker: str):
    return templates.TemplateResponse(
        request, "partials/stock_view.html", {"ticker": ticker.upper()}
    )


@router.get("/partials/signals/{ticker}", response_class=HTMLResponse)
def signals_partial(request: Request, ticker: str):
    signals = load_signal_details(ticker.upper())
    return templates.TemplateResponse(
        request, "partials/signals_table.html",
        {"ticker": ticker.upper(), "signals": signals},
    )


@router.get("/partials/news/{ticker}", response_class=HTMLResponse)
def news_partial(request: Request, ticker: str):
    articles = load_from_db(ticker.upper())[:100]
    return templates.TemplateResponse(
        request, "partials/news_list.html",
        {"ticker": ticker.upper(), "articles": articles},
    )


@router.get("/partials/backtest/{ticker}", response_class=HTMLResponse)
def backtest_partial(request: Request, ticker: str, hold_days: int = 20):
    summary        = run_backtest(ticker.upper(), hold_days=hold_days)
    atr_summary, _ = run_atr_backtest(ticker.upper())
    regime         = run_regime_analysis(ticker.upper(), hold_days=hold_days)
    return templates.TemplateResponse(
        request, "partials/backtest_result.html",
        {
            "ticker": ticker.upper(),
            "summary": summary,
            "atr_summary": atr_summary,
            "regime": regime,
            "hold_days": hold_days,
        },
    )
