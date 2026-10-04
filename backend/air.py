"""Outdoor air quality (US AQI) for a ZIP code, from free APIs that need no key.

ZIP -> latitude/longitude via api.zippopotam.us, then the current US AQI from
Open-Meteo's air-quality API. Results are cached; any failure returns None.
"""

import logging
import time

import httpx

log = logging.getLogger(__name__)

AQI_CACHE_SECONDS = 30 * 60
_places: dict[str, tuple[float, float]] = {}
_aqi: dict[str, tuple[float, float]] = {}  # zip -> (fetched_at, aqi)


async def _place(client: httpx.AsyncClient, zip_code: str) -> tuple[float, float]:
    if zip_code not in _places:
        response = await client.get(f"https://api.zippopotam.us/us/{zip_code}")
        response.raise_for_status()
        place = response.json()["places"][0]
        _places[zip_code] = (float(place["latitude"]), float(place["longitude"]))
    return _places[zip_code]


async def us_aqi(zip_code: str) -> float | None:
    cached = _aqi.get(zip_code)
    if cached and time.monotonic() - cached[0] < AQI_CACHE_SECONDS:
        return cached[1]
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            latitude, longitude = await _place(client, zip_code)
            response = await client.get(
                "https://air-quality-api.open-meteo.com/v1/air-quality",
                params={"latitude": latitude, "longitude": longitude, "current": "us_aqi"},
            )
            response.raise_for_status()
            value = response.json()["current"]["us_aqi"]
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
        log.warning("Air quality unavailable for %s: %s", zip_code, exc)
        return None
    if value is None:
        return None
    _aqi[zip_code] = (time.monotonic(), float(value))
    return float(value)
