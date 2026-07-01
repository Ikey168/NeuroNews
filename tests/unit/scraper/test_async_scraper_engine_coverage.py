"""Coverage-focused tests for src/scraper/async_scraper_engine.py.

Targets lines left uncovered by test_async_scraper_engine.py and
test_async_scraper_engine_internals.py:

* monitoring component wiring (CloudWatch / DynamoDB / SNS / retry) when
  ``enable_monitoring=True`` and the proxy / tor / captcha init branches,
* the async ``start()`` and ``close()`` methods with aiohttp + Playwright
  fully mocked (including the CloudWatch/DynamoDB flush branches on close),
* the Playwright JS scraping path (``scrape_js_source``,
  ``get_article_links_js``, ``scrape_article_js``),
* ``validate_article`` scoring branches, ``save_articles``, and the
  exception fall-throughs in the extract helpers.

External deps (aiohttp session/connector, playwright, monitoring managers)
are mocked. The known source bug -- get_article_links_http referencing the
undefined self.extract_links_from_html -- is avoided.
"""

import asyncio
import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

pytest.importorskip("aiohttp")
pytest.importorskip("bs4")

from scraper.async_scraper_engine import (  # noqa: E402
    Article,
    AsyncNewsScraperEngine,
    NewsSource,
    PerformanceMonitor,
)


def make_source(**over):
    base = dict(
        name="TestSource",
        base_url="https://example.com/news",
        article_selectors={
            "title": "h1",
            "content": "article p",
            "author": ".author",
            "date": "time",
        },
        link_patterns=[r"/news/.*"],
        requires_js=True,
        rate_limit=1.0,
    )
    base.update(over)
    return NewsSource(**base)


def make_article(**over):
    base = dict(
        title="A Genuinely Long Headline About Something",
        url="https://example.com/news/1",
        content="Body text. " * 30,
        author="Reporter",
        published_date="2026-01-01",
        source="TestSource",
        scraped_date="2026-01-01",
    )
    base.update(over)
    return Article(**base)


@pytest.fixture
def engine():
    eng = AsyncNewsScraperEngine(enable_monitoring=False)
    yield eng
    eng.monitor.stop()


# ---------------------------------------------------------------------------
# Async context-manager helper for Playwright page objects
# ---------------------------------------------------------------------------


def make_page(evaluate_return):
    """Build a mock Playwright page whose evaluate() returns ``evaluate_return``."""
    page = MagicMock()
    page.goto = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    page.close = AsyncMock()
    page.evaluate = AsyncMock(return_value=evaluate_return)
    return page


def make_context(pages):
    """Build a mock BrowserContext whose new_page() yields the given pages."""
    context = MagicMock()
    context.new_page = AsyncMock(side_effect=list(pages))
    context.close = AsyncMock()
    return context


# ---------------------------------------------------------------------------
# Monitoring / init branches
# ---------------------------------------------------------------------------


