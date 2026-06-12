"""
Tests for GET /inbound (artifact listing) and GET /inbound/batches (grouping),
plus the parallel run_extraction service against a stubbed Gemini client.
"""

import json

from service_photo.services import inbound_extraction

from .conftest import JPEG_BYTES


def _write_artifact(inbound_dir, stem, batch_name=None, started=None, api_error=None):
    artifact = {
        "meta": {
            "image_files": [f"{stem}.jpg"],
            "model": "gemini-2.5-flash",
            "batch_name": batch_name,
            "batch_started_at_utc": started,
            "api_error": api_error,
            "schema_valid": api_error is None,
        },
        "response": None if api_error else {"overview": {"brand": "Nikon"}},
    }
    path = inbound_dir / f"extraction_2026-06-12T00-00-00Z__{stem}.json"
    path.write_text(json.dumps(artifact), encoding="utf-8")
    return path


class TestListInbound:
    def test_empty_dir_returns_empty_list(self, inbound_client):
        r = inbound_client.get("/api/v1/inbound")
        assert r.status_code == 200
        assert r.json()["items"] == []

    def test_lists_artifacts_and_skips_corrupt_files(self, inbound_client, data_dirs):
        _write_artifact(data_dirs["inbound"], "good")
        (data_dirs["inbound"] / "extraction_bad.json").write_text("{not json", encoding="utf-8")

        r = inbound_client.get("/api/v1/inbound")
        items = r.json()["items"]
        assert len(items) == 1
        assert items[0]["image_files"] == ["good.jpg"]
        assert items[0]["image_urls"] == ["/api/v1/inbound/images/good.jpg"]


class TestBatches:
    def test_groups_by_batch_and_counts_failures(self, inbound_client, data_dirs):
        ts = "2026-06-12T10:00:00Z"
        _write_artifact(data_dirs["inbound"], "a", batch_name="run one", started=ts)
        _write_artifact(data_dirs["inbound"], "b", batch_name="run one", started=ts, api_error="boom")
        _write_artifact(data_dirs["inbound"], "legacy")  # no batch metadata

        r = inbound_client.get("/api/v1/inbound/batches")
        batches = r.json()["batches"]
        assert len(batches) == 2

        named = next(b for b in batches if b["batch_name"] == "run one")
        assert named["image_count"] == 2
        assert named["succeeded"] == 1
        assert named["failed"] == 1

        legacy = next(b for b in batches if b["batch_id"] == "__legacy__")
        assert legacy["image_count"] == 1


class FakeGeminiClient:
    """Stands in for RealGeminiClient — returns a canned response instantly."""

    model_name = "fake-model"

    def analyse_images(self, image_paths, prompt, enable_web_search=False):
        return {
            "overview": {"brand": "Nikon"},
            "pricing": {"market_valuation": {"fair_price": 100}},
        }


class TestRunExtractionParallel:
    def test_parallel_run_writes_one_artifact_per_image(self, tmp_path, monkeypatch):
        input_dir = tmp_path / "in"
        output_dir = tmp_path / "out"
        input_dir.mkdir()
        for i in range(5):
            (input_dir / f"img{i}.jpg").write_bytes(JPEG_BYTES)

        monkeypatch.setattr(inbound_extraction, "RealGeminiClient", lambda model_name=None: FakeGeminiClient())
        monkeypatch.setattr(inbound_extraction, "load_prompt", lambda: "prompt text")
        monkeypatch.setattr(inbound_extraction.settings, "EXTRACTION_CONCURRENCY", 3)

        started, finished = [], []
        summary = inbound_extraction.run_extraction(
            input_folder=input_dir,
            output_folder=output_dir,
            on_image_start=lambda i, t, name: started.append(name),
            on_image_done=lambda i, t, res: finished.append(res.image_name),
            batch_name="parallel test",
            batch_started_at_utc="2026-06-12T10:00:00Z",
        )

        assert summary.total == 5
        assert summary.succeeded == 5
        assert summary.failed == 0
        # Results stay in deterministic filename order even with parallel completion.
        assert [r.image_name for r in summary.results] == sorted(f"img{i}.jpg" for i in range(5))
        # Every callback fired exactly once per image.
        assert sorted(started) == sorted(finished) == sorted(f"img{i}.jpg" for i in range(5))

        artifacts = sorted(output_dir.glob("extraction_*.json"))
        assert len(artifacts) == 5
        sample = json.loads(artifacts[0].read_text(encoding="utf-8"))
        assert sample["meta"]["batch_name"] == "parallel test"
        # Pricing hoisted out of response to the artifact root.
        assert sample["pricing"] == {"market_valuation": {"fair_price": 100}}
        assert "pricing" not in sample["response"]

    def test_purge_existing_removes_prior_artifacts(self, tmp_path, monkeypatch):
        input_dir = tmp_path / "in"
        output_dir = tmp_path / "out"
        input_dir.mkdir()
        output_dir.mkdir()
        (input_dir / "img.jpg").write_bytes(JPEG_BYTES)
        stale = output_dir / "extraction_old__stale.json"
        stale.write_text("{}", encoding="utf-8")

        monkeypatch.setattr(inbound_extraction, "RealGeminiClient", lambda model_name=None: FakeGeminiClient())
        monkeypatch.setattr(inbound_extraction, "load_prompt", lambda: "prompt text")

        inbound_extraction.run_extraction(
            input_folder=input_dir,
            output_folder=output_dir,
            purge_existing=True,
        )
        assert not stale.exists()
        assert len(list(output_dir.glob("extraction_*.json"))) == 1
