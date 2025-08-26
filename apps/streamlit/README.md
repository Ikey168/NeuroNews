# NeuroNews Streamlit App

This directory contains the Streamlit-based UI for NeuroNews, including the "Ask the News" debug interface.

## Structure

- `Home.py` - Main entry point for the Streamlit app
- `pages/02_Ask_the_News.py` - Ask the News question-answering interface
- `requirements.txt` - Streamlit-specific dependencies

## Running the App

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Run the Streamlit app:
```bash
streamlit run Home.py
```

3. Open your browser to `http://localhost:8501`

## Ask the News Features

The Ask the News page (Issue #234) provides:

### Inputs
- **Query**: Natural language question
- **Date Range**: Filter articles by publication date  
- **Language**: Select article language (en, es, fr, de, it, pt)
- **K**: Number of documents to retrieve (1-20)
- **Rerank Toggle**: Enable/disable cross-encoder reranking
- **Fusion Toggle**: Enable/disable query fusion (vector + lexical)
- **Provider**: Choose LLM provider (openai, anthropic, local)
- **Source Filter**: Optional filter by news source

### Panels
- **Final Answer**: Generated response to the question
- **Citations List**: Sources with relevance scores and metadata
- **Retrieval Debug**: Performance metrics, timing breakdown, scores
- **Show Chunks**: Preview of matched text segments

### Debug Features
- Relevance score visualization
- Processing time breakdown chart
- Raw metadata inspection
- MLflow tracking status

## Technical Details

The app integrates with:
- `services/api/routes/ask.py` - FastAPI ask endpoint
- `services/rag/answer.py` - RAG answer service
- MLflow tracking for experiment monitoring
- Vector + lexical search with optional reranking

## DoD Requirements (Issue #234)

✅ **Inputs**: query, date range, lang, K, rerank toggle  
✅ **Panels**: final answer, citations list, retrieval debug (scores, fusion weights), time breakdown  
✅ **Button**: "Show chunks" to preview matched text  
✅ **Manual query works end-to-end**

## Screenshots

Screenshots for documentation should be added to `docs/` after testing.
