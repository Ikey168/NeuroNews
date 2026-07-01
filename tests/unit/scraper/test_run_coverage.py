"""Coverage-focused tests for src/scraper/run.py.

Targets branches the existing ``test_run_cli.py`` leaves uncovered:

* ``run_spider`` playwright spider selection.
* ``main`` ``--list-sources`` fallback that reads sources from ``config/settings.json``
  (both the success and the exception-handling paths), and the SCRAPING_SOURCES path.
* ``main`` ``--validate`` and ``--spider`` (including the ``ValueError`` path).
* ``main`` multi-source + validate combined path.
* ``main`` config-file override branches for AWS profile / S3 / CloudWatch and
  the corresponding informational ``print`` statements.

scrapy is guarded with ``importorskip``. ``CrawlerProcess`` / ``MultiSourceRunner``
are mocked so no real crawl runs.
"""

import json
import os
import sys
from unittest.mock import MagicMock

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

pytest.importorskip("scrapy")

from scraper import run as run_mod  # noqa: E402


def make_settings():
    settings = MagicMock()
    settings.get.side_effect = lambda key, default=None: (
        {} if key == "ITEM_PIPELINES" else (default if default is not None else 400)
    )
    return settings


class TestRunSpiderPlaywright:
    def test_playwright_spider_selected(self, monkeypatch):
        settings = make_settings()
        proc = MagicMock()
        monkeypatch.setattr(run_mod, "load_aws_config", lambda env: {})
        monkeypatch.setattr(run_mod, "get_project_settings", lambda: settings)
        monkeypatch.setattr(run_mod, "CrawlerProcess", MagicMock(return_value=proc))

        # Provide a fake playwright spider module so the import inside run_spider
        # succeeds without pulling real playwright.
        fake_mod = MagicMock()
        fake_mod.PlaywrightNewsSpider = object
        monkeypatch.setitem(
            sys.modules, "scraper.spiders.playwright_spider", fake_mod
        )
        run_mod.run_spider(use_playwright=True)
        proc.crawl.assert_called_once_with(fake_mod.PlaywrightNewsSpider)
        proc.start.assert_called_once()


class TestListSources:
    def _argv(self, monkeypatch, argv):
        monkeypatch.setattr(sys, "argv", ["run.py"] + argv)

    def test_list_sources_from_settings(self, monkeypatch, capsys):
        runner = MagicMock()
        runner.spiders = {"cnn": object}
        monkeypatch.setattr(run_mod, "MultiSourceRunner", MagicMock(return_value=runner))

        settings = MagicMock()
        settings.get.side_effect = lambda key, default=None: (
            ["cnn.com", "bbc.com"] if key == "SCRAPING_SOURCES" else default
        )
        monkeypatch.setattr(run_mod, "get_project_settings", lambda: settings)
        self._argv(monkeypatch, ["--list-sources"])
        run_mod.main()
        out = capsys.readouterr().out
        assert "cnn.com" in out and "bbc.com" in out

    def test_list_sources_from_config_file(self, monkeypatch, capsys, tmp_path):
        runner = MagicMock()
        runner.spiders = {"cnn": object}
        monkeypatch.setattr(run_mod, "MultiSourceRunner", MagicMock(return_value=runner))

        settings = MagicMock()
        settings.get.side_effect = lambda key, default=None: (
            [] if key == "SCRAPING_SOURCES" else default
        )
        monkeypatch.setattr(run_mod, "get_project_settings", lambda: settings)

        monkeypatch.chdir(tmp_path)
        (tmp_path / "config").mkdir()
        (tmp_path / "config" / "settings.json").write_text(
            json.dumps({"scraping": {"sources": ["fromfile.com"]}})
        )
        self._argv(monkeypatch, ["--list-sources"])
        run_mod.main()
        assert "fromfile.com" in capsys.readouterr().out

    def test_list_sources_config_file_missing(self, monkeypatch, capsys, tmp_path):
        runner = MagicMock()
        runner.spiders = {"cnn": object}
        monkeypatch.setattr(run_mod, "MultiSourceRunner", MagicMock(return_value=runner))

        settings = MagicMock()
        settings.get.side_effect = lambda key, default=None: (
            [] if key == "SCRAPING_SOURCES" else default
        )
        monkeypatch.setattr(run_mod, "get_project_settings", lambda: settings)
        monkeypatch.chdir(tmp_path)  # no config/settings.json -> exception branch
        self._argv(monkeypatch, ["--list-sources"])
        run_mod.main()
        assert "Could not load sources" in capsys.readouterr().out


