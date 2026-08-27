"""Offline tests for the ROR auto-download path (network + zip are stubbed)."""
import io
import json
import zipfile

import fairly.authorities.ror as ror


def _fake_dump_bytes():
    orgs = [
        {"id": "https://ror.org/01an7q238",
         "names": [{"value": "University of California, Berkeley", "types": ["ror_display"]},
                   {"value": "UC Berkeley", "types": ["alias"]}],
         "locations": [{"geonames_details": {"country_code": "US", "name": "Berkeley"}}]},
        {"id": "https://ror.org/00f54p054",
         "names": [{"value": "Stanford University", "types": ["ror_display"]}],
         "locations": [{"geonames_details": {"country_code": "US", "name": "Stanford"}}]},
    ]
    return json.dumps(orgs).encode("utf-8")


def _fake_zip_bytes(member="v2.12-2026-08-25-ror-data_schema_v2.json"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(member, _fake_dump_bytes())
        zf.writestr("v2.12-2026-08-25-ror-data.csv", "ignore me")
    return buf.getvalue()


def test_fetch_latest_and_build(tmp_path, monkeypatch):
    zip_bytes = _fake_zip_bytes()

    monkeypatch.setattr(ror, "_http_get_json", lambda url, timeout=30: {
        "hits": {"hits": [{"files": [
            {"key": "v2.12-2026-08-25-ror-data.zip",
             "links": {"self": "https://zenodo.example/download"}},
        ]}]}
    })

    def fake_download(url, dest, timeout=120):
        with open(dest, "wb") as fh:
            fh.write(zip_bytes)

    monkeypatch.setattr(ror, "_download", fake_download)

    cache = tmp_path / "ror_cache"
    path = ror.fetch_latest_ror_dump(cache_dir=str(cache))

    assert path.endswith("_schema_v2.json")
    # The large zip is removed; only the extracted JSON is cached.
    assert not list(cache.glob("*.zip"))

    idx = ror.build_ror_index(path)
    assert idx.resolve("UC Berkeley") == "https://ror.org/01an7q238"
    assert idx.resolve("Stanford University") == "https://ror.org/00f54p054"


def test_cache_reused_without_redownload(tmp_path, monkeypatch):
    zip_bytes = _fake_zip_bytes()
    monkeypatch.setattr(ror, "_http_get_json", lambda url, timeout=30: {
        "hits": {"hits": [{"files": [
            {"key": "v2.12-2026-08-25-ror-data.zip",
             "links": {"self": "https://zenodo.example/download"}},
        ]}]}
    })

    calls = {"n": 0}

    def counting_download(url, dest, timeout=120):
        calls["n"] += 1
        with open(dest, "wb") as fh:
            fh.write(zip_bytes)

    monkeypatch.setattr(ror, "_download", counting_download)

    cache = str(tmp_path / "ror_cache")
    p1 = ror.fetch_latest_ror_dump(cache_dir=cache)
    p2 = ror.fetch_latest_ror_dump(cache_dir=cache)  # should hit cache, not re-download
    assert p1 == p2
    assert calls["n"] == 1

    p3 = ror.fetch_latest_ror_dump(cache_dir=cache, force=True)  # force re-download
    assert p3 == p1
    assert calls["n"] == 2
