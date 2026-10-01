"""Tests for the weather lookup.

No network: every request is served by an httpx MockTransport, so these are
deterministic and run offline. Log assertions read captured stderr: the app
callback points loguru at `sys.stderr` when `main` runs, which is the stream
`capsys` has already swapped in.
"""

import functools
import json

import httpx
import pytest

from template_dogfood.cli import main
from template_dogfood.weather import WTTR_URL, WeatherReport, fetch_weather, render_weather_json

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


def _make_response(status: int, body: str, _request: httpx.Request) -> httpx.Response:
    """MockTransport handler: build a fresh response for every request."""
    return httpx.Response(status, text=body)


def client_returning(body: str | None = None, status: int = 200) -> httpx.Client:
    """Return a client whose every request answers with `body` and `status`."""
    text = body if body is not None else json.dumps(CLEVE_REPORT)
    handler = functools.partial(_make_response, status, text)
    return httpx.Client(transport=httpx.MockTransport(handler))


def _unreachable(*_args: object, **_kwargs: object) -> WeatherReport:
    """Stand in for fetch_weather when the service cannot be reached."""
    msg = "connection refused"
    raise httpx.ConnectError(msg)


def _always(report: WeatherReport, *_args: object, **_kwargs: object) -> WeatherReport:
    """Stand in for fetch_weather with a fixed answer."""
    return report


def _record_query(seen_queries: list[str], query: str, **_kwargs: object) -> WeatherReport:
    """Stand in for fetch_weather, recording the query it was called with."""
    seen_queries.append(query)
    return WeatherReport(
        location=query,
        temperature_c=0.0,
        feels_like_c=0.0,
        humidity_percent=0,
        wind_speed_kmph=0.0,
        description="x",
    )


def _no_data(*_args: object, **_kwargs: object) -> WeatherReport:
    """Stand in for fetch_weather when the location has no data."""
    msg = "no weather data found for 'nowhere-at-all-xyz'"
    raise ValueError(msg)


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


def test_caller_supplied_client_is_not_closed() -> None:
    """The function must not close a client it does not own."""
    with client_returning() as client:
        fetch_weather("cleve", client=client)
        assert not client.is_closed


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
    report = WeatherReport(
        location="Cleve",
        temperature_c=22.0,
        feels_like_c=20.0,
        humidity_percent=60,
        wind_speed_kmph=11.0,
        description="Sunny",
    )
    monkeypatch.setattr(
        "template_dogfood.weather.fetch_weather", functools.partial(_always, report)
    )
    assert main(["weather", "cleve"]) == 0
    captured = capsys.readouterr()
    assert "Sunny" in captured.out


def test_main_output_json_emits_parseable_stdout(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = WeatherReport(
        location="Cleve",
        temperature_c=22.0,
        feels_like_c=20.0,
        humidity_percent=60,
        wind_speed_kmph=11.0,
        description="Sunny",
    )
    monkeypatch.setattr(
        "template_dogfood.weather.fetch_weather", functools.partial(_always, report)
    )
    assert main(["weather", "cleve", "--output", "json"]) == 0
    decoded = json.loads(capsys.readouterr().out)
    assert decoded["description"] == "Sunny"


def test_main_joins_multi_word_location(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_queries: list[str] = []
    monkeypatch.setattr(
        "template_dogfood.weather.fetch_weather", functools.partial(_record_query, seen_queries)
    )
    main(["weather", "cleve,", "south", "australia"])
    assert seen_queries == ["cleve, south australia"]


def test_main_reports_no_data_without_polluting_stdout(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("template_dogfood.weather.fetch_weather", _no_data)
    assert main(["weather", "nowhere-at-all-xyz"]) == 1
    captured = capsys.readouterr()
    assert not captured.out
    assert "no weather data found" in captured.err


def test_main_reports_unreachable_service_without_polluting_stdout(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("template_dogfood.weather.fetch_weather", _unreachable)
    assert main(["weather", "cleve"]) == 1
    captured = capsys.readouterr()
    assert not captured.out
    assert "could not reach" in captured.err


def test_wttr_url_is_the_official_endpoint() -> None:
    assert WTTR_URL == "https://wttr.in"
