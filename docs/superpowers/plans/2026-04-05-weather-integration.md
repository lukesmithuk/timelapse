# Weather Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Associate Open-Meteo weather data with timelapse captures — 15-minute intervals + daily summaries, stored in SQLite, displayed as toggleable overlays in the web UI, filterable by conditions.

**Architecture:** New `weather.py` module fetches from Open-Meteo API using `urllib.request` (no new deps). Capture service fetches hourly. CLI backfills historical data. FastAPI endpoints serve weather for the Vue frontend. Weather toggle persisted in localStorage.

**Tech Stack:** Open-Meteo API, urllib.request, SQLite, FastAPI, Vue 3

---

## File Structure

```
src/timelapse/
├── weather.py              # NEW: Open-Meteo fetcher, WMO mapping, storage, backfill
├── jobs.py                 # MODIFY: add weather table + DB methods
├── service.py              # MODIFY: hourly weather fetch in main loop
├── cli.py                  # MODIFY: add backfill-weather command
└── web/
    ├── app.py              # MODIFY: register weather router
    └── routes/
        ├── weather.py      # NEW: /api/weather endpoints
        └── captures.py     # MODIFY: add conditions filter

frontend/src/
├── api.js                  # MODIFY: add weather API methods
├── components/
│   ├── WeatherBadge.vue    # NEW: icon + temp badge
│   ├── WeatherDetail.vue   # NEW: expanded weather card
│   └── ImageViewer.vue     # MODIFY: show weather detail
└── views/
    ├── Gallery.vue         # MODIFY: weather toggle, badges, condition filter
    └── Compare.vue         # MODIFY: weather badges

tests/
├── test_weather.py         # NEW: weather module tests
└── test_web_weather.py     # NEW: API endpoint tests
```

---

### Task 1: Weather Module + DB Schema

**Files:**
- Create: `src/timelapse/weather.py`
- Modify: `src/timelapse/jobs.py`
- Create: `tests/test_weather.py`

The weather module handles Open-Meteo API calls, WMO code mapping, and DB storage. The DB gets a new `weather` table and query methods.

- [ ] **Step 1: Add weather table to DB schema**

In `src/timelapse/jobs.py`, append to the `_SCHEMA` string (before the closing `"""`):

```sql
CREATE TABLE IF NOT EXISTS weather (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    date          TEXT NOT NULL,
    minute        INTEGER,
    temperature   REAL,
    conditions    TEXT,
    humidity      INTEGER,
    wind_speed    REAL,
    precipitation REAL,
    cloud_cover   INTEGER,
    temp_high     REAL,
    temp_low      REAL,
    fetched_at    TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_weather_date_minute
    ON weather(date, minute);
```

- [ ] **Step 2: Add weather DB methods to jobs.py**

Add these methods to the `Database` class:

```python
# --- Weather ---

def store_weather_reading(
    self, date: str, minute: Optional[int],
    temperature: Optional[float] = None, conditions: Optional[str] = None,
    humidity: Optional[int] = None, wind_speed: Optional[float] = None,
    precipitation: Optional[float] = None, cloud_cover: Optional[int] = None,
    temp_high: Optional[float] = None, temp_low: Optional[float] = None,
) -> None:
    self._conn.execute(
        """INSERT OR REPLACE INTO weather
           (date, minute, temperature, conditions, humidity, wind_speed,
            precipitation, cloud_cover, temp_high, temp_low, fetched_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (date, minute, temperature, conditions, humidity, wind_speed,
         precipitation, cloud_cover, temp_high, temp_low,
         datetime.now().isoformat()),
    )
    self._conn.commit()

def get_weather_summary(self, date: str) -> Optional[sqlite3.Row]:
    return self._conn.execute(
        "SELECT * FROM weather WHERE date = ? AND minute IS NULL",
        (date,),
    ).fetchone()

def get_weather_intervals(self, date: str) -> list[sqlite3.Row]:
    return self._conn.execute(
        "SELECT * FROM weather WHERE date = ? AND minute IS NOT NULL ORDER BY minute",
        (date,),
    ).fetchall()

def get_weather_for_time(self, date: str, minute: int) -> Optional[sqlite3.Row]:
    return self._conn.execute(
        """SELECT * FROM weather
           WHERE date = ? AND minute IS NOT NULL
           ORDER BY ABS(minute - ?)
           LIMIT 1""",
        (date, minute),
    ).fetchone()

def has_weather(self, date: str) -> bool:
    row = self._conn.execute(
        "SELECT COUNT(*) FROM weather WHERE date = ?",
        (date,),
    ).fetchone()
    return row[0] > 0
```

