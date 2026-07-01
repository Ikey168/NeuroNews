"""Coverage tests for src/database/dynamodb_metadata_manager.py.

Uses moto's mock_aws() so the boto3 DynamoDB resource/client created via
src.utils.local_cloud.get_resource/get_client are intercepted. Real table
creation, indexing, querying, full-text search, statistics, update/delete,
health check and the integration helpers are exercised end-to-end against the
moto in-memory DynamoDB, plus targeted error branches.
"""

import asyncio

import pytest
from moto import mock_aws

from src.database.dynamodb_metadata_manager import (
    ArticleMetadataIndex,
    DynamoDBMetadataConfig,
    DynamoDBMetadataManager,
    SearchMode,
    SearchQuery,
    integrate_with_redshift_etl,
    integrate_with_s3_storage,
    sync_metadata_from_scraper,
)


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def make_manager(table="meta-table"):
    return DynamoDBMetadataManager(DynamoDBMetadataConfig(table_name=table))


SAMPLE = {
    "id": "a1",
    "title": "Breaking News About Climate Science",
    "source": "reuters",
    "published_date": "2024-06-15",
    "url": "http://x/a1",
    "content": "Detailed climate science article body about warming trends.",
    "category": "science",
    "tags": ["climate", "science"],
    "author": "Jane Doe",
}


# --------------------------------------------------------------------------
# Dataclass helpers
# --------------------------------------------------------------------------

def test_metadata_index_tokenize_and_item():
    idx = ArticleMetadataIndex(
        article_id="x",
        content_hash="h",
        title="Hello Amazing World",
        source="s",
        published_date="2024-01-02",
        tags=["b", "a"],
        category="news",
    )
    # __post_init__ builds title_tokens (words > 2 chars, deduped)
    assert "hello" in idx.title_tokens
    assert "amazing" in idx.title_tokens
    item = idx.to_dynamodb_item()
    assert item["source_date"] == "s#2024-01-02"
    assert item["year_month"] == "2024-01"
    assert item["tags_string"] == "a#b"  # sorted


def test_metadata_index_short_published_date_year_month_empty():
    idx = ArticleMetadataIndex(
        article_id="x",
        content_hash="h",
        title="T",
        source="s",
        published_date="24",  # too short
    )
    assert idx.to_dynamodb_item()["year_month"] == ""


def test_from_dynamodb_item_roundtrip():
    idx = ArticleMetadataIndex(
        article_id="x", content_hash="h", title="Title", source="s",
        published_date="2024-01-01", tags=["t"],
    )
    item = idx.to_dynamodb_item()
    restored = ArticleMetadataIndex.from_dynamodb_item(item)
    assert restored.article_id == "x"
    assert restored.tags == ["t"]


# --------------------------------------------------------------------------
# Init / table creation
# --------------------------------------------------------------------------

@mock_aws
def test_manager_creates_table_from_config():
    mgr = make_manager("created-table")
    assert mgr.table is not None
    # Table was created with GSIs
    desc = mgr.dynamodb_client.describe_table(TableName="created-table")
    gsi_names = {g["IndexName"] for g in desc["Table"].get("GlobalSecondaryIndexes", [])}
    assert "source-date-index" in gsi_names


@mock_aws
def test_manager_string_config_and_existing_table():
    # String config -> DynamoDBMetadataConfig(table_name=...) (line 253)
    mgr1 = DynamoDBMetadataManager("string-table")
    assert mgr1.table_name == "string-table"
    # Second manager for the same table hits the "table exists" path (277-278)
    mgr2 = DynamoDBMetadataManager("string-table")
    assert mgr2.table is not None


@mock_aws
def test_manager_no_pitr_still_creates_indexes():
    # enable_point_in_time_recovery=False skips the update_continuous_backups
    # call (branch at line 356). create_indexes stays True because passing an
    # empty GlobalSecondaryIndexes list is rejected by DynamoDB/moto (a genuine
    # source limitation: _create_table always forwards the GSI list).
    cfg = DynamoDBMetadataConfig(
        table_name="ep-table",
        endpoint_url=None,
        enable_point_in_time_recovery=False,
    )
    mgr = DynamoDBMetadataManager(cfg)
    desc = mgr.dynamodb_client.describe_table(TableName="ep-table")
    gsis = desc["Table"].get("GlobalSecondaryIndexes", [])
    assert len(gsis) == 3