class TestMonitoringInit:
    def test_monitoring_wires_managers(self):
        with patch("scraper.cloudwatch_logger.CloudWatchLogger") as cw, patch(
            "scraper.dynamodb_failure_manager.DynamoDBFailureManager"
        ) as ddb, patch("scraper.sns_alert_manager.SNSAlertManager") as sns, patch(
            "scraper.enhanced_retry_manager.EnhancedRetryManager"
        ) as retry, patch(
            "scraper.enhanced_retry_manager.RetryConfig"
        ):
            eng = AsyncNewsScraperEngine(
                enable_monitoring=True, sns_topic_arn="arn:aws:sns:topic"
            )
            try:
                assert eng.cloudwatch_logger is not None
                assert eng.failure_manager is not None
                assert eng.alert_manager is not None
                assert eng.retry_manager is not None
                cw.assert_called_once()
                ddb.assert_called_once()
                sns.assert_called_once()
                retry.assert_called_once()
            finally:
                eng.monitor.stop()

    def test_monitoring_without_sns_topic(self):
        with patch("scraper.cloudwatch_logger.CloudWatchLogger"), patch(
            "scraper.dynamodb_failure_manager.DynamoDBFailureManager"
        ), patch("scraper.enhanced_retry_manager.EnhancedRetryManager"), patch(
            "scraper.enhanced_retry_manager.RetryConfig"
        ):
            eng = AsyncNewsScraperEngine(enable_monitoring=True)
            try:
                # No SNS topic -> alert_manager stays None.
                assert eng.alert_manager is None
                assert eng.cloudwatch_logger is not None
            finally:
                eng.monitor.stop()

    def test_proxy_config_path_branch(self):
        with patch("scraper.proxy_manager.ProxyRotationManager") as prm:
            eng = AsyncNewsScraperEngine(
                enable_monitoring=False, proxy_config_path="/tmp/proxies.json"
            )
            try:
                assert eng.proxy_manager is not None
                prm.assert_called_once_with(config_path="/tmp/proxies.json")
            finally:
                eng.monitor.stop()

    def test_proxy_config_dict_branch(self):
        with patch("scraper.proxy_manager.ProxyConfig") as pc:
            eng = AsyncNewsScraperEngine(
                enable_monitoring=False,
                proxy_config={"host": "1.2.3.4", "port": 8080},
            )
            try:
                pc.assert_called_once_with(host="1.2.3.4", port=8080)
                assert eng.proxy_manager is None
            finally:
                eng.monitor.stop()

    def test_tor_branch(self):
        with patch("scraper.tor_manager.TorManager") as tm:
            eng = AsyncNewsScraperEngine(enable_monitoring=False, use_tor=True)
            try:
                assert eng.tor_manager is not None
                tm.assert_called_once()
            finally:
                eng.monitor.stop()

    def test_captcha_branch(self):
        with patch("scraper.captcha_solver.CaptchaSolver") as cs:
            eng = AsyncNewsScraperEngine(
                enable_monitoring=False, captcha_api_key="secret-key"
            )
            try:
                assert eng.captcha_solver is not None
                cs.assert_called_once_with("secret-key")
            finally:
                eng.monitor.stop()


# ---------------------------------------------------------------------------
# PerformanceMonitor internals
# ---------------------------------------------------------------------------


class TestPerformanceMonitor:
    def test_monitor_records_and_reports(self):
        mon = PerformanceMonitor()
        try:
            mon.record_article("SourceA")
            mon.record_success(0.5)
            mon.record_error("SourceA")
            stats = mon.get_stats()
            assert stats["total_articles"] == 1
            assert stats["successful_requests"] == 1
            assert stats["failed_requests"] == 1
            assert stats["source_stats"]["SourceA"]["articles"] == 1
            assert stats["source_stats"]["SourceA"]["errors"] == 1
            assert 0 <= stats["success_rate"] <= 100
        finally:
            mon.stop()

    def test_monitor_system_swallows_errors(self):
        # Drive the real _monitor_system loop once with psutil raising so the
        # except branch (lines 92-93) executes without leaking exceptions.
        mon = PerformanceMonitor()
        mon.stop()  # halt the background daemon thread first
        mon.monitor_thread.join(timeout=2)

        class FlipFlag:
            """Truthy for the first while-check, falsy afterwards."""

            def __init__(self):
                self.checks = 0

            def __bool__(self):
                self.checks += 1
                return self.checks == 1

        flag = FlipFlag()
        mon.monitoring = flag

        with patch("scraper.async_scraper_engine.psutil.Process",
                   side_effect=RuntimeError("no proc")):
            # One guarded iteration: psutil raises -> except: pass -> loop exits.
            mon._monitor_system()

        assert flag.checks >= 2  # entered the loop once, then exited


# ---------------------------------------------------------------------------
# start()
# ---------------------------------------------------------------------------