- [ ] **Step 3: Write failing tests for weather module**

Create `tests/test_weather.py`:

```python
import json
from datetime import date
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from timelapse.jobs import Database
from timelapse.weather import (
    WMO_CODES,
    parse_weather_response,
    store_weather,
    fetch_weather,
)


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "test.db")


SAMPLE_API_RESPONSE = {
    "minutely_15": {
        "time": ["2026-04-05T00:00", "2026-04-05T00:15", "2026-04-05T00:30"],
        "temperature_2m": [9.1, 8.8, 8.5],
        "relative_humidity_2m": [82, 83, 84],
        "precipitation": [0.0, 0.0, 0.0],
        "weather_code": [0, 0, 1],
        "wind_speed_10m": [8.5, 7.2, 6.8],
        "cloud_cover": [12, 15, 20],
    },
    "daily": {
        "time": ["2026-04-05"],
        "temperature_2m_max": [18.2],
        "temperature_2m_min": [8.1],
        "weather_code": [2],
    },
}


class TestWMOCodes:
    def test_known_code(self):
        assert WMO_CODES[0] == "Clear sky"
        assert WMO_CODES[61] == "Light rain"
        assert WMO_CODES[95] == "Thunderstorm"

    def test_unknown_code_returns_unknown(self):
        assert WMO_CODES.get(999, "Unknown") == "Unknown"


class TestParseWeatherResponse:
    def test_parses_intervals(self):
        data = parse_weather_response(SAMPLE_API_RESPONSE)
        assert len(data["intervals"]) == 3
        assert data["intervals"][0]["minute"] == 0
        assert data["intervals"][0]["temperature"] == 9.1
        assert data["intervals"][0]["conditions"] == "Clear sky"
        assert data["intervals"][1]["minute"] == 15

    def test_parses_daily_summary(self):
        data = parse_weather_response(SAMPLE_API_RESPONSE)
        assert data["summary"]["temp_high"] == 18.2
        assert data["summary"]["temp_low"] == 8.1
        assert data["summary"]["conditions"] == "Partly cloudy"


class TestStoreWeather:
    def test_stores_and_retrieves(self, db):
        data = parse_weather_response(SAMPLE_API_RESPONSE)
        store_weather(db, "2026-04-05", data)

        summary = db.get_weather_summary("2026-04-05")
        assert summary is not None
        assert summary["temp_high"] == 18.2

        intervals = db.get_weather_intervals("2026-04-05")
        assert len(intervals) == 3

    def test_has_weather(self, db):
        assert db.has_weather("2026-04-05") is False
        data = parse_weather_response(SAMPLE_API_RESPONSE)
        store_weather(db, "2026-04-05", data)
        assert db.has_weather("2026-04-05") is True

    def test_get_weather_for_time(self, db):
        data = parse_weather_response(SAMPLE_API_RESPONSE)
        store_weather(db, "2026-04-05", data)

        reading = db.get_weather_for_time("2026-04-05", 10)
        assert reading is not None
        assert reading["minute"] == 15  # closest to 10 is 15

    def test_get_weather_for_time_exact(self, db):
        data = parse_weather_response(SAMPLE_API_RESPONSE)
        store_weather(db, "2026-04-05", data)

        reading = db.get_weather_for_time("2026-04-05", 0)
        assert reading["minute"] == 0
        assert reading["temperature"] == 9.1


class TestFetchWeather:
    @patch("timelapse.weather.urlopen")
    def test_fetch_returns_parsed_data(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(SAMPLE_API_RESPONSE).encode()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        result = fetch_weather(51.5, -0.1, "2026-04-05")
        assert result is not None
        assert len(result["intervals"]) == 3

    @patch("timelapse.weather.urlopen", side_effect=Exception("network error"))
    def test_fetch_returns_none_on_error(self, mock_urlopen):
        result = fetch_weather(51.5, -0.1, "2026-04-05")
        assert result is None
```

