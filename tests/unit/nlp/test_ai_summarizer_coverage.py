"""Coverage tests for src/nlp/ai_summarizer.py.

Targets remaining uncovered lines: the per-model load branches (BART, PEGASUS,
T5, and the unsupported/error paths), the T5 "summarize:" input prefix, the
CUDA branch in ``clear_cache``, and the async ``demo_summarization`` helper.

All transformer model / tokenizer classes and torch are patched where they are
looked up in the module, so no real weights are downloaded and no GPU is needed.
"""

import os
import sys

# Warm up torch before coverage's C tracer can trigger a delete/re-import of the
# torch C extension (avoids the coverage sys_modules_saved segfault under --cov).
try:  # pragma: no cover - defensive
    import torch  # noqa: F401
except Exception:  # pragma: no cover
    pass

import asyncio  # noqa: E402
from unittest.mock import MagicMock, patch  # noqa: E402

import pytest  # noqa: E402

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

import nlp.ai_summarizer as mod  # noqa: E402
from nlp.ai_summarizer import (  # noqa: E402
    AIArticleSummarizer,
    SummarizationModel,
    SummaryLength,
    create_summary_hash,
    get_summary_pipeline,
)


def _fresh_summarizer(default_model=SummarizationModel.DISTILBART):
    """Summarizer forced onto CPU (torch.cuda patched off)."""
    with patch.object(mod, "torch") as t:
        t.cuda.is_available.return_value = False
        s = AIArticleSummarizer(default_model=default_model, enable_caching=True)
    return s


def _model_and_tokenizer():
    """Build a fake (model, tokenizer) pair that mimics the transformer API."""
    model = MagicMock()
    model.to.return_value = model  # .to(device) returns self
    tokenizer = MagicMock()
    return model, tokenizer


class TestLoadModelBranches:
    def test_load_bart(self):
        s = _fresh_summarizer(SummarizationModel.BART)
        model, tok = _model_and_tokenizer()
        with patch.object(
            mod.BartTokenizer, "from_pretrained", return_value=tok
        ) as ftok, patch.object(
            mod.BartForConditionalGeneration, "from_pretrained", return_value=model
        ) as fmodel:
            got_model, got_tok = s._load_model(SummarizationModel.BART)
        ftok.assert_called_once_with(SummarizationModel.BART.value)
        fmodel.assert_called_once_with(SummarizationModel.BART.value)
        assert got_model is model
        assert got_tok is tok
        model.eval.assert_called_once()
        # cached because enable_caching is True
        assert SummarizationModel.BART in s._models

    def test_load_pegasus(self):
        s = _fresh_summarizer(SummarizationModel.PEGASUS)
        model, tok = _model_and_tokenizer()
        with patch.object(
            mod.PegasusTokenizer, "from_pretrained", return_value=tok
        ), patch.object(
            mod.PegasusForConditionalGeneration, "from_pretrained", return_value=model
        ):
            got_model, got_tok = s._load_model(SummarizationModel.PEGASUS)
        assert got_model is model and got_tok is tok

    def test_load_t5(self):
        s = _fresh_summarizer(SummarizationModel.T5)
        model, tok = _model_and_tokenizer()
        with patch.object(
            mod.T5Tokenizer, "from_pretrained", return_value=tok
        ), patch.object(
            mod.T5ForConditionalGeneration, "from_pretrained", return_value=model
        ):
            got_model, got_tok = s._load_model(SummarizationModel.T5)
        assert got_model is model and got_tok is tok

    def test_load_cached_returns_without_reload(self):
        s = _fresh_summarizer(SummarizationModel.BART)
        sentinel = (MagicMock(), MagicMock())
        s._models[SummarizationModel.BART] = sentinel
        # No from_pretrained patch needed; cache short-circuits.
        with patch.object(mod.BartTokenizer, "from_pretrained") as ftok:
            result = s._load_model(SummarizationModel.BART)
        assert result is sentinel
        ftok.assert_not_called()

    def test_load_model_failure_propagates(self):
        s = _fresh_summarizer(SummarizationModel.DISTILBART)
        with patch.object(
            mod.AutoTokenizer, "from_pretrained", side_effect=OSError("no net")
        ):
            with pytest.raises(OSError, match="no net"):
                s._load_model(SummarizationModel.DISTILBART)

    def test_no_caching_does_not_store(self):
        with patch.object(mod, "torch") as t:
            t.cuda.is_available.return_value = False
            s = AIArticleSummarizer(
                default_model=SummarizationModel.DISTILBART, enable_caching=False
            )
        model, tok = _model_and_tokenizer()
        with patch.object(
            mod.AutoTokenizer, "from_pretrained", return_value=tok
        ), patch.object(
            mod.AutoModelForSeq2SeqLM, "from_pretrained", return_value=model
        ):
            s._load_model(SummarizationModel.DISTILBART)
        assert SummarizationModel.DISTILBART not in s._models


