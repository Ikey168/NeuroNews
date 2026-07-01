"""Coverage-focused tests for src/apps/streamlit/pages/02_Ask_the_News.py.

The page is a top-to-bottom Streamlit script (no functions to import), so we
drive it by executing its source in a controlled namespace where ``streamlit``
is a ``MagicMock``.  Layout helpers (``columns``, ``container``, ``expander``,
``spinner``) are wired up as context managers and the inputs (``text_area``,
``button``, ``date_input`` ...) return deterministic values so we can steer the
script down each branch and assert on the render calls that were made.

Two rendering modes are covered:
  * demo mode  - RAG services genuinely unavailable in this env (mlflow missing)
  * real mode  - fake ``services.api.routes.ask`` / ``services.rag.answer``
                 modules injected so RAG_AVAILABLE becomes True and the real
                 ``ask_question`` path runs.
"""

import builtins
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

# streamlit must be present for these tests to make sense.
pytest.importorskip("streamlit")

PAGE_PATH = "/home/user/Noesis/src/apps/streamlit/pages/02_Ask_the_News.py"

with open(PAGE_PATH, "r") as _f:
    PAGE_SOURCE = _f.read()
PAGE_CODE = compile(PAGE_SOURCE, PAGE_PATH, "exec")


class _CtxManager:
    """A context manager whose ``__enter__`` yields a fresh MagicMock.

    Used for ``st.spinner``/``st.container``/``st.expander`` and for the entries
    returned by ``st.columns`` so that ``with col1:`` blocks execute.
    """

    def __enter__(self):
        return MagicMock()

    def __exit__(self, *exc):
        return False


def _make_st():
    """Build a MagicMock configured to stand in for the streamlit module."""
    st = MagicMock(name="streamlit")

    # Context-manager helpers.
    st.spinner.return_value = _CtxManager()
    st.container.return_value = _CtxManager()
    st.expander.return_value = _CtxManager()

    # Sidebar is itself a namespace of widgets.
    st.sidebar = MagicMock(name="st.sidebar")

    # columns() must return an iterable of context managers.
    st.columns.return_value = [_CtxManager(), _CtxManager(), _CtxManager()]
    st.sidebar.columns.return_value = [_CtxManager(), _CtxManager()]

    # Default widget values (overridden per-test as needed).
    date_obj = MagicMock(name="date")
    date_obj.isoformat.return_value = "2024-01-01"
    st.date_input.return_value = date_obj
    st.sidebar.text_area.return_value = "What is happening in AI?"
    st.sidebar.text_input.return_value = ""

    # selectbox is used twice (Language then Answer Provider); return a value
    # appropriate to each based on its label so ``language`` != ``provider``.
    def _selectbox(label, *args, **kwargs):
        if "Language" in label:
            return "en"
        return "openai"

    st.sidebar.selectbox.side_effect = _selectbox
    st.sidebar.slider.return_value = 5
    st.sidebar.checkbox.return_value = True
    st.button.return_value = False
    st.checkbox.return_value = True
    return st


def _make_rag_modules(response):
    """Fabricate ``services.api.routes.ask`` and ``services.rag.answer``.

    Injected into ``sys.modules`` so the page's ``try: from services...`` import
    succeeds and RAG_AVAILABLE becomes True.
    """
    ask_mod = types.ModuleType("services.api.routes.ask")

    class AskRequest:
        def __init__(self, **kwargs):
            self._kwargs = kwargs

        def dict(self):
            return self._kwargs

    async def ask_question(request, rag_service):
        return response

    def get_rag_service():
        return MagicMock(name="rag_service")

    ask_mod.AskRequest = AskRequest
    ask_mod.ask_question = ask_question
    ask_mod.get_rag_service = get_rag_service

    answer_mod = types.ModuleType("services.rag.answer")
    answer_mod.RAGAnswerService = MagicMock(name="RAGAnswerService")
    return ask_mod, answer_mod


def _run_page(st, *, rag_modules=None, block_plotly=False, extra_sys_modules=None):
    """Execute the page source with ``st`` standing in for streamlit.

    Returns the globals dict the script populated so callers can inspect the
    module-level flags (RAG_AVAILABLE, PLOTLY_AVAILABLE, ...).
    """
    saved = {}
    to_restore_keys = ["streamlit", "services.api.routes.ask", "services.rag.answer"]
    for key in to_restore_keys:
        saved[key] = sys.modules.get(key)

    sys.modules["streamlit"] = st
    if rag_modules is not None:
        sys.modules["services.api.routes.ask"] = rag_modules[0]
        sys.modules["services.rag.answer"] = rag_modules[1]
    else:
        # Ensure the real (import-failing) modules are attempted so RAG stays off.
        sys.modules.pop("services.api.routes.ask", None)
        sys.modules.pop("services.rag.answer", None)

    if extra_sys_modules:
        for k, v in extra_sys_modules.items():
            saved.setdefault(k, sys.modules.get(k))
            sys.modules[k] = v

    real_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if block_plotly and name.startswith("plotly"):
            raise ImportError("plotly blocked for test")
        return real_import(name, *args, **kwargs)

    glob = {"__name__": "ask_the_news_page", "__file__": PAGE_PATH}
    with patch("time.sleep", lambda *a, **k: None):
        if block_plotly:
            for mod_name in list(sys.modules):
                if mod_name.startswith("plotly"):
                    sys.modules.pop(mod_name, None)
            with patch("builtins.__import__", side_effect=guarded_import):
                exec(PAGE_CODE, glob)
        else:
            exec(PAGE_CODE, glob)

    # Restore sys.modules.
    for key, val in saved.items():
        if val is None:
            sys.modules.pop(key, None)
        else:
            sys.modules[key] = val
    return glob


