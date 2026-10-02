"""Look up current weather conditions using wttr.in's JSON API.

wttr.in needs no key and serves plain text by default when it detects a browser or curl
`User-Agent`; `format=j1` forces the JSON report regardless of caller, so no header is
required. Every numeric field in that JSON arrives as a string, so this module converts
them once at the boundary and hands the rest of the command a typed `WeatherReport`.
"""

import json
import sys
from typing import Annotated, Any
from urllib.parse import quote

import httpx
import typer
from loguru import logger
from pydantic import BaseModel
from rich.table import Table

from .config import load_settings
from .options import OutputOption, global_options
from .output import OutputFormat, out

WTTR_URL = "https://wttr.in"
DEFAULT_TIMEOUT_SECONDS = 10.0


class WeatherReport(BaseModel):
    """Current conditions for one location."""

    location: str
    temperature_c: float
    feels_like_c: float
    humidity_percent: int
    wind_speed_kmph: float
    description: str


def _parse_weather_report(location: str, payload: dict[str, Any]) -> WeatherReport:
    """Extract a `WeatherReport` from wttr.in's j1 JSON body."""
    conditions = payload["current_condition"][0]
    description = conditions["weatherDesc"][0]["value"]
    return WeatherReport(
        location=location,
        temperature_c=float(conditions["temp_C"]),
        feels_like_c=float(conditions["FeelsLikeC"]),
        humidity_percent=int(conditions["humidity"]),
        wind_speed_kmph=float(conditions["windspeedKmph"]),
        description=description,
    )


def _request_weather(
    client: httpx.Client,
    location: str,
    timeout: float,
) -> WeatherReport:
    """Fetch and parse the current conditions using an already-open client."""
    response = client.get(
        f"{WTTR_URL}/{quote(location)}",
        params={"format": "j1"},
        timeout=timeout,
    )
    response.raise_for_status()
    try:
        payload = response.json()
    except json.JSONDecodeError as exc:
        msg = f"no weather data found for {location!r}"
        raise ValueError(msg) from exc
    return _parse_weather_report(location, payload)


def fetch_weather(
    location: str,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    client: httpx.Client | None = None,
) -> WeatherReport:
    """Return the current conditions for `location`.

    Pass `client` to reuse a connection or to substitute a transport in tests; when
    omitted, a client is opened and closed around the single request.
    """
    if client is not None:
        return _request_weather(client, location, timeout)
    with httpx.Client() as owned_client:
        return _request_weather(owned_client, location, timeout)


def render_weather_json(report: WeatherReport) -> str:
    """Render `report` as a JSON object."""
    return report.model_dump_json()


def _build_weather_table(report: WeatherReport) -> Table:
    """Return a rich Table describing one weather report."""
    table = Table(title=report.location)
    table.add_column("Measure")
    table.add_column("Value", justify="right")
    table.add_row("Conditions", report.description)
    table.add_row("Temperature", f"{report.temperature_c:.1f} C")
    table.add_row("Feels like", f"{report.feels_like_c:.1f} C")
    table.add_row("Humidity", f"{report.humidity_percent}%")
    table.add_row("Wind speed", f"{report.wind_speed_kmph:.1f} km/h")
    return table


def emit(report: WeatherReport, fmt: OutputFormat) -> None:
    """Write `report` to stdout in the requested format."""
    if fmt is OutputFormat.json:
        sys.stdout.write(render_weather_json(report) + "\n")
        return
    out.print(_build_weather_table(report))


def weather(
    ctx: typer.Context,
    location: Annotated[
        list[str],
        typer.Argument(help="free-text place name, e.g. cleve or 'cleve, south australia'"),
    ],
    output: OutputOption = None,
    timeout: Annotated[
        float, typer.Option(help="request timeout in seconds")
    ] = DEFAULT_TIMEOUT_SECONDS,
) -> None:
    """Look up current weather conditions for a town, village or city."""
    settings = load_settings(verbose=global_options(ctx).verbose, output=output)
    query = " ".join(location)
    logger.debug("querying wttr.in for {!r}", query)
    try:
        report = fetch_weather(query, timeout=timeout)
    except httpx.HTTPError as exc:
        logger.exception("could not reach {}", WTTR_URL)
        raise typer.Exit(1) from exc
    except ValueError as exc:
        logger.error(str(exc))
        raise typer.Exit(1) from exc

    emit(report, settings.output)