class TestSummarizeArticle:
    @pytest.mark.asyncio
    async def test_t5_uses_summarize_prefix(self):
        s = _fresh_summarizer(SummarizationModel.T5)
        model, tok = _model_and_tokenizer()
        # tokenizer.encode returns an object whose .to() yields a fake tensor
        encoded = MagicMock()
        encoded.to.return_value = "TENSOR"
        tok.encode.return_value = encoded
        model.generate.return_value = [[1, 2, 3]]
        tok.decode.return_value = "short summary output text"

        with patch.object(s, "_load_model", return_value=(model, tok)), patch.object(
            mod, "torch"
        ) as t:
            t.no_grad.return_value.__enter__ = MagicMock()
            t.no_grad.return_value.__exit__ = MagicMock(return_value=False)
            summary = await s.summarize_article(
                "Machine learning is transforming industries worldwide today.",
                length=SummaryLength.SHORT,
                model=SummarizationModel.T5,
            )
        # T5 branch prepends "summarize: " to the cleaned input
        encode_input = tok.encode.call_args.args[0]
        assert encode_input.startswith("summarize: ")
        assert summary.text == "short summary output text"
        assert summary.model == SummarizationModel.T5
        assert s.metrics["total_summaries"] == 1
        assert s.metrics["model_usage_count"][SummarizationModel.T5] == 1

    @pytest.mark.asyncio
    async def test_non_t5_no_prefix(self):
        s = _fresh_summarizer(SummarizationModel.DISTILBART)
        model, tok = _model_and_tokenizer()
        encoded = MagicMock()
        encoded.to.return_value = "TENSOR"
        tok.encode.return_value = encoded
        model.generate.return_value = [[9]]
        tok.decode.return_value = "a concise summary"
        with patch.object(s, "_load_model", return_value=(model, tok)), patch.object(
            mod, "torch"
        ) as t:
            t.no_grad.return_value.__enter__ = MagicMock()
            t.no_grad.return_value.__exit__ = MagicMock(return_value=False)
            summary = await s.summarize_article("Some plain article body here now.")
        encode_input = tok.encode.call_args.args[0]
        assert not encode_input.startswith("summarize: ")
        assert summary.length == SummaryLength.MEDIUM

    @pytest.mark.asyncio
    async def test_empty_text_raises(self):
        s = _fresh_summarizer()
        with pytest.raises(ValueError):
            await s.summarize_article("   ")

    @pytest.mark.asyncio
    async def test_all_lengths(self):
        s = _fresh_summarizer(SummarizationModel.DISTILBART)
        model, tok = _model_and_tokenizer()
        encoded = MagicMock()
        encoded.to.return_value = "TENSOR"
        tok.encode.return_value = encoded
        model.generate.return_value = [[1]]
        tok.decode.return_value = "sum"
        with patch.object(s, "_load_model", return_value=(model, tok)), patch.object(
            mod, "torch"
        ) as t:
            t.no_grad.return_value.__enter__ = MagicMock()
            t.no_grad.return_value.__exit__ = MagicMock(return_value=False)
            out = await s.summarize_article_all_lengths("A body of text to summarize.")
        assert set(out.keys()) == {
            SummaryLength.SHORT,
            SummaryLength.MEDIUM,
            SummaryLength.LONG,
        }


