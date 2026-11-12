"""Cassette serialization must remove API keys, authorization and contact details."""

from vcr import VCR
from vcr.request import Request


def test_cassette_filters_credentials_before_writing(tmp_path, vcr_config):
    path = tmp_path / "synthetic.yaml"
    recorder = VCR(**vcr_config)
    request = Request(
        "GET",
        "https://example.invalid/works?api_key=synthetic-secret&mailto=synthetic@example.invalid",
        None,
        {"Authorization": "Bearer synthetic-secret", "User-Agent": "synthetic@example.invalid"},
    )
    response = {"status": {"code": 200, "message": "OK"}, "headers": {}, "body": {"string": b"{}"}}
    with recorder.use_cassette(str(path), record_mode="all") as cassette:
        cassette.append(request, response)
    recorded = path.read_text()
    assert "synthetic-secret" not in recorded
    assert "synthetic@example.invalid" not in recorded
    assert "example.invalid/works" in recorded