- [ ] **Step 4: Run tests to verify they fail**

```bash
source .venv/bin/activate && pytest tests/test_weather.py -v
```

Expected: ImportError — `timelapse.weather` does not exist yet.

- [ ] **Step 5: Implement weather.py**

Create `src/timelapse/weather.py`:

```python
"""Open-Meteo weather data fetcher and storage."""

from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime
from typing import Optional
from urllib.request import urlopen, Request

log = logging.getLogger(__name__)

WMO_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Depositing rime fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    61: "Light rain", 63: "Moderate rain", 65: "Heavy rain",
    71: "Light snow", 73: "Moderate snow", 75: "Heavy snow",
    80: "Light rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
    95: "Thunderstorm", 96: "Thunderstorm with light hail", 99: "Thunderstorm with heavy hail",
}

_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

_PARAMS = (
    "minutely_15=temperature_2m,relative_humidity_2m,precipitation,weather_code,wind_speed_10m,cloud_cover"
    "&daily=temperature_2m_max,temperature_2m_min,weather_code"
    "&timezone=auto"
)


def _time_to_minute(time_str: str) -> int:
    """Convert 'HH:MM' or ISO time to minutes since midnight."""
    parts = time_str.split("T")[-1].split(":")
    return int(parts[0]) * 60 + int(parts[1])


def parse_weather_response(data: dict) -> dict:
    """Parse an Open-Meteo API response into our storage format."""
    intervals = []
    m15 = data.get("minutely_15", {})
    times = m15.get("time", [])
    for i, t in enumerate(times):
        minute = _time_to_minute(t)
        code = m15.get("weather_code", [None])[i]
        intervals.append({
            "minute": minute,
            "temperature": m15.get("temperature_2m", [None])[i],
            "conditions": WMO_CODES.get(code, "Unknown") if code is not None else None,
            "humidity": m15.get("relative_humidity_2m", [None])[i],
            "wind_speed": m15.get("wind_speed_10m", [None])[i],
            "precipitation": m15.get("precipitation", [None])[i],
            "cloud_cover": m15.get("cloud_cover", [None])[i],
        })

    daily = data.get("daily", {})
    daily_code = daily.get("weather_code", [None])[0] if daily.get("weather_code") else None
    summary = {
        "temp_high": daily.get("temperature_2m_max", [None])[0] if daily.get("temperature_2m_max") else None,
        "temp_low": daily.get("temperature_2m_min", [None])[0] if daily.get("temperature_2m_min") else None,
        "conditions": WMO_CODES.get(daily_code, "Unknown") if daily_code is not None else None,
    }

    return {"summary": summary, "intervals": intervals}


def fetch_weather(latitude: float, longitude: float, day: str, historical: bool = False) -> Optional[dict]:
    """Fetch weather from Open-Meteo for a single date. Returns None on error."""
    base = _ARCHIVE_URL if historical else _FORECAST_URL
    url = f"{base}?latitude={latitude}&longitude={longitude}&start_date={day}&end_date={day}&{_PARAMS}"
    try:
        req = Request(url, headers={"User-Agent": "timelapse/1.0"})
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        return parse_weather_response(data)
    except Exception:
        log.exception("Failed to fetch weather for %s", day)
        return None


def store_weather(db, day: str, weather_data: dict) -> None:
    """Write parsed weather data to the database."""
    summary = weather_data["summary"]
    db.store_weather_reading(
        date=day, minute=None,
        conditions=summary.get("conditions"),
        temp_high=summary.get("temp_high"),
        temp_low=summary.get("temp_low"),
    )
    for iv in weather_data["intervals"]:
        db.store_weather_reading(
            date=day, minute=iv["minute"],
            temperature=iv.get("temperature"),
            conditions=iv.get("conditions"),
            humidity=iv.get("humidity"),
            wind_speed=iv.get("wind_speed"),
            precipitation=iv.get("precipitation"),
            cloud_cover=iv.get("cloud_cover"),
        )


def backfill_weather(db, latitude: float, longitude: float, date_from: date, date_to: date) -> int:
    """Fetch historical weather for a date range. Returns count of days fetched."""
    count = 0
    current = date_from
    while current <= date_to:
        day_str = current.isoformat()
        if not db.has_weather(day_str):
            data = fetch_weather(latitude, longitude, day_str, historical=True)
            if data:
                store_weather(db, day_str, data)
                summary = data["summary"]
                log.info("Fetched weather for %s (%s, %s°C)",
                         day_str, summary.get("conditions", "?"),
                         summary.get("temp_high", "?"))
                count += 1
            time.sleep(0.5)  # rate limiting
        current = date(current.year, current.month, current.day + 1) if current.day < 28 else _next_day(current)
    return count


def _next_day(d: date) -> date:
    """Safe next-day calculation."""
    from datetime import timedelta
    return d + timedelta(days=1)
```

