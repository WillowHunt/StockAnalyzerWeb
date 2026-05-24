from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from database.connection import init_db
from api.stocks import router as stocks_router
from api.analysis import router as analysis_router
from api.news import router as news_router
from api.web import router as web_router
from api.compare import router as compare_router
from api.market import router as market_router

app = FastAPI(title="Stock Analyzer", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.on_event("startup")
def startup():
    init_db()


app.include_router(web_router)
app.include_router(stocks_router)
app.include_router(analysis_router)
app.include_router(news_router)
app.include_router(compare_router)
app.include_router(market_router)