def test_manager_with_endpoint_url_kwarg(monkeypatch):
    # config.endpoint_url set -> merged into client kwargs (line 261). moto does
    # not intercept a custom endpoint, so capture the kwargs via stubbed
    # get_resource/get_client instead of doing real network I/O.
    from src.database import dynamodb_metadata_manager as dm

    captured = {}

    class FakeTable:
        class meta:
            class client:
                @staticmethod
                def describe_table(**k):
                    return {}

    class FakeResource:
        def Table(self, name):
            return FakeTable()

    def fake_get_resource(service, region_name=None, **kw):
        captured["resource_kwargs"] = kw
        return FakeResource()

    def fake_get_client(service, region_name=None, **kw):
        captured["client_kwargs"] = kw
        return object()

    monkeypatch.setattr(dm, "get_resource", fake_get_resource)
    monkeypatch.setattr(dm, "get_client", fake_get_client)

    cfg = DynamoDBMetadataConfig(
        table_name="epk-table", endpoint_url="http://localhost:8000"
    )
    mgr = DynamoDBMetadataManager(cfg)
    assert captured["resource_kwargs"]["endpoint_url"] == "http://localhost:8000"
    assert captured["client_kwargs"]["endpoint_url"] == "http://localhost:8000"
    assert mgr.table is not None


@mock_aws
def test_initialize_table_non_notfound_reraised(monkeypatch):
    from botocore.exceptions import ClientError

    cfg = DynamoDBMetadataConfig(table_name="init-err")

    # Patch describe_table on the resource's table client to raise a non-404
    err = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "denied"}},
        "DescribeTable",
    )

    real_init = DynamoDBMetadataManager._initialize_table

    # Build manager but intercept describe_table before _initialize_table runs
    mgr = DynamoDBMetadataManager.__new__(DynamoDBMetadataManager)
    mgr.config = cfg
    mgr.table_name = cfg.table_name
    import logging as _logging

    mgr.logger = _logging.getLogger("test")
    from src.utils.local_cloud import get_resource, get_client

    mgr.dynamodb = get_resource("dynamodb", region_name="us-east-1")
    mgr.dynamodb_client = get_client("dynamodb", region_name="us-east-1")

    class FakeTable:
        class meta:
            class client:
                @staticmethod
                def describe_table(**k):
                    raise err

    mgr.dynamodb.Table = lambda name: FakeTable()
    with pytest.raises(ClientError):
        real_init(mgr)


@mock_aws
def test_create_table_exception_reraised(monkeypatch):
    cfg = DynamoDBMetadataConfig(table_name="ct-err")
    mgr = DynamoDBMetadataManager.__new__(DynamoDBMetadataManager)
    mgr.config = cfg
    mgr.table_name = cfg.table_name
    import logging as _logging

    mgr.logger = _logging.getLogger("test")
    from src.utils.local_cloud import get_resource, get_client

    mgr.dynamodb = get_resource("dynamodb", region_name="us-east-1")
    mgr.dynamodb_client = get_client("dynamodb", region_name="us-east-1")
    mgr.dynamodb.create_table = lambda **k: (_ for _ in ()).throw(
        RuntimeError("create boom")
    )
    with pytest.raises(RuntimeError, match="create boom"):
        mgr._create_table()


# --------------------------------------------------------------------------
# Indexing
# --------------------------------------------------------------------------

@mock_aws
def test_index_article_metadata():
    mgr = make_manager("idx-table")
    meta = run(mgr.index_article_metadata(SAMPLE))
    assert meta.article_id == "a1"
    fetched = run(mgr.get_article_by_id("a1"))
    assert fetched is not None
    assert fetched.title == SAMPLE["title"]


# GSI key attributes (source / published_date / category) must be non-empty or
# DynamoDB rejects the write, so every indexed article supplies them.
def full_article(**over):
    base = {
        "source": "src",
        "published_date": "2024-01-01",
        "category": "general",
        "content": "content body",
    }
    base.update(over)
    return base


@mock_aws
def test_create_metadata_generates_id_and_hash():
    mgr = make_manager("gen-table")
    # No id / content_hash -> both computed
    art = full_article(title="No Id Article", url="http://x/n")
    meta = run(mgr.index_article_metadata(art))
    assert meta.article_id  # md5 of url+title
    assert meta.content_hash  # sha256 of content