# ---------------------------------------------------------------------------
# Page scaffolding (runs regardless of the Ask button).
# ---------------------------------------------------------------------------
class TestPageScaffolding:
    def test_button_not_pressed_renders_shell_only(self):
        st = _make_st()
        st.button.return_value = False
        glob = _run_page(st)

        # Title + page config were rendered.
        st.set_page_config.assert_called_once()
        st.title.assert_called_once()
        title_arg = st.title.call_args.args[0]
        assert "Ask the News" in title_arg

        # Sidebar inputs were built.
        assert st.sidebar.text_area.called
        assert st.sidebar.slider.called
        assert st.sidebar.selectbox.called

        # Body never ran: no answer header, no success banner.
        assert not st.success.called
        header_titles = [c.args[0] for c in st.header.call_args_list]
        assert "📝 Answer" not in header_titles

    def test_rag_unavailable_marks_demo_mode(self):
        # mlflow is genuinely missing in this env, so RAG_AVAILABLE is False.
        st = _make_st()
        st.button.return_value = False
        glob = _run_page(st)
        assert glob["RAG_AVAILABLE"] is False
        # Demo-mode warning/info were surfaced.
        assert st.warning.called
        assert st.info.called

    def test_example_questions_rendered_in_sidebar(self):
        st = _make_st()
        st.button.return_value = False
        _run_page(st)
        captions = [c.args[0] for c in st.sidebar.caption.call_args_list]
        # Five numbered example questions get captioned.
        numbered = [c for c in captions if c.startswith("**")]
        assert len(numbered) >= 5


# ---------------------------------------------------------------------------
# Demo mode body (RAG unavailable, mock response path).
# ---------------------------------------------------------------------------
class TestDemoModeBody:
    def test_demo_mode_renders_answer_and_citations(self):
        st = _make_st()
        st.button.return_value = True
        st.checkbox.return_value = True  # demo_mode toggle on
        glob = _run_page(st)

        assert glob["RAG_AVAILABLE"] is False
        # Success banner shown.
        assert st.success.called
        # The three analysis panels were rendered.
        header_titles = [c.args[0] for c in st.header.call_args_list]
        assert "📝 Answer" in header_titles
        assert "📚 Citations" in header_titles
        assert "🔧 Retrieval Debug" in header_titles

        # Citations dataframe + retrieval metrics were produced.
        assert st.dataframe.called
        assert st.metric.called

    def test_demo_mode_uses_plotly_charts_when_available(self):
        st = _make_st()
        st.button.return_value = True
        st.checkbox.return_value = True
        glob = _run_page(st)
        assert glob["PLOTLY_AVAILABLE"] is True
        # Time-breakdown + relevance-score charts.
        assert st.plotly_chart.call_count >= 2

    def test_demo_mode_raw_debug_hits_exception_handler(self):
        # In demo mode ``request`` is never defined, so building the raw-debug
        # JSON raises NameError which the outer try/except catches -> st.exception.
        st = _make_st()
        st.button.return_value = True
        st.checkbox.return_value = True
        _run_page(st)
        assert st.exception.called
        # st.json is only reached in the real path, not demo.
        assert not st.json.called

    def test_empty_query_short_circuits(self):
        st = _make_st()
        st.button.return_value = True
        st.sidebar.text_area.return_value = "    "  # whitespace-only
        # st.stop halts execution in Streamlit; emulate with an exception.
        st.stop.side_effect = RuntimeError("streamlit-stop")
        with pytest.raises(RuntimeError, match="streamlit-stop"):
            _run_page(st)
        assert st.error.called
        error_msg = st.error.call_args.args[0]
        assert "Please enter a question" in error_msg
        assert st.stop.called
        # Analysis never started.
        assert not st.success.called