- [ ] **Step 6: Run tests**

```bash
source .venv/bin/activate && pytest tests/test_weather.py -v
```

Expected: All pass.

- [ ] **Step 7: Also run existing tests**

```bash
pytest tests/ -q
```

Expected: All existing tests still pass.

- [ ] **Step 8: Commit**

```bash
git add src/timelapse/weather.py src/timelapse/jobs.py tests/test_weather.py
git commit -m "feat: weather module with Open-Meteo fetcher, DB schema, and storage"
```

---

### Task 2: Capture Service Integration + CLI Backfill

**Files:**
- Modify: `src/timelapse/service.py`
- Modify: `src/timelapse/cli.py`

- [ ] **Step 1: Add hourly weather fetch to service.py**

In `service.py`, add import at the top:

```python
from timelapse.weather import fetch_weather, store_weather
```

In the `__init__` method, add:

```python
self._last_weather_fetch = 0.0  # monotonic time
```

In the main `while not self._stop` loop, after the heartbeat section, add:

```python
# Fetch weather hourly
if time.monotonic() - self._last_weather_fetch >= 3600:
    try:
        loc = self.config.location
        today_str = today.isoformat()
        data = fetch_weather(loc.latitude, loc.longitude, today_str)
        if data:
            store_weather(self.db, today_str, data)
            log.info("Weather updated for %s", today_str)
    except Exception:
        log.exception("Weather fetch failed")
    self._last_weather_fetch = time.monotonic()
```

- [ ] **Step 2: Add backfill-weather CLI command**

In `src/timelapse/cli.py`, add:

