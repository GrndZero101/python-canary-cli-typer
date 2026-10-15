"""Tests for the weather lookup.

No network: every request is served by an httpx MockTransport, so these are
deterministic and run offline. Log assertions read captured stderr: the app
callback points loguru at `sys.stderr` when `main` runs, which is the stream
`capsys` has already swapped in.
"""

import functools
import json
from pathlib import Path

import httpx
import pytest

from python_canary_cli_typer.cli import main
from python_canary_cli_typer.http_client import build_client
from python_canary_cli_typer.weather import (
    WTTR_URL,
    WeatherReport,
    fetch_weather,
    render_weather_json,
)

CLEVE_REPORT = {
    "current_condition": [
        {
            "temp_C": "22",
            "FeelsLikeC": "20",
            "humidity": "60",
            "windspeedKmph": "11",
            "weatherDesc": [{"value": "Sunny"}],
        }
    ],
}


def _make_response(
    status: int, body: str, seen: list[httpx.Request], request: httpx.Request
) -> httpx.Response:
    """MockTransport handler: record the request, then build a fresh response for it."""
    seen.append(request)
    return httpx.Response(status, text=body)


def _refuse(request: httpx.Request) -> httpx.Response:
    """MockTransport handler for a service that cannot be reached."""
    msg = "connection refused"
    raise httpx.ConnectError(msg, request=request)


def _no_wait(_seconds: float) -> None:
    """Stand in for `time.sleep`, so a retried request does not wait."""


def client_returning(
    body: str | None = None, status: int = 200, seen: list[httpx.Request] | None = None
) -> httpx.Client:
    """Return a client whose every request answers with `body` and `status`."""
    text = body if body is not None else json.dumps(CLEVE_REPORT)
    handler = functools.partial(_make_response, status, text, seen if seen is not None else [])
    return build_client(transport=httpx.MockTransport(handler), sleep=_no_wait)


def _serving(client: httpx.Client, **_kwargs: object) -> httpx.Client:
    """Stand in for `weather.build_client`, handing the command `client`."""
    return client


def _serve(monkeypatch: pytest.MonkeyPatch, client: httpx.Client) -> None:
    """Make the command's own client `client`."""
    monkeypatch.setattr(
        "python_canary_cli_typer.weather.build_client", functools.partial(_serving, client)
    )


def test_returns_a_report_parsed_from_the_body() -> None:
    with client_returning() as client:
        report = fetch_weather("cleve", client=client)
    assert report == WeatherReport(
        location="cleve",
        temperature_c=22.0,
        feels_like_c=20.0,
        humidity_percent=60,
        wind_speed_kmph=11.0,
        description="Sunny",
    )


def test_http_error_propagates() -> None:
    with client_returning(status=503) as client, pytest.raises(httpx.HTTPStatusError):
        fetch_weather("cleve", client=client)


def test_unparseable_body_is_a_value_error() -> None:
    with (
        client_returning(body="Unable to find any matching weather location") as client,
        pytest.raises(ValueError, match="no weather data found"),
    ):
        fetch_weather("nowhere-at-all-xyz", client=client)


def test_render_weather_json() -> None:
    report = WeatherReport(
        location="Cleve, South Australia",
        temperature_c=22.0,
        feels_like_c=20.0,
        humidity_percent=60,
        wind_speed_kmph=11.0,
        description="Sunny",
    )
    decoded = json.loads(render_weather_json(report))
    assert decoded == {
        "location": "Cleve, South Australia",
        "temperature_c": 22.0,
        "feels_like_c": 20.0,
        "humidity_percent": 60,
        "wind_speed_kmph": 11.0,
        "description": "Sunny",
    }


def test_main_prints_conditions_to_stdout(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _serve(monkeypatch, client_returning())
    assert main(["weather", "cleve"]) == 0
    captured = capsys.readouterr()
    assert "Sunny" in captured.out


def test_main_output_json_emits_parseable_stdout(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _serve(monkeypatch, client_returning())
    assert main(["weather", "cleve", "--output", "json"]) == 0
    decoded = json.loads(capsys.readouterr().out)
    assert decoded["description"] == "Sunny"


def test_main_reads_the_config_file_named_by_the_global_flag(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("output: json\n", encoding="utf-8")
    _serve(monkeypatch, client_returning())
    assert main(["--config", str(config_path), "weather", "cleve"]) == 0
    decoded = json.loads(capsys.readouterr().out)
    assert decoded["description"] == "Sunny"


def test_main_joins_multi_word_location(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[httpx.Request] = []
    _serve(monkeypatch, client_returning(seen=seen))
    main(["weather", "cleve,", "south", "australia"])
    assert seen[0].url.path == "/cleve, south australia"


def test_main_reports_no_data_without_polluting_stdout(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _serve(monkeypatch, client_returning(body="Unable to find any matching weather location"))
    assert main(["weather", "nowhere-at-all-xyz"]) == 1
    captured = capsys.readouterr()
    assert not captured.out
    assert "no weather data found" in captured.err


def test_main_reports_unreachable_service_without_polluting_stdout(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _serve(monkeypatch, build_client(transport=httpx.MockTransport(_refuse), sleep=_no_wait))
    assert main(["weather", "cleve"]) == 1
    captured = capsys.readouterr()
    assert not captured.out
    assert "could not reach https://wttr.in: connection refused" in captured.err


def test_wttr_url_is_the_official_endpoint() -> None:
    assert WTTR_URL == "https://wttr.in"
