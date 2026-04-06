"""Weather data endpoints."""

from __future__ import annotations

from datetime import date as date_type, datetime

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/weather")
async def get_weather(
    request: Request,
    date: str = Query(..., description="Date in YYYY-MM-DD format"),
) -> dict:
    try:
        date_type.fromisoformat(date)
    except ValueError:
        return JSONResponse({"error": "Invalid date format, expected YYYY-MM-DD"}, status_code=400)
    db = request.app.state.db
    summary = db.get_weather_summary(date)
    intervals = db.get_weather_intervals(date)

    summary_dict = None
    if summary:
        summary_dict = {
            "conditions": summary["conditions"],
            "temp_high": summary["temp_high"],
            "temp_low": summary["temp_low"],
            "humidity": summary["humidity"],
            "wind_speed": summary["wind_speed"],
            "precipitation": summary["precipitation"],
            "cloud_cover": summary["cloud_cover"],
        }

    interval_list = []
    for iv in intervals:
        m = iv["minute"]
        interval_list.append({
            "minute": m,
            "time": f"{m // 60:02d}:{m % 60:02d}",
            "temperature": iv["temperature"],
            "conditions": iv["conditions"],
            "humidity": iv["humidity"],
            "wind_speed": iv["wind_speed"],
            "precipitation": iv["precipitation"],
            "cloud_cover": iv["cloud_cover"],
        })

    return {
        "date": date,
        "summary": summary_dict,
        "intervals": interval_list,
    }


@router.get("/weather/for-capture")
async def get_weather_for_capture(
    request: Request,
    captured_at: str = Query(..., description="Capture timestamp in ISO format"),
) -> dict | None:
    db = request.app.state.db
    try:
        dt = datetime.fromisoformat(captured_at)
        day = dt.date().isoformat()
        minute = dt.hour * 60 + dt.minute
    except ValueError:
        return JSONResponse({"error": "Invalid timestamp format, expected ISO 8601"}, status_code=400)

    reading = db.get_weather_for_time(day, minute)
    if reading is None:
        return None

    return {
        "temperature": reading["temperature"],
        "conditions": reading["conditions"],
        "humidity": reading["humidity"],
        "wind_speed": reading["wind_speed"],
        "precipitation": reading["precipitation"],
        "cloud_cover": reading["cloud_cover"],
    }