```python
@main.command("backfill-weather")
@click.option("--config", "config_path", required=True, type=click.Path(exists=False), help="Path to config file")
@click.option("--from", "date_from", required=True, type=click.DateTime(formats=["%Y-%m-%d"]), help="Start date")
@click.option("--to", "date_to", type=click.DateTime(formats=["%Y-%m-%d"]), default=None, help="End date (default: yesterday)")
def backfill_weather_cmd(config_path: str, date_from, date_to) -> None:
    """Backfill historical weather data from Open-Meteo."""
    from timelapse.jobs import Database
    from timelapse.weather import backfill_weather

    try:
        cfg = load_config(Path(config_path))
    except ConfigError as e:
        click.echo(f"Configuration error: {e}", err=True)
        raise SystemExit(1)

    if date_to is None:
        from datetime import timedelta
        date_to = date.today() - timedelta(days=1)
    else:
        date_to = date_to.date()

    db = Database(Path(cfg.storage.path) / "timelapse.db")
    click.echo(f"Backfilling weather from {date_from.date()} to {date_to}")
    count = backfill_weather(db, cfg.location.latitude, cfg.location.longitude, date_from.date(), date_to)
    click.echo(f"Done: fetched weather for {count} day(s)")
    db.close()
```

- [ ] **Step 3: Run tests**

```bash
source .venv/bin/activate && pytest tests/ -q
```

- [ ] **Step 4: Commit**

```bash
git add src/timelapse/service.py src/timelapse/cli.py
git commit -m "feat: hourly weather fetch in capture service and backfill CLI command"
```

---

### Task 3: Weather API Endpoints

**Files:**
- Create: `src/timelapse/web/routes/weather.py`
- Modify: `src/timelapse/web/app.py`
- Create: `tests/test_web_weather.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_web_weather.py`:

```python
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from timelapse.config import AppConfig, LocationConfig, CameraConfig, StorageConfig
from timelapse.jobs import Database
from timelapse.weather import parse_weather_response, store_weather
from timelapse.web.app import create_app

SAMPLE_API_RESPONSE = {
    "minutely_15": {
        "time": ["2026-04-05T00:00", "2026-04-05T00:15"],
        "temperature_2m": [9.1, 8.8],
        "relative_humidity_2m": [82, 83],
        "precipitation": [0.0, 0.0],
        "weather_code": [0, 1],
        "wind_speed_10m": [8.5, 7.2],
        "cloud_cover": [12, 15],
    },
    "daily": {
        "time": ["2026-04-05"],
        "temperature_2m_max": [18.2],
        "temperature_2m_min": [8.1],
        "weather_code": [2],
    },
}


@pytest.fixture
def app_config(tmp_path):
    storage_path = tmp_path / "timelapse"
    storage_path.mkdir()
    return AppConfig(
        location=LocationConfig(latitude=51.5, longitude=-0.1),
        cameras={"garden": CameraConfig(device=0)},
        storage=StorageConfig(path=str(storage_path), require_mount=False),
    )


@pytest.fixture
def db(app_config):
    return Database(Path(app_config.storage.path) / "timelapse.db")


@pytest.fixture
def app(app_config):
    return create_app(config=app_config)


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestWeatherByDate:
    @pytest.mark.asyncio
    async def test_returns_summary_and_intervals(self, client, db):
        data = parse_weather_response(SAMPLE_API_RESPONSE)
        store_weather(db, "2026-04-05", data)

        resp = await client.get("/api/weather?date=2026-04-05")
        assert resp.status_code == 200
        body = resp.json()
        assert body["summary"]["temp_high"] == 18.2
        assert len(body["intervals"]) == 2

    @pytest.mark.asyncio
    async def test_returns_empty_for_missing_date(self, client):
        resp = await client.get("/api/weather?date=2026-01-01")
        assert resp.status_code == 200
        body = resp.json()
        assert body["summary"] is None
        assert body["intervals"] == []


class TestWeatherForCapture:
    @pytest.mark.asyncio
    async def test_returns_closest_reading(self, client, db):
        data = parse_weather_response(SAMPLE_API_RESPONSE)
        store_weather(db, "2026-04-05", data)

        resp = await client.get("/api/weather/for-capture?captured_at=2026-04-05T00:10:00")
        assert resp.status_code == 200
        body = resp.json()
        assert body["temperature"] == 8.8  # closest to minute 10 is minute 15

    @pytest.mark.asyncio
    async def test_returns_null_for_missing(self, client):
        resp = await client.get("/api/weather/for-capture?captured_at=2026-01-01T12:00:00")
        assert resp.status_code == 200
        assert resp.json() is None
```

