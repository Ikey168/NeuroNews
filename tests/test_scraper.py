from scrapy.http import HtmlResponse, Request

from src.scraper.spiders.news_spider import NewsSpider


def create_response(content, url="http://example.com/news/article"):
    """Helper function to create a fake HtmlResponse."""
    request = Request(url=url)
    return HtmlResponse(url=url, request=request, body=content.encode("utf-8"), encoding="utf-8")


class TestNewsSpider:
    def setup_method(self):
        self.spider = NewsSpider()

    def test_parse_article_basic(self):
        # Test basic article parsing
        html = """
        <html>
            <head><title>Test Article</title></head>
            <body>
                <h1>Main Headline</h1>
                <div class="article-body">
                    <p>First paragraph</p>
                    <p>Second paragraph</p>
                </div>
                <div class="byline">John Doe</div>
                <time datetime="2024-01-01T12:00:00">January 1, 2024</time>
            </body>
        </html>
        """
        response = create_response(html)
        result = self.spider.parse_article(response)

        assert result["title"] == "Main Headline"
        assert result["url"] == "http://example.com/news/article"
        assert "First paragraph Second paragraph" in result["content"]
        assert result["author"] == "John Doe"
        assert result["published_date"] == "2024-01-01T12:00:00"
        assert result["source"] == "example.com"

    def test_parse_article_missing_fields(self):
        # Test handling of missing fields
        html = """
        <html>
            <head><title>Test Article</title></head>
            <body>
                <div class="content">
                    <p>Only content</p>
                </div>
            </body>
        </html>
        """
        response = create_response(html)
        result = self.spider.parse_article(response)

        assert result["title"] == "Test Article"  # Falls back to title tag
        assert "Only content" in result["content"]
        assert result["author"] == "Unknown"
        assert result["source"] == "example.com"
        assert "published_date" in result  # Should default to current time

    def test_parse_article_category_from_url(self):
        # Test category extraction from URL
        url = "http://example.com/tech/latest-news"
        html = "<html><body><p>Content</p></body></html>"
        response = create_response(html, url)
        result = self.spider.parse_article(response)

        assert result["category"] == "tech"

    def test_content_selectors(self):
        # Test different content selectors
        html = """
        <html><body>
            <article><p>Article content</p></article>
            <div class="article-body"><p>Body content</p></div>
            <div class="content"><p>Main content</p></div>
            <div id="main-content"><p>Alternative content</p></div>
        </body></html>
        """
        response = create_response(html)
        result = self.spider.parse_article(response)

        assert any(
            content in result["content"]
            for content in [
                "Article content",
                "Body content",
                "Main content",
                "Alternative content",
            ]
        )