@mock_aws
def test_create_metadata_category_as_tag():
    mgr = make_manager("cat-table")
    # tags absent but category present -> category becomes the sole tag
    art = full_article(id="c1", title="T", category="tech")
    del art  # placeholder to keep readability; rebuild without 'tags'
    art = {"id": "c1", "title": "T", "category": "tech", "content": "x",
           "source": "src", "published_date": "2024-01-01"}
    meta = run(mgr.index_article_metadata(art))
    assert meta.tags == ["tech"]


@mock_aws
def test_create_metadata_scalar_tag():
    mgr = make_manager("scal-table")
    art = full_article(id="s1", title="T", tags="single")
    meta = run(mgr.index_article_metadata(art))
    assert meta.tags == ["single"]


@mock_aws
def test_index_article_error_reraised(monkeypatch):
    mgr = make_manager("err-table")

    def boom(**k):
        raise RuntimeError("put fail")

    mgr.table.put_item = boom
    with pytest.raises(RuntimeError, match="put fail"):
        run(mgr.index_article_metadata(SAMPLE))


@mock_aws
def test_batch_index_articles():
    mgr = make_manager("batch-table")
    articles = [
        {"id": "b{0}".format(i), "title": "T{0}".format(i), "source": "s",
         "published_date": "2024-01-0{0}".format(i + 1), "content": "c",
         "category": "general"}
        for i in range(3)
    ]
    result = run(mgr.batch_index_articles(articles))
    assert result["status"] == "completed"
    assert result["indexed_count"] == 3
    assert result["failed_count"] == 0


@mock_aws
def test_process_batch_handles_item_failure(monkeypatch):
    mgr = make_manager("pbf-table")

    real_create = mgr._create_metadata_from_article

    def flaky(article):
        if article.get("title") == "BAD":
            raise ValueError("bad article")
        return real_create(article)

    mgr._create_metadata_from_article = flaky
    articles = [
        {"id": "ok", "title": "Good", "content": "c", "source": "s",
         "published_date": "2024-01-01", "category": "general"},
        {"id": "bad", "title": "BAD", "content": "c", "source": "s",
         "published_date": "2024-01-01", "category": "general"},
    ]
    result = run(mgr.batch_index_articles(articles))
    assert result["indexed_count"] == 1
    assert result["failed_count"] == 1
    assert result["failed_articles"][0]["article_id"] == "bad"


# --------------------------------------------------------------------------
# Query API
# --------------------------------------------------------------------------

@mock_aws
def test_batch_index_outer_exception_reraised(monkeypatch):
    mgr = make_manager("batchouter-table")

    async def boom(batch):
        raise RuntimeError("process batch outer")

    monkeypatch.setattr(mgr, "_process_batch", boom)
    with pytest.raises(RuntimeError, match="process batch outer"):
        run(mgr.batch_index_articles([{"id": "x", "title": "T"}]))


@mock_aws
def test_get_article_by_id_missing_returns_none():
    mgr = make_manager("byid-table")
    assert run(mgr.get_article_by_id("nope")) is None


@mock_aws
def test_get_articles_by_source_with_date_filter():
    mgr = make_manager("src-table")
    run(mgr.index_article_metadata(SAMPLE))
    run(mgr.index_article_metadata({**SAMPLE, "id": "a2", "published_date": "2024-06-20"}))
    result = run(
        mgr.get_articles_by_source(
            "reuters", start_date="2024-06-01", end_date="2024-06-30"
        )
    )
    assert result.count >= 1
    assert all(item.source == "reuters" for item in result.items)


@mock_aws
def test_get_articles_by_date_range():
    mgr = make_manager("dr-table")
    run(mgr.index_article_metadata(SAMPLE))
    result = run(mgr.get_articles_by_date_range("2024-06-01", "2024-06-30"))
    assert result.count >= 1


@mock_aws
def test_get_articles_by_tags_any_and_all():
    mgr = make_manager("tags-table")
    run(mgr.index_article_metadata(SAMPLE))
    any_res = run(mgr.get_articles_by_tags(["climate", "unrelated"], match_all=False))
    assert any_res.count >= 1
    all_res = run(mgr.get_articles_by_tags(["climate", "science"], match_all=True))
    assert all_res.count >= 1