- [ ] **Step 2: Implement weather route**

Create `src/timelapse/web/routes/weather.py`:

```python
"""Weather data endpoints."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Query, Request

router = APIRouter()


@router.get("/weather")
async def get_weather(
    request: Request,
    date: str = Query(..., description="Date in YYYY-MM-DD format"),
) -> dict:
    db = request.app.state.db
    summary = db.get_weather_summary(date)
    intervals = db.get_weather_intervals(date)

    summary_dict = None
    if summary:
        summary_dict = {
            "conditions": summary["conditions"],
            "temp_high": summary["temp_high"],
            "temp_low": summary["temp_low"],
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
        return None

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
```

- [ ] **Step 3: Register weather router in app.py**

In `src/timelapse/web/app.py`, add to imports:

```python
from timelapse.web.routes import status, config as config_routes, captures, images, renders, videos, weather
```

In `create_app`, add:

```python
app.include_router(weather.router, prefix="/api")
```

- [ ] **Step 4: Run tests**

```bash
source .venv/bin/activate && pytest tests/test_web_weather.py tests/test_weather.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/timelapse/web/routes/weather.py src/timelapse/web/app.py tests/test_web_weather.py
git commit -m "feat: weather API endpoints (by date and for capture)"
```

---

### Task 4: Frontend API Methods + Weather Components

**Files:**
- Modify: `frontend/src/api.js`
- Create: `frontend/src/components/WeatherBadge.vue`
- Create: `frontend/src/components/WeatherDetail.vue`

**NOTE:** Use the frontend-design skill for the WeatherBadge and WeatherDetail components.

- [ ] **Step 1: Add weather methods to api.js**

Add to the `api` export object in `frontend/src/api.js`:

```js
getWeather: (params) => get('/weather', params),
getWeatherForCapture: (params) => get('/weather/for-capture', params),
```

- [ ] **Step 2: Create WeatherBadge.vue**

Use frontend-design skill. Small inline badge showing weather icon + temperature. Props: `conditions` (string), `temperature` (number). Map conditions to emoji icons:
- Clear sky / Mainly clear → ☀️
- Partly cloudy → ⛅
- Overcast / Fog → ☁️
- Rain / Drizzle / Showers → 🌧️
- Snow → ❄️
- Thunderstorm → ⛈️

Dark theme, compact, ~24px height.

- [ ] **Step 3: Create WeatherDetail.vue**

Use frontend-design skill. Expanded weather card. Props: `weather` (object with temperature, conditions, humidity, wind_speed, precipitation, cloud_cover). Shows all fields in a compact grid layout. Dark theme matching the app.

- [ ] **Step 4: Build and test**

```bash
cd frontend && npm run build && npm test && cd ..
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api.js frontend/src/components/WeatherBadge.vue frontend/src/components/WeatherDetail.vue
git commit -m "feat: weather API client methods and WeatherBadge/WeatherDetail components"
```

---

### Task 5: Gallery Weather Toggle + Badges

**Files:**
- Modify: `frontend/src/views/Gallery.vue`

- [ ] **Step 1: Add weather toggle and badges to Gallery**

Add to Gallery.vue:
- `showWeather` ref persisted to localStorage
- Toggle switch in the toolbar (next to the sort button)
- When toggled on, fetch weather for the current date via `api.getWeather({ date })`
- Show WeatherBadge on each thumbnail (using the daily summary conditions + temp_high)
- Add condition filter dropdown (All, Clear, Cloudy, Rain, etc.) visible when weather is on

The condition filter should filter the captures client-side by matching the daily summary conditions.

- [ ] **Step 2: Build and test**

```bash
cd frontend && npm run build && npm test && cd ..
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/Gallery.vue
git commit -m "feat: gallery weather toggle, badges, and condition filter"
```

---

