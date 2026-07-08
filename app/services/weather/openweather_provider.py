from __future__ import annotations

from typing import Any

import httpx

from app.core.config.settings import settings
from app.services.live.schemas import LiveWeatherReport


class OpenWeatherProvider:
    provider_name = "openweather"
    default_base_url = "https://api.openweathermap.org/data/2.5"

    def configured(self) -> bool:
        return bool(settings.weather_api_key)

    def current(self, location: str) -> LiveWeatherReport:
        requested_location = location.strip() or settings.weather_default_location
        if not self.configured():
            return LiveWeatherReport(
                location=requested_location,
                provider=self.provider_name,
                configured=False,
                error="OpenWeather is not configured.",
            )

        url = f"{(settings.weather_api_base_url or self.default_base_url).rstrip('/')}/weather"
        try:
            with httpx.Client(timeout=20) as client:
                response = client.get(
                    url,
                    params={
                        "q": requested_location,
                        "appid": settings.weather_api_key,
                        "units": settings.weather_default_units,
                    },
                )
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPStatusError as exc:
            return LiveWeatherReport(
                location=requested_location,
                provider=self.provider_name,
                configured=True,
                error=self._http_error(exc),
            )
        except Exception as exc:
            return LiveWeatherReport(location=requested_location, provider=self.provider_name, configured=True, error=str(exc))

        return LiveWeatherReport(
            location=self._location(payload) or requested_location,
            provider=self.provider_name,
            configured=True,
            temperature=self._number((payload.get("main") or {}).get("temp")),
            condition=self._condition(payload),
            humidity=self._integer((payload.get("main") or {}).get("humidity")),
            wind_speed=self._number((payload.get("wind") or {}).get("speed")),
        )

    def _http_error(self, exc: httpx.HTTPStatusError) -> str:
        try:
            payload = exc.response.json()
            message = payload.get("message")
        except ValueError:
            message = None
        if exc.response.status_code in {401, 403}:
            return f"OpenWeather access denied. Check WEATHER_API_KEY. {message or ''}".strip()
        if exc.response.status_code == 404:
            return f"Weather location was not found. {message or ''}".strip()
        if exc.response.status_code == 429:
            return "OpenWeather rate limit reached. Try again after the quota resets."
        return f"OpenWeather request failed with HTTP {exc.response.status_code}. {message or ''}".strip()

    def _location(self, payload: dict[str, Any]) -> str | None:
        name = payload.get("name")
        country = (payload.get("sys") or {}).get("country")
        if isinstance(name, str) and name.strip():
            return f"{name.strip()}, {country}" if isinstance(country, str) and country.strip() else name.strip()
        return None

    def _condition(self, payload: dict[str, Any]) -> str | None:
        weather = payload.get("weather")
        if isinstance(weather, list) and weather and isinstance(weather[0], dict):
            value = weather[0].get("description") or weather[0].get("main")
            if isinstance(value, str):
                return value.strip().title()
        return None

    def _number(self, value: Any) -> float | None:
        try:
            return round(float(value), 1)
        except (TypeError, ValueError):
            return None

    def _integer(self, value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
