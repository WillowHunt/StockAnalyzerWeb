import datetime
from fastapi import APIRouter, Query
from data.fetcher import fetch_market_regime

router = APIRouter(prefix="/api", tags=["market"])


@router.get("/regime")
def get_regime(
    index: str = Query("^GSPC"),
    start: str = Query(...),
    end: str = Query(...),
):
    start_date = datetime.date.fromisoformat(start)
    end_date   = datetime.date.fromisoformat(end)
    regime     = fetch_market_regime(index, start_date, end_date)
    if not regime:
        return []

    sorted_dates = sorted(regime.keys())
    segments  = []
    seg_start = sorted_dates[0]
    seg_bull  = regime[sorted_dates[0]]

    for i in range(1, len(sorted_dates)):
        d = sorted_dates[i]
        if regime[d] != seg_bull:
            segments.append({"start": str(seg_start), "end": str(sorted_dates[i - 1]), "is_bull": seg_bull})
            seg_start = d
            seg_bull  = regime[d]

    segments.append({"start": str(seg_start), "end": str(sorted_dates[-1]), "is_bull": seg_bull})
    return segments