### Task 6: ImageViewer Weather Detail

**Files:**
- Modify: `frontend/src/components/ImageViewer.vue`

- [ ] **Step 1: Add weather detail to lightbox**

Read localStorage `timelapse-show-weather`. When true:
- Fetch weather for the current capture via `api.getWeatherForCapture({ captured_at })`
- Show WeatherDetail below the camera name and timestamp in the viewer info bar

- [ ] **Step 2: Build and test**

```bash
cd frontend && npm run build && npm test && cd ..
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/ImageViewer.vue
git commit -m "feat: weather detail in image viewer lightbox"
```

---

### Task 7: Compare Weather Badges

**Files:**
- Modify: `frontend/src/views/Compare.vue`

- [ ] **Step 1: Add weather badges to Compare**

Read localStorage `timelapse-show-weather`. When true:
- For each selected capture, fetch weather via `api.getWeatherForCapture({ captured_at })`
- Show WeatherBadge next to each capture's info line (date + time)
- Add toggle switch in the controls section

- [ ] **Step 2: Build and test**

```bash
cd frontend && npm run build && npm test && cd ..
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/Compare.vue
git commit -m "feat: weather badges in compare view"
```

---

### Task 8: Frontend Tests + Full Integration

**Files:**
- Modify: `frontend/src/__tests__/components.test.js`

- [ ] **Step 1: Add WeatherBadge and WeatherDetail tests**

```js
import WeatherBadge from '../components/WeatherBadge.vue'
import WeatherDetail from '../components/WeatherDetail.vue'

describe('WeatherBadge', () => {
  it('renders conditions and temperature', () => {
    const wrapper = mount(WeatherBadge, {
      props: { conditions: 'Clear sky', temperature: 18.2 },
    })
    expect(wrapper.text()).toContain('18')
    expect(wrapper.text()).toContain('°C')
  })

  it('shows sun icon for clear sky', () => {
    const wrapper = mount(WeatherBadge, {
      props: { conditions: 'Clear sky', temperature: 20 },
    })
    expect(wrapper.text()).toContain('☀')
  })
})

describe('WeatherDetail', () => {
  it('renders all weather fields', () => {
    const wrapper = mount(WeatherDetail, {
      props: {
        weather: {
          temperature: 15.3,
          conditions: 'Partly cloudy',
          humidity: 65,
          wind_speed: 12.1,
          precipitation: 0.0,
          cloud_cover: 45,
        },
      },
    })
    expect(wrapper.text()).toContain('15.3')
    expect(wrapper.text()).toContain('Partly cloudy')
    expect(wrapper.text()).toContain('65')
  })
})
```

- [ ] **Step 2: Run all tests**

```bash
cd frontend && npm test && cd ..
source .venv/bin/activate && pytest tests/ -q
```

- [ ] **Step 3: Build final production build**

```bash
cd frontend && npm run build && cd ..
sudo systemctl restart timelapse-web
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/__tests__/components.test.js
git commit -m "test: weather component tests"
```

---

## Summary

| Task | Component | Key Files |
|------|-----------|-----------|
| 1 | Weather module + DB schema | `weather.py`, `jobs.py`, `test_weather.py` |
| 2 | Service integration + CLI backfill | `service.py`, `cli.py` |
| 3 | Weather API endpoints | `web/routes/weather.py`, `test_web_weather.py` |
| 4 | Frontend API + components | `api.js`, `WeatherBadge.vue`, `WeatherDetail.vue` |
| 5 | Gallery weather toggle | `Gallery.vue` |
| 6 | ImageViewer weather detail | `ImageViewer.vue` |
| 7 | Compare weather badges | `Compare.vue` |
| 8 | Frontend tests + integration | `components.test.js` |

Tasks 1-3 are backend (Python, testable with pytest). Task 4 creates frontend components (use frontend-design skill). Tasks 5-7 integrate weather into existing views. Task 8 adds tests and does final integration.
