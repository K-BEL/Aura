"""Tests for export functions."""

import csv
import json
import tempfile
from pathlib import Path

from omniscraper.exporters import export, to_csv, to_json, to_jsonl
from omniscraper.models import ListingItem, ScrapeResult


def _sample_result() -> ScrapeResult:
    return ScrapeResult(
        site_name="test_site",
        total_pages=1,
        items=[
            ListingItem(
                source_url="https://example.com/1",
                data={"title": "Luxury Apartment", "price": 250000, "city": "Casablanca"},
            ),
            ListingItem(
                source_url="https://example.com/2",
                data={"title": "Modern Villa", "price": 500000, "city": "Marrakech"},
            ),
        ],
    )


class TestCsvExport:
    def test_exports_csv(self, tmp_path: Path):
        result = _sample_result()
        out = to_csv(result, tmp_path / "out.csv")
        assert out.exists()

        with open(out, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 2
        assert rows[0]["title"] == "Luxury Apartment"
        assert rows[1]["city"] == "Marrakech"


class TestJsonExport:
    def test_exports_json(self, tmp_path: Path):
        result = _sample_result()
        out = to_json(result, tmp_path / "out.json")
        assert out.exists()

        with open(out, encoding="utf-8") as f:
            data = json.load(f)

        assert len(data) == 2
        assert data[0]["title"] == "Luxury Apartment"
        assert data[1]["price"] == 500000


class TestJsonlExport:
    def test_exports_jsonl(self, tmp_path: Path):
        result = _sample_result()
        out = to_jsonl(result, tmp_path / "out.jsonl")
        assert out.exists()

        with open(out, encoding="utf-8") as f:
            lines = [json.loads(line) for line in f]

        assert len(lines) == 2
        assert lines[0]["source_url"] == "https://example.com/1"


class TestAutoDetect:
    def test_auto_csv(self, tmp_path: Path):
        result = _sample_result()
        out = export(result, tmp_path / "data.csv")
        assert out.suffix == ".csv"
        assert out.exists()

    def test_auto_json(self, tmp_path: Path):
        result = _sample_result()
        out = export(result, tmp_path / "data.json")
        assert out.suffix == ".json"

    def test_format_override(self, tmp_path: Path):
        result = _sample_result()
        out = export(result, tmp_path / "data.txt", fmt="jsonl")
        assert out.exists()
        # Should be JSONL even though extension is .txt
        with open(out, encoding="utf-8") as f:
            lines = f.readlines()
        assert len(lines) == 2

    def test_empty_result(self, tmp_path: Path):
        result = ScrapeResult(site_name="empty")
        out = to_csv(result, tmp_path / "empty.csv")
        assert out.exists()