class TestStart:
    @pytest.mark.asyncio
    async def test_start_initializes_session_and_browser(self, engine):
        fake_browser = MagicMock()
        fake_browser.new_context = AsyncMock(return_value=MagicMock())
        fake_chromium = MagicMock()
        fake_chromium.launch = AsyncMock(return_value=fake_browser)
        fake_pw = MagicMock()
        fake_pw.chromium = fake_chromium
        pw_starter = MagicMock()
        pw_starter.start = AsyncMock(return_value=fake_pw)

        with patch("scraper.async_scraper_engine.async_playwright",
                   return_value=pw_starter), patch(
            "scraper.async_scraper_engine.aiohttp.ClientSession"
        ) as session_cls, patch(
            "scraper.async_scraper_engine.aiohttp.TCPConnector"
        ), patch("scraper.async_scraper_engine.aiohttp.ClientTimeout"):
            await engine.start()

        # Session + browser created; some contexts spun up.
        session_cls.assert_called_once()
        fake_chromium.launch.assert_awaited_once()
        assert engine.browser is fake_browser
        assert len(engine.browser_contexts) >= 1

    @pytest.mark.asyncio
    async def test_start_with_proxy_config(self):
        proxy_obj = MagicMock()
        proxy_obj.proxy_type = "http"
        proxy_obj.host = "10.0.0.1"
        proxy_obj.port = 3128
        with patch("scraper.proxy_manager.ProxyConfig", return_value=proxy_obj):
            eng = AsyncNewsScraperEngine(
                enable_monitoring=False,
                proxy_config={"host": "10.0.0.1", "port": 3128},
            )
        try:
            fake_browser = MagicMock()
            fake_browser.new_context = AsyncMock(return_value=MagicMock())
            fake_chromium = MagicMock()
            fake_chromium.launch = AsyncMock(return_value=fake_browser)
            fake_pw = MagicMock()
            fake_pw.chromium = fake_chromium
            pw_starter = MagicMock()
            pw_starter.start = AsyncMock(return_value=fake_pw)

            with patch("scraper.async_scraper_engine.async_playwright",
                       return_value=pw_starter), patch(
                "scraper.async_scraper_engine.aiohttp.ClientSession"
            ), patch("scraper.async_scraper_engine.aiohttp.TCPConnector"), patch(
                "scraper.async_scraper_engine.aiohttp.ClientTimeout"
            ):
                await eng.start()

            # Proxy present -> chromium launched with a --proxy-server arg.
            args, kwargs = fake_chromium.launch.call_args
            browser_args = kwargs.get("args", [])
            assert any("--proxy-server=http://10.0.0.1:3128" in a for a in browser_args)
        finally:
            eng.monitor.stop()


# ---------------------------------------------------------------------------
# close() with monitoring branches
# ---------------------------------------------------------------------------


class TestClose:
    @pytest.mark.asyncio
    async def test_close_flushes_monitoring(self):
        with patch("scraper.cloudwatch_logger.CloudWatchLogger"), patch(
            "scraper.dynamodb_failure_manager.DynamoDBFailureManager"
        ), patch("scraper.enhanced_retry_manager.EnhancedRetryManager"), patch(
            "scraper.enhanced_retry_manager.RetryConfig"
        ):
            eng = AsyncNewsScraperEngine(enable_monitoring=True)
        try:
            eng.cloudwatch_logger.flush_metrics = AsyncMock()
            eng.failure_manager.cleanup_old_failures = AsyncMock()
            eng.session = MagicMock()
            eng.session.close = AsyncMock()
            eng.browser_contexts = []
            eng.browser = None
            eng.playwright = None
            eng.thread_pool = MagicMock()

            await eng.close()

            eng.cloudwatch_logger.flush_metrics.assert_awaited_once()
            eng.failure_manager.cleanup_old_failures.assert_awaited_once_with(days=30)
            eng.session.close.assert_awaited_once()
        finally:
            eng.monitor.stop()

    @pytest.mark.asyncio
    async def test_close_handles_flush_errors(self):
        with patch("scraper.cloudwatch_logger.CloudWatchLogger"), patch(
            "scraper.dynamodb_failure_manager.DynamoDBFailureManager"
        ), patch("scraper.enhanced_retry_manager.EnhancedRetryManager"), patch(
            "scraper.enhanced_retry_manager.RetryConfig"
        ):
            eng = AsyncNewsScraperEngine(enable_monitoring=True)
        try:
            eng.cloudwatch_logger.flush_metrics = AsyncMock(
                side_effect=RuntimeError("flush failed")
            )
            eng.failure_manager.cleanup_old_failures = AsyncMock(
                side_effect=RuntimeError("cleanup failed")
            )
            eng.session = None
            eng.browser_contexts = []
            eng.browser = None
            eng.playwright = None
            eng.thread_pool = MagicMock()

            # Errors in flush/cleanup are caught and logged, not raised.
            await eng.close()
            eng.thread_pool.shutdown.assert_called_once_with(wait=True)
        finally:
            eng.monitor.stop()

    @pytest.mark.asyncio
    async def test_close_closes_browser_and_contexts(self, engine):
        ctx1, ctx2 = MagicMock(), MagicMock()
        ctx1.close = AsyncMock()
        ctx2.close = AsyncMock()
        engine.browser_contexts = [ctx1, ctx2]
        engine.browser = MagicMock()
        engine.browser.close = AsyncMock()
        engine.playwright = MagicMock()
        engine.playwright.stop = AsyncMock()
        engine.session = None
        engine.thread_pool = MagicMock()

        await engine.close()

        ctx1.close.assert_awaited_once()
        ctx2.close.assert_awaited_once()
        engine.browser.close.assert_awaited_once()
        engine.playwright.stop.assert_awaited_once()