@mock_aws
def test_get_articles_by_category():
    mgr = make_manager("bycat-table")
    run(mgr.index_article_metadata(SAMPLE))
    result = run(mgr.get_articles_by_category("science", start_date="2024-01-01"))
    assert result.count >= 1
    assert result.items[0].category == "science"


@mock_aws
def test_get_article_by_id_error_reraised(monkeypatch):
    mgr = make_manager("byiderr-table")

    def boom(**k):
        raise RuntimeError("get fail")

    mgr.table.get_item = boom
    with pytest.raises(RuntimeError, match="get fail"):
        run(mgr.get_article_by_id("x"))


# --------------------------------------------------------------------------
# Full-text search
# --------------------------------------------------------------------------

@mock_aws
def test_search_articles_contains():
    mgr = make_manager("search-table")
    run(mgr.index_article_metadata(SAMPLE))
    query = SearchQuery(query_text="climate science", search_mode=SearchMode.CONTAINS)
    result = run(mgr.search_articles(query))
    assert result.count >= 1
    assert result.query_info["tokens"]


@mock_aws
def test_search_articles_empty_tokens_short_circuit():
    mgr = make_manager("search-empty")
    # Only stop words -> no tokens -> empty result (line ~756-757)
    query = SearchQuery(query_text="the and or")
    result = run(mgr.search_articles(query))
    assert result.count == 0


@mock_aws
def test_search_articles_with_filters_and_date_range():
    mgr = make_manager("search-filt")
    run(mgr.index_article_metadata(SAMPLE))
    query = SearchQuery(
        query_text="climate",
        search_mode=SearchMode.CONTAINS,
        filters={"source": "reuters"},
        date_range={"start": "2024-01-01", "end": "2024-12-31"},
    )
    result = run(mgr.search_articles(query))
    assert result.count >= 1


@mock_aws
def test_search_articles_exact_mode():
    mgr = make_manager("search-exact")
    run(mgr.index_article_metadata(SAMPLE))
    query = SearchQuery(
        query_text=SAMPLE["title"],
        fields=["title"],
        search_mode=SearchMode.EXACT,
    )
    result = run(mgr.search_articles(query))
    assert result.count >= 1


@mock_aws
def test_search_articles_starts_with_mode():
    mgr = make_manager("search-sw")
    run(mgr.index_article_metadata(SAMPLE))
    query = SearchQuery(
        query_text="breaking",
        fields=["title"],
        search_mode=SearchMode.STARTS_WITH,
    )
    # Should execute without error (scoring path exercised)
    result = run(mgr.search_articles(query))
    assert isinstance(result.count, int)


@mock_aws
def test_query_methods_error_reraised():
    mgr = make_manager("qerr-table")

    def boom(**k):
        raise RuntimeError("query fail")

    def boom_scan(**k):
        raise RuntimeError("scan fail")

    mgr.table.query = boom
    mgr.table.scan = boom_scan

    with pytest.raises(RuntimeError, match="query fail"):
        run(mgr.get_articles_by_source("s"))
    with pytest.raises(RuntimeError, match="scan fail"):
        run(mgr.get_articles_by_date_range("2024-01-01", "2024-12-31"))
    with pytest.raises(RuntimeError, match="scan fail"):
        run(mgr.get_articles_by_tags(["t"]))
    with pytest.raises(RuntimeError, match="query fail"):
        run(mgr.get_articles_by_category("c"))


@mock_aws
def test_search_articles_error_reraised():
    mgr = make_manager("serr-table")

    def boom(**k):
        raise RuntimeError("search scan fail")

    mgr.table.scan = boom
    with pytest.raises(RuntimeError, match="search scan fail"):
        run(mgr.search_articles(SearchQuery(query_text="climate")))


@mock_aws
def test_statistics_error_reraised():
    mgr = make_manager("statserr-table")

    def boom(**k):
        raise RuntimeError("stats scan fail")

    mgr.table.scan = boom
    with pytest.raises(RuntimeError, match="stats scan fail"):
        run(mgr.get_metadata_statistics())