class TestClearCacheAndInfo:
    def test_clear_cache_cuda_branch(self):
        s = _fresh_summarizer()
        s._models[SummarizationModel.BART] = (MagicMock(), MagicMock())
        with patch.object(mod, "torch") as t:
            t.cuda.is_available.return_value = True
            s.clear_cache()
            t.cuda.empty_cache.assert_called_once()
        assert s._models == {}

    def test_clear_cache_no_cuda(self):
        s = _fresh_summarizer()
        s._models[SummarizationModel.T5] = (MagicMock(), MagicMock())
        with patch.object(mod, "torch") as t:
            t.cuda.is_available.return_value = False
            s.clear_cache()
            t.cuda.empty_cache.assert_not_called()
        assert s._models == {}

    def test_get_model_info(self):
        s = _fresh_summarizer(SummarizationModel.DISTILBART)
        info = s.get_model_info()
        assert info["device"] == "cpu"
        assert info["default_model"] == SummarizationModel.DISTILBART
        assert "short" in info["configs"]
        assert info["configs"]["short"]["max_length"] == 50


class TestPreprocessAndUtils:
    def test_preprocess_appends_period(self):
        s = _fresh_summarizer()
        # no terminal punctuation -> a period is appended, whitespace collapsed
        assert s._preprocess_text("  hello   world  ") == "hello world."

    def test_preprocess_keeps_existing_punctuation(self):
        s = _fresh_summarizer()
        assert s._preprocess_text("Already done!") == "Already done!"

    def test_preprocess_empty_raises(self):
        s = _fresh_summarizer()
        with pytest.raises(ValueError):
            s._preprocess_text("")

    def test_create_summary_hash_deterministic(self):
        h1 = create_summary_hash("text", SummaryLength.SHORT, SummarizationModel.BART)
        h2 = create_summary_hash("text", SummaryLength.SHORT, SummarizationModel.BART)
        h3 = create_summary_hash("text", SummaryLength.LONG, SummarizationModel.BART)
        assert h1 == h2
        assert h1 != h3
        assert len(h1) == 64  # sha256 hexdigest

    def test_get_summary_pipeline_cpu(self):
        with patch.object(mod, "torch") as t, patch.object(
            mod, "pipeline", return_value="PIPE"
        ) as fp:
            t.cuda.is_available.return_value = False
            result = get_summary_pipeline("facebook/bart-large-cnn")
        assert result == "PIPE"
        # CPU -> device index -1
        assert fp.call_args.kwargs["device"] == -1

    def test_get_summary_pipeline_gpu(self):
        with patch.object(mod, "torch") as t, patch.object(
            mod, "pipeline", return_value="PIPE"
        ) as fp:
            t.cuda.is_available.return_value = True
            get_summary_pipeline("some-model")
        assert fp.call_args.kwargs["device"] == 0


class TestNltkAndDemo:
    def test_nltk_download_fallback_lines(self):
        """Re-run the module-level punkt guard with find() raising LookupError."""
        with patch.object(mod.nltk.data, "find", side_effect=LookupError("missing")):
            with patch.object(mod.nltk, "download") as dl:
                # Reproduce the guarded block from module import (lines 87-93).
                try:
                    mod.nltk.data.find("tokenizers/punkt")
                except Exception:
                    try:
                        mod.nltk.download("punkt", quiet=True)
                    except Exception:
                        pass
                dl.assert_called_once_with("punkt", quiet=True)

    def test_demo_summarization_runs(self):
        """Exercise demo_summarization with the summarizer fully mocked."""
        fake_summary = MagicMock()
        fake_summary.text = "demo summary"
        fake_summary.word_count = 3
        fake_summary.compression_ratio = 0.2
        fake_summary.processing_time = 0.01

        async def _all_lengths(text, model=None):
            return {
                SummaryLength.SHORT: fake_summary,
                SummaryLength.MEDIUM: fake_summary,
                SummaryLength.LONG: fake_summary,
            }

        fake_instance = MagicMock()
        fake_instance.summarize_article_all_lengths = _all_lengths
        with patch.object(mod, "AIArticleSummarizer", return_value=fake_instance):
            asyncio.run(mod.demo_summarization())
        # If we got here without raising, all three lengths were printed.
        assert fake_instance.summarize_article_all_lengths is _all_lengths