# ---------------------------------------------------------------------------
# JS scraping path
# ---------------------------------------------------------------------------


class TestGetArticleLinksJs:
    @pytest.mark.asyncio
    async def test_returns_links(self, engine):
        src = make_source()
        page = make_page(["https://example.com/news/1", "https://example.com/news/2"])
        context = make_context([page])
        links = await engine.get_article_links_js(context, src)
        assert links == ["https://example.com/news/1", "https://example.com/news/2"]
        page.goto.assert_awaited_once()
        page.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_exception_returns_empty_and_closes_page(self, engine):
        src = make_source()
        page = make_page(None)
        page.goto = AsyncMock(side_effect=RuntimeError("nav failed"))
        context = make_context([page])
        assert await engine.get_article_links_js(context, src) == []
        page.close.assert_awaited_once()


class TestScrapeArticleJs:
    @pytest.mark.asyncio
    async def test_builds_article(self, engine):
        src = make_source()
        data = {
            "title": "A Genuinely Long And Descriptive JS Headline",
            "content": "Body content text here. " * 20,
            "author": "JS Reporter",
            "date": "2026-02-02",
        }
        page = make_page(data)
        context = make_context([page])
        sem = asyncio.Semaphore(1)
        art = await engine.scrape_article_js(
            sem, context, src, "https://example.com/news/tech/9"
        )
        assert isinstance(art, Article)
        assert art.title == data["title"]
        assert art.author == "JS Reporter"
        assert art.category == "Technology"
        page.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_missing_title_returns_none(self, engine):
        src = make_source()
        page = make_page({"title": "", "content": "x", "author": "", "date": ""})
        context = make_context([page])
        sem = asyncio.Semaphore(1)
        assert await engine.scrape_article_js(
            sem, context, src, "https://example.com/x"
        ) is None

    @pytest.mark.asyncio
    async def test_default_author_used(self, engine):
        src = make_source()
        data = {
            "title": "A Genuinely Long Headline Without Any Author Given",
            "content": "Rich body content text. " * 20,
            "author": "",
            "date": "",
        }
        page = make_page(data)
        context = make_context([page])
        sem = asyncio.Semaphore(1)
        art = await engine.scrape_article_js(
            sem, context, src, "https://example.com/news/1"
        )
        assert art is not None
        assert art.author == "TestSource Sta"

    @pytest.mark.asyncio
    async def test_low_score_filtered(self, engine):
        src = make_source()
        engine.validate_article = MagicMock(return_value=5)
        data = {
            "title": "A Genuinely Long Headline Here For Coverage",
            "content": "Body content. " * 20,
            "author": "R",
            "date": "d",
        }
        page = make_page(data)
        context = make_context([page])
        sem = asyncio.Semaphore(1)
        assert await engine.scrape_article_js(
            sem, context, src, "https://example.com/x"
        ) is None

    @pytest.mark.asyncio
    async def test_exception_returns_none(self, engine):
        src = make_source()
        page = make_page(None)
        page.goto = AsyncMock(side_effect=RuntimeError("boom"))
        context = make_context([page])
        sem = asyncio.Semaphore(1)
        assert await engine.scrape_article_js(
            sem, context, src, "https://example.com/x"
        ) is None
        page.close.assert_awaited_once()


class TestScrapeJsSource:
    @pytest.mark.asyncio
    async def test_collects_articles(self, engine):
        src = make_source()
        engine.browser_contexts = [MagicMock()]
        links = ["https://example.com/news/1", "https://example.com/news/2"]
        engine.get_article_links_js = AsyncMock(return_value=links)

        good = make_article()

        async def fake_scrape(sem, context, source, link):
            return good

        engine.scrape_article_js = AsyncMock(side_effect=fake_scrape)

        result = await engine.scrape_js_source(src)
        assert len(result) == 2
        assert all(isinstance(a, Article) for a in result)
        for link in links:
            assert link in engine.seen_urls

    @pytest.mark.asyncio
    async def test_dedupes_and_filters(self, engine):
        src = make_source()
        engine.browser_contexts = [MagicMock()]
        engine.seen_urls.add("https://example.com/news/seen")
        engine.get_article_links_js = AsyncMock(
            return_value=[
                "https://example.com/news/seen",
                "https://example.com/news/new",
            ]
        )
        engine.scrape_article_js = AsyncMock(return_value=None)
        result = await engine.scrape_js_source(src)
        # seen url skipped; the new url yields None -> filtered out.
        assert result == []
        engine.scrape_article_js.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_exception_returns_empty(self, engine):
        src = make_source()
        engine.browser_contexts = [MagicMock()]
        engine.get_article_links_js = AsyncMock(side_effect=RuntimeError("js down"))
        assert await engine.scrape_js_source(src) == []