def test_build_search_filter_branches():
    mgr = DynamoDBMetadataManager.__new__(DynamoDBMetadataManager)
    # Empty tokens -> None (line 879-880)
    assert (
        DynamoDBMetadataManager._build_search_filter(
            mgr, [], SearchQuery(query_text="x")
        )
        is None
    )
    # EXACT mode, non-title field -> contains branch (line 894)
    q_exact = SearchQuery(
        query_text="climate", fields=["content_summary"], search_mode=SearchMode.EXACT
    )
    expr = DynamoDBMetadataManager._build_search_filter(mgr, ["climate"], q_exact)
    assert expr is not None
    # CONTAINS mode with title_tokens field (line 899)
    q_tok = SearchQuery(
        query_text="climate", fields=["title_tokens"], search_mode=SearchMode.CONTAINS
    )
    expr2 = DynamoDBMetadataManager._build_search_filter(mgr, ["climate"], q_tok)
    assert expr2 is not None
    # No fields -> no field_filters -> None (line 913-914)
    q_none = SearchQuery(query_text="climate", fields=[])
    assert (
        DynamoDBMetadataManager._build_search_filter(mgr, ["climate"], q_none) is None
    )


@mock_aws
def test_search_additional_filters_without_base_token_filter():
    # search_mode with empty fields yields no base filter; additional filters
    # then become the whole expression (lines 769-770). date_range without base
    # exercises 777-778.
    mgr = make_manager("sfnb-table")
    run(mgr.index_article_metadata(SAMPLE))
    q = SearchQuery(
        query_text="climate",
        fields=[],  # no token filter -> filter_expr None after tokens
        filters={"source": "reuters"},
        date_range={"start": "2024-01-01"},
    )
    result = run(mgr.search_articles(q))
    assert isinstance(result.count, int)


@mock_aws
def test_search_date_range_only_without_base_filter():
    # No fields (no token filter) and no additional filters -> filter_expr stays
    # None until date_range makes it the whole expression (lines 777-778).
    mgr = make_manager("sdro-table")
    run(mgr.index_article_metadata(SAMPLE))
    q = SearchQuery(
        query_text="climate",
        fields=[],
        date_range={"start": "2024-01-01", "end": "2024-12-31"},
    )
    result = run(mgr.search_articles(q))
    assert isinstance(result.count, int)


def test_build_additional_filters_list_and_scalar():
    mgr_cls = DynamoDBMetadataManager.__new__(DynamoDBMetadataManager)
    # list value -> OR of eq, scalar -> single eq; then combined with AND
    expr = DynamoDBMetadataManager._build_additional_filters(
        mgr_cls, {"source": ["a", "b"], "category": "news"}
    )
    assert expr is not None


def test_build_date_range_filter_variants():
    mgr_cls = DynamoDBMetadataManager.__new__(DynamoDBMetadataManager)
    both = DynamoDBMetadataManager._build_date_range_filter(
        mgr_cls, {"start": "2024-01-01", "end": "2024-12-31"}
    )
    assert both is not None
    end_only = DynamoDBMetadataManager._build_date_range_filter(
        mgr_cls, {"end": "2024-12-31"}
    )
    assert end_only is not None
    empty = DynamoDBMetadataManager._build_date_range_filter(mgr_cls, {})
    assert empty is None


def test_calculate_relevance_score():
    mgr_cls = DynamoDBMetadataManager.__new__(DynamoDBMetadataManager)
    item = ArticleMetadataIndex(
        article_id="x", content_hash="h",
        title="climate change report",
        source="s", published_date="2024-01-01",
        tags=["climate"],
    )
    score = DynamoDBMetadataManager._calculate_relevance_score(
        mgr_cls, item, ["climate"], ["title", "tags"]
    )
    assert score > 0


def test_tokenize_search_query_filters_stopwords():
    mgr_cls = DynamoDBMetadataManager.__new__(DynamoDBMetadataManager)
    tokens = DynamoDBMetadataManager._tokenize_search_query(
        mgr_cls, "The climate and science"
    )
    assert "the" not in tokens
    assert "climate" in tokens
    assert "science" in tokens


# --------------------------------------------------------------------------
# Statistics / update / delete / health
# --------------------------------------------------------------------------

@mock_aws
def test_get_metadata_statistics():
    mgr = make_manager("stats-table")
    run(mgr.index_article_metadata(SAMPLE))
    run(mgr.index_article_metadata({**SAMPLE, "id": "a2", "source": "bbc"}))
    stats = run(mgr.get_metadata_statistics())
    assert stats["total_articles"] == 2
    assert "reuters" in stats["source_distribution"]
    assert stats["table_info"]["table_name"] == "stats-table"


