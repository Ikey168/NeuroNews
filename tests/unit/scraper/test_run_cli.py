"""Tests for src/scraper/run.py (CLI + spider runner)."""

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

pytest.importorskip("scrapy")

from scraper import run as run_mod  # noqa: E402


def make_settings():
    """A stand-in for a Scrapy Settings object."""
    settings = MagicMock()
    settings.get.side_effect = lambda key, default=None: (
        {} if key == "ITEM_PIPELINES" else (default if default is not None else 400)
    )
    return settings


class TestLoadAwsConfig:
    def test_missing_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert run_mod.load_aws_config("dev") == {}

    def test_valid_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "config").mkdir()
        (tmp_path / "config" / "prod_aws.json").write_text(json.dumps({"aws_profile": "p"}))
        assert run_mod.load_aws_config("prod") == {"aws_profile": "p"}

    def test_invalid_json(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "config").mkdir()
        (tmp_path / "config" / "dev_aws.json").write_text("{bad")
        assert run_mod.load_aws_config("dev") == {}
        assert "Could not parse" in capsys.readouterr().out


class TestRunSpider:
    def test_basic_run(self, monkeypatch):
        proc = MagicMock()
        monkeypatch.setattr(run_mod, "load_aws_config", lambda env: {})
        monkeypatch.setattr(run_mod, "get_project_settings", make_settings)
        monkeypatch.setattr(run_mod, "CrawlerProcess", MagicMock(return_value=proc))
        run_mod.run_spider()
        proc.crawl.assert_called_once()
        proc.start.assert_called_once()

    def test_output_file_sets_feed(self, monkeypatch, tmp_path):
        settings = make_settings()
        monkeypatch.setattr(run_mod, "load_aws_config", lambda env: {})
        monkeypatch.setattr(run_mod, "get_project_settings", lambda: settings)
        monkeypatch.setattr(run_mod, "CrawlerProcess", MagicMock())
        out = str(tmp_path / "out" / "articles.json")
        run_mod.run_spider(output_file=out)
        settings.set.assert_any_call("FEED_URI", out)

    def test_s3_storage_branch(self, monkeypatch):
        settings = make_settings()
        monkeypatch.setattr(run_mod, "load_aws_config", lambda env: {})
        monkeypatch.setattr(run_mod, "get_project_settings", lambda: settings)
        monkeypatch.setattr(run_mod, "CrawlerProcess", MagicMock())
        run_mod.run_spider(
            s3_storage=True, s3_bucket="b", s3_prefix="p",
            aws_access_key_id="k", aws_secret_access_key="s",
        )
        settings.set.assert_any_call("S3_BUCKET", "b")

    def test_cloudwatch_branch(self, monkeypatch):
        settings = make_settings()
        monkeypatch.setattr(run_mod, "load_aws_config", lambda env: {})
        monkeypatch.setattr(run_mod, "get_project_settings", lambda: settings)
        monkeypatch.setattr(run_mod, "CrawlerProcess", MagicMock())
        run_mod.run_spider(
            cloudwatch_logging=True, cloudwatch_log_group="g",
            cloudwatch_log_stream_prefix="sp", cloudwatch_log_level="INFO",
            aws_region="us-west-2",
        )
        settings.set.assert_any_call("CLOUDWATCH_LOGGING_ENABLED", True)

    def test_config_file_overrides(self, monkeypatch):
        settings = make_settings()
        cfg = {
            "aws_profile": "myprof",
            "s3_storage": {"enabled": True, "bucket": "cfgb", "prefix": "cfgp"},
            "cloudwatch_logging": {
                "enabled": True, "log_group": "cg",
                "log_stream_prefix": "cs", "log_level": "DEBUG",
            },
        }
        monkeypatch.setattr(run_mod, "load_aws_config", lambda env: cfg)
        monkeypatch.setattr(run_mod, "get_project_settings", lambda: settings)
        monkeypatch.setattr(run_mod, "CrawlerProcess", MagicMock())
        run_mod.run_spider()
        assert os.environ.get("AWS_PROFILE") == "myprof"
        settings.set.assert_any_call("S3_BUCKET", "cfgb")


class TestMainCLI:
    def _run(self, monkeypatch, argv):
        monkeypatch.setattr(sys, "argv", ["run.py"] + argv)

    def test_list_sources(self, monkeypatch, capsys):
        runner = MagicMock()
        runner.spiders = {"cnn": object, "bbc": object}
        monkeypatch.setattr(run_mod, "MultiSourceRunner", MagicMock(return_value=runner))
        self._run(monkeypatch, ["--list-sources"])
        run_mod.main()
        assert "cnn" in capsys.readouterr().out

    def test_report(self, monkeypatch):
        runner = MagicMock()
        monkeypatch.setattr(run_mod, "MultiSourceRunner", MagicMock(return_value=runner))
        self._run(monkeypatch, ["--report"])
        run_mod.main()
        runner.generate_report.assert_called_once()

    def test_single_spider(self, monkeypatch):
        runner = MagicMock()
        monkeypatch.setattr(run_mod, "MultiSourceRunner", MagicMock(return_value=runner))
        self._run(monkeypatch, ["--spider", "cnn"])
        run_mod.main()
        runner.run_spider.assert_called_once_with("cnn")

    def test_multi_source(self, monkeypatch):
        runner = MagicMock()
        monkeypatch.setattr(run_mod, "MultiSourceRunner", MagicMock(return_value=runner))
        self._run(monkeypatch, ["--multi-source"])
        run_mod.main()
        runner.run_all_spiders.assert_called_once()

    def test_default_runs_spider(self, monkeypatch):
        run_spider = MagicMock()
        monkeypatch.setattr(run_mod, "run_spider", run_spider)
        self._run(monkeypatch, ["--output", "x.json"])
        run_mod.main()
        run_spider.assert_called_once()