# ---------------------------------------------------------------------------
# validate_article scoring branches
# ---------------------------------------------------------------------------


class TestValidateArticle:
    def test_full_score_for_good_article(self, engine):
        art = make_article(content="x" * 500, title="A Reasonable Length Title Here")
        art.content_length = 500
        assert engine.validate_article(art) == 100

    def test_missing_fields_penalised(self, engine):
        art = make_article(title="", content="", author="")
        art.content_length = 0
        score = engine.validate_article(art)
        # -25 (title) -30 (content) -10 (author) -20 (short content) -10 (short title)
        assert score == max(0, 100 - 25 - 30 - 10 - 20 - 10)

    def test_very_long_content_penalty(self, engine):
        art = make_article(title="A Reasonable Length Title Here")
        art.content_length = 20000
        # long content -5
        assert engine.validate_article(art) == 95

    def test_long_title_penalty(self, engine):
        art = make_article(title="T" * 250)
        art.content_length = 500
        # long title -5
        assert engine.validate_article(art) == 95

    def test_short_title_penalty(self, engine):
        art = make_article(title="Short")
        art.content_length = 500
        # short title -10
        assert engine.validate_article(art) == 90

    def test_short_content_penalty(self, engine):
        art = make_article(title="A Reasonable Length Title Here")
        art.content_length = 50
        # short content -20
        assert engine.validate_article(art) == 80

    def test_quality_labels(self, engine):
        assert engine.get_quality_label(85) == "high"
        assert engine.get_quality_label(65) == "medium"
        assert engine.get_quality_label(30) == "low"


# ---------------------------------------------------------------------------
# extract helper exception fall-throughs
# ---------------------------------------------------------------------------


class TestExtractHelpersExceptions:
    def test_extract_text_bad_soup_returns_empty(self, engine):
        broken = MagicMock()
        broken.select_one.side_effect = RuntimeError("bad selector")
        assert engine.extract_text_by_selector(broken, "h1") == ""

    def test_extract_content_bad_soup_returns_empty(self, engine):
        broken = MagicMock()
        broken.select.side_effect = RuntimeError("bad selector")
        assert engine.extract_content_by_selector(broken, "p") == ""


# ---------------------------------------------------------------------------
# category extraction (each mapped category) + fallback
# ---------------------------------------------------------------------------


class TestExtractCategory:
    @pytest.mark.parametrize(
        "url,expected",
        [
            ("https://x.com/technology/a", "Technology"),
            ("https://x.com/politics/b", "Politics"),
            ("https://x.com/business/c", "Business"),
            ("https://x.com/sports/d", "Sports"),
            ("https://x.com/health/e", "Health"),
            ("https://x.com/science/f", "Science"),
            ("https://x.com/misc/g", "News"),
        ],
    )
    def test_category_mapping(self, engine, url, expected):
        assert engine.extract_category_from_url(url) == expected


# ---------------------------------------------------------------------------
# save_articles + get_performance_stats
# ---------------------------------------------------------------------------


class TestSaveArticles:
    @pytest.mark.asyncio
    async def test_save_writes_json(self, engine, tmp_path):
        out = tmp_path / "nested" / "articles.json"
        await engine.save_articles([make_article(), make_article(url="u2")], str(out))
        # File actually written to disk with two serialised articles.
        data = json.loads(out.read_text())
        assert len(data) == 2
        assert data[0]["title"].startswith("A Genuinely Long")

    def test_get_performance_stats_delegates_to_monitor(self, engine):
        engine.monitor.record_success(0.3)
        stats = engine.get_performance_stats()
        assert stats["successful_requests"] >= 1
        assert "elapsed_time" in stats