@mock_aws
def test_update_article_metadata():
    mgr = make_manager("upd-table")
    run(mgr.index_article_metadata(SAMPLE))
    ok = run(mgr.update_article_metadata("a1", {"processing_status": "processed"}))
    assert ok is True
    updated = run(mgr.get_article_by_id("a1"))
    assert updated.processing_status == "processed"


@mock_aws
def test_update_article_metadata_error_returns_false(monkeypatch):
    mgr = make_manager("upderr-table")

    def boom(**k):
        raise RuntimeError("update fail")

    mgr.table.update_item = boom
    assert run(mgr.update_article_metadata("a1", {"x": 1})) is False


@mock_aws
def test_delete_article_metadata():
    mgr = make_manager("del-table")
    run(mgr.index_article_metadata(SAMPLE))
    assert run(mgr.delete_article_metadata("a1")) is True
    assert run(mgr.get_article_by_id("a1")) is None


@mock_aws
def test_delete_article_metadata_error_returns_false():
    mgr = make_manager("delerr-table")

    def boom(**k):
        raise RuntimeError("delete fail")

    mgr.table.delete_item = boom
    assert run(mgr.delete_article_metadata("a1")) is False


@mock_aws
def test_health_check_healthy():
    mgr = make_manager("health-table")
    health = run(mgr.health_check())
    assert health["status"] == "healthy"
    assert health["table_status"] == "ACTIVE"
    assert health["table_name"] == "health-table"


@mock_aws
def test_health_check_unhealthy_on_error(monkeypatch):
    mgr = make_manager("health-err")

    def boom(**k):
        raise RuntimeError("describe fail")

    mgr.table.meta.client.describe_table = boom
    health = run(mgr.health_check())
    assert health["status"] == "unhealthy"
    assert "error" in health


# --------------------------------------------------------------------------
# Integration helpers
# --------------------------------------------------------------------------

@mock_aws
def test_integrate_with_s3_storage_maps_fields(monkeypatch):
    mgr = make_manager("s3int-table")
    s3_meta = {
        "article_id": "s3a1",
        "title": "S3 Article",
        "source": "src",
        "published_date": "2024-05-05",
        "url": "http://x/s3",
        "s3_key": "raw/x.json",
        "content_hash": "hh",
        "scraped_date": "2024-05-05T00:00:00Z",
        "processing_status": "stored",
    }

    # NOTE (genuine source limitation): integrate_with_s3_storage does not carry
    # a category, so the DynamoDB item has category="" which the category GSI
    # rejects. To assert the S3->DynamoDB field mapping (lines 1178-1190) in
    # isolation, capture the article_data handed to index_article_metadata.
    captured = {}

    async def fake_index(article_data):
        captured.update(article_data)
        return ArticleMetadataIndex(
            article_id=article_data["id"],
            content_hash=article_data["content_hash"],
            title=article_data["title"],
            source=article_data["source"],
            published_date=article_data["published_date"],
            s3_key=article_data["s3_key"],
        )

    monkeypatch.setattr(mgr, "index_article_metadata", fake_index)
    meta = run(integrate_with_s3_storage(s3_meta, mgr))
    assert meta.article_id == "s3a1"
    assert meta.s3_key == "raw/x.json"
    # Mapping assertions
    assert captured["id"] == "s3a1"
    assert captured["source"] == "src"
    assert captured["processing_status"] == "stored"


@mock_aws
def test_integrate_with_redshift_etl():
    mgr = make_manager("rsint-table")
    run(mgr.index_article_metadata(SAMPLE))
    ok = run(integrate_with_redshift_etl({"article_id": "a1"}, mgr))
    assert ok is True
    updated = run(mgr.get_article_by_id("a1"))
    assert updated.redshift_loaded is True


@mock_aws
def test_integrate_with_redshift_etl_no_id():
    mgr = make_manager("rsint2-table")
    # Missing article_id -> returns False early
    assert run(integrate_with_redshift_etl({}, mgr)) is False


@mock_aws
def test_sync_metadata_from_scraper():
    mgr = make_manager("sync-table")
    articles = [
        {"id": "sy1", "title": "T1", "content": "c", "source": "s",
         "published_date": "2024-01-01"},
    ]
    result = run(sync_metadata_from_scraper(articles, mgr))
    assert result["indexed_count"] == 1