class TestValidateAndSpider:
    def _argv(self, monkeypatch, argv):
        monkeypatch.setattr(sys, "argv", ["run.py"] + argv)

    def test_validate_only(self, monkeypatch, capsys):
        validator = MagicMock()
        monkeypatch.setattr(
            run_mod, "ScrapedDataValidator", MagicMock(return_value=validator)
        )
        self._argv(monkeypatch, ["--validate"])
        run_mod.main()
        validator.save_validation_report.assert_called_once()
        assert "Data validation completed" in capsys.readouterr().out

    def test_spider_value_error(self, monkeypatch, capsys):
        runner = MagicMock()
        runner.run_spider.side_effect = ValueError("no such spider: bogus")
        monkeypatch.setattr(run_mod, "MultiSourceRunner", MagicMock(return_value=runner))
        self._argv(monkeypatch, ["--spider", "bogus"])
        run_mod.main()
        assert "Error: no such spider" in capsys.readouterr().out

    def test_multi_source_run_all(self, monkeypatch, capsys):
        # NOTE: ``--validate`` is checked before ``--multi-source`` in main() and
        # returns early, so the multi-source path is exercised on its own here.
        runner = MagicMock()
        monkeypatch.setattr(run_mod, "MultiSourceRunner", MagicMock(return_value=runner))
        self._argv(monkeypatch, ["--multi-source", "--exclude", "cnn", "--include", "bbc"])
        run_mod.main()
        runner.run_all_spiders.assert_called_once_with(
            exclude=["cnn"], include_only=["bbc"]
        )
        assert "Multi-source scraping completed" in capsys.readouterr().out


class TestMainConfigOverridesAndPrints:
    def _argv(self, monkeypatch, argv):
        monkeypatch.setattr(sys, "argv", ["run.py"] + argv)

    def test_config_file_drives_defaults_and_prints(self, monkeypatch, capsys):
        # main() mutates os.environ["AWS_PROFILE"]; register the key with
        # monkeypatch so it is restored on teardown and does not leak into
        # other tests/processes.
        monkeypatch.setenv("AWS_PROFILE", "")
        captured = {}

        def fake_run_spider(**kwargs):
            captured.update(kwargs)

        cfg = {
            "aws_profile": "cfg-profile",
            "s3_storage": {"enabled": True, "bucket": "cfg-bucket", "prefix": "cfg-prefix"},
            "cloudwatch_logging": {
                "enabled": True,
                "log_group": "cfg-group",
                "log_stream_prefix": "cfg-stream",
                "log_level": "DEBUG",
            },
        }
        monkeypatch.setattr(run_mod, "load_aws_config", lambda env: cfg)
        monkeypatch.setattr(run_mod, "run_spider", fake_run_spider)
        # Defaults for output/prefix/group so the config-override branches fire.
        self._argv(monkeypatch, ["--playwright"])
        run_mod.main()

        # AWS profile resolved from config, exported to env.
        assert os.environ.get("AWS_PROFILE") == "cfg-profile"
        # S3 + CloudWatch enabled and resolved from config.
        assert captured["s3_storage"] is True
        assert captured["s3_bucket"] == "cfg-bucket"
        assert captured["s3_prefix"] == "cfg-prefix"
        assert captured["cloudwatch_logging"] is True
        assert captured["cloudwatch_log_group"] == "cfg-group"
        assert captured["cloudwatch_log_stream_prefix"] == "cfg-stream"
        assert captured["cloudwatch_log_level"] == "DEBUG"
        assert captured["use_playwright"] is True

        out = capsys.readouterr().out
        assert "Using AWS profile: cfg-profile" in out
        assert "Storing articles in S3 bucket: cfg-bucket" in out
        assert "Logging to CloudWatch" in out
        assert "Log level: DEBUG" in out
        assert "Using Playwright" in out
        assert "Scraping completed." in out