# ---------------------------------------------------------------------------
# Real mode body (RAG services injected).
# ---------------------------------------------------------------------------
def _fake_response():
    resp = MagicMock(name="AskResponse")
    resp.question = "What is happening in AI?"
    resp.answer = "A detailed synthesized answer about AI developments."
    resp.citations = [
        {
            "title": "Article One",
            "source": "Reuters",
            "url": "https://example.com/1",
            "relevance_score": 0.91,
            "published_date": "2024-05-01",
            "excerpt": "excerpt one",
            "citation_strength": 0.8,
        },
        {
            "title": "Article Two",
            "source": "BBC",
            "url": "https://example.com/2",
            "relevance_score": 0.77,
            "published_date": "2024-05-02",
            "excerpt": "excerpt two",
            "citation_strength": 0.7,
        },
    ]
    resp.metadata = {
        "documents_retrieved": 5,
        "provider_used": "openai",
        "rerank_enabled": True,
        "fusion_enabled": True,
        "retrieval_time_ms": 10.0,
        "rerank_time_ms": 5.0,
        "answer_time_ms": 20.0,
        "total_time_ms": 35.0,
    }
    resp.tracked_in_mlflow = True
    resp.request_id = "req-123"
    return resp


class TestRealModeBody:
    def test_real_mode_renders_full_pipeline(self):
        resp = _fake_response()
        st = _make_st()
        st.button.return_value = True
        st.checkbox.return_value = False  # demo toggle irrelevant when RAG on
        glob = _run_page(st, rag_modules=_make_rag_modules(resp))

        assert glob["RAG_AVAILABLE"] is True
        assert st.success.called
        # Question + answer were written out.
        assert st.write.called
        write_calls = [c.args[0] for c in st.write.call_args_list if c.args]
        assert resp.answer in write_calls

        # Real path renders the raw-debug JSON (request.dict() succeeds).
        assert st.json.called
        raw_debug = st.json.call_args.args[0]
        assert raw_debug["response_summary"]["citations_count"] == 2
        assert raw_debug["response_summary"]["request_id"] == "req-123"
        # No exception in the happy path.
        assert not st.exception.called

    def test_real_mode_builds_askrequest_with_filters(self):
        resp = _fake_response()
        ask_mod, answer_mod = _make_rag_modules(resp)
        st = _make_st()
        st.button.return_value = True
        st.sidebar.text_input.return_value = "reuters"  # source filter set
        glob = _run_page(st, rag_modules=(ask_mod, answer_mod))

        assert glob["RAG_AVAILABLE"] is True
        # The rendered raw-debug request must carry the source filter and lang.
        raw_debug = st.json.call_args.args[0]
        request_dict = raw_debug["request"]
        assert request_dict["filters"]["source"] == "reuters"
        assert request_dict["filters"]["lang"] == "en"
        assert request_dict["question"] == "What is happening in AI?"

    def test_real_mode_no_citations_warns(self):
        resp = _fake_response()
        resp.citations = []  # empty citation list -> "No citations found" branch
        st = _make_st()
        st.button.return_value = True
        glob = _run_page(st, rag_modules=_make_rag_modules(resp))

        assert glob["RAG_AVAILABLE"] is True
        warnings = [c.args[0] for c in st.warning.call_args_list if c.args]
        assert "No citations found." in warnings
        # Debug panel still renders even with no citations.
        header_titles = [c.args[0] for c in st.header.call_args_list]
        assert "🔧 Retrieval Debug" in header_titles

    def test_real_mode_show_chunks_button_expands_citations(self):
        resp = _fake_response()
        st = _make_st()

        # Outer "Ask" button True; nested "Show Matched Text Chunks" button True.
        def _button(label, *args, **kwargs):
            return True  # both the Ask and Show-Chunks buttons are pressed

        st.button.side_effect = _button
        glob = _run_page(st, rag_modules=_make_rag_modules(resp))

        assert glob["RAG_AVAILABLE"] is True
        # The matched-chunks subheader was rendered and per-citation expanders opened.
        subheaders = [c.args[0] for c in st.subheader.call_args_list if c.args]
        assert "Matched Text Chunks" in subheaders
        # One expander per citation (2) for the chunk view, plus raw-debug expander.
        assert st.expander.call_count >= len(resp.citations)

    def test_real_mode_error_is_surfaced(self):
        # Force ask_question to raise so the except branch renders the error.
        ask_mod, answer_mod = _make_rag_modules(_fake_response())

        async def boom(request, rag_service):
            raise RuntimeError("rag exploded")

        ask_mod.ask_question = boom
        st = _make_st()
        st.button.return_value = True
        glob = _run_page(st, rag_modules=(ask_mod, answer_mod))

        assert glob["RAG_AVAILABLE"] is True
        assert st.error.called
        error_msg = st.error.call_args.args[0]
        assert "Error processing query" in error_msg
        assert st.exception.called


# ---------------------------------------------------------------------------
# Plotly-unavailable fallback (tables instead of charts).
# ---------------------------------------------------------------------------
class TestPlotlyUnavailable:
    def test_plotly_import_failure_falls_back_to_tables(self):
        resp = _fake_response()
        st = _make_st()
        st.button.return_value = True
        glob = _run_page(st, rag_modules=_make_rag_modules(resp), block_plotly=True)

        assert glob["PLOTLY_AVAILABLE"] is False
        # A warning about plotly is emitted at import time.
        warnings = [c.args[0] for c in st.warning.call_args_list if c.args]
        assert any("Plotly" in w for w in warnings)
        # Charts are never drawn; tables are used instead.
        assert not st.plotly_chart.called
        assert st.dataframe.called
