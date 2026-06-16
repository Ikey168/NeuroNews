![Airflow DAG Check](https://github.com/Ikey168/NeuroNews/actions/workflows/airflow-dag-check.yml/badge.svg)
![MLflow CI](https://github.com/Ikey168/NeuroNews/actions/workflows/mlops-ci.yml/badge.svg)

# NeuroNews - AI-Powered News Intelligence Pipeline

Real-time ETL pipeline for politics and technology news, with AI-driven insights,
sentiment analysis, and trend detection.

---

## Overview

NeuroNews is an ETL pipeline that scrapes, analyzes, and visualizes politics and
technology news using NLP, sentiment analysis, and knowledge-graph-based insights.
It runs entirely against local, self-hostable services - object storage, a
document/metadata store, and a graph database - so it can be developed and tested
without any managed cloud account. Each backend speaks a standard protocol, so the
same code runs against a local emulator in development and a hosted equivalent in
production by changing only an endpoint.

---

## Features

- Automated news scraping - extracts articles from multiple sources using Scrapy
  with optional Playwright/Selenium rendering.
- AI-powered event detection - clusters related articles into significant
  political and technology events.
- NLP and sentiment analysis - extracts named entities, sentiment scores, and
  keyword/topic trends.
- Knowledge graph integration - links entities, policies, and historical context
  using a Gremlin-compatible graph database.
- Custom dashboards and reports - interactive visualizations and AI-driven
  summaries via Streamlit.
- Historical news context - tracks the timeline-based evolution of news topics.
- REST API for insights - structured access to event summaries, trends, and
  sentiment data.

---

## Architecture (local-first)

NeuroNews replaces managed cloud services with local, standards-compatible
alternatives. No proprietary cloud SDK calls are required to run the stack.

| Concern             | Local backend                                             |
| ------------------- | --------------------------------------------------------- |
| Object storage      | S3-compatible store (e.g. MinIO) via a configurable endpoint |
| Article metadata    | DynamoDB-compatible store (e.g. DynamoDB Local)           |
| Knowledge graph     | Gremlin server (e.g. TinkerPop/JanusGraph), `NEPTUNE_ENDPOINT` |
| Analytics warehouse | Local Snowflake-compatible connector                      |
| Streaming ingest    | Kafka (`bootstrap.servers` defaults to `localhost:9092`)  |
| Vector search       | Qdrant and PostgreSQL/pgvector                            |
| Alerting & metrics  | Local JSON/log files (no managed monitoring service)      |
| Request firewall    | In-process WAF (SQL-injection / XSS detection)            |
| Sentiment & translation | Local Python models and lexicons                      |

Endpoints are environment-driven (for example `S3_ENDPOINT_URL`,
`DYNAMODB_ENDPOINT_URL`, `NEPTUNE_ENDPOINT`, `AWS_ENDPOINT_URL`), defaulting to
localhost so the system works out of the box for development and tests.

---

## Use Cases

- Journalists and analysts - quick access to AI-generated summaries and sentiment
  shifts.
- Policy makers and think tanks - track legislative impact and policy evolution.
- Business intelligence teams - analyze technology trends and company sentiment.
- Researchers and data scientists - leverage knowledge-graph insights and
  historical data.

---

## Tech Stack

- Backend and scraping: Python, Scrapy, Selenium, Playwright, FastAPI.
- NLP and AI: Hugging Face Transformers, sentence-transformers, scikit-learn.
- Storage: S3-compatible object storage, DynamoDB-compatible metadata store,
  PostgreSQL, Qdrant.
- Event detection and summarization: embeddings, k-means / LDA clustering.
- Visualization and reporting: Streamlit, Plotly.
- Orchestration and MLOps: Apache Airflow, MLflow.

---

## Getting Started

### Project structure

See [`docs/PROJECT_STRUCTURE.md`](docs/PROJECT_STRUCTURE.md) for a detailed
overview of the directory layout and organization guidelines.

### 1. Clone the repository

```bash
git clone https://github.com/Ikey168/NeuroNews.git
cd NeuroNews
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Docker development (recommended)

```bash
# Run with Docker Compose for development
docker compose up --build

# Run tests in a containerized environment
docker compose -f docker-compose.test-minimal.yml up --build --abort-on-container-exit
```

### 4. Configure local services

Set the endpoints for the local backends (sensible localhost defaults are used
when unset):

```bash
export S3_ENDPOINT_URL=http://localhost:9000        # MinIO
export DYNAMODB_ENDPOINT_URL=http://localhost:8000  # DynamoDB Local
export NEPTUNE_ENDPOINT=ws://localhost:8182/gremlin # local Gremlin server
```

Any non-empty credentials are accepted by the local emulators.

### 5. Run tests and generate a coverage report

```bash
# Run the test suite with coverage
pytest

# Open coverage_report/index.html in your browser to view the report
```

The coverage report provides line and branch coverage, untested-code
identification, and module-level summaries.

If you also run the Terraform validation steps, install the Terraform CLI first,
then:

```bash
terraform -chdir=deployment/terraform init -backend=false
terraform -chdir=deployment/terraform validate
```

### 6. Run demo scripts

```bash
# Explore available demos
ls demo/

# Run a specific demo
python demo/demo_airflow_bootstrap.py
```

### 7. MLflow autologging demo

Experience MLflow's automatic experiment tracking with scikit-learn models:

```bash
# Run the MLflow autologging demonstration
python examples/train_sklearn_demo.py

# Results are stored in ./mlruns (or viewable in the MLflow UI if running)

# Explore the interactive Jupyter notebook
jupyter notebook notebooks/mlflow_autolog_demo.ipynb
```

What gets logged automatically:

- Model hyperparameters (C, n_estimators, max_depth, and similar).
- Training and test metrics.
- Model artifacts (serialized models) and signatures (input/output schema).
- Feature importance for tree-based models.

### 8. Run the scraper

Run it as a module from the repository root (it uses package-relative imports):

```bash
python -m src.scraper.run --help          # list all options
python -m src.scraper.run --spider bbc    # scrape a single source
python -m src.scraper.run --multi-source  # scrape all sources
```

### 9. Access dashboards and reports

- Streamlit dashboards for visualizations and insights.
- REST API for news sentiment, event tracking, and historical context.

---

## Documentation

- [Project structure](docs/PROJECT_STRUCTURE.md)
- [Exactly-once delivery design](docs/EXACTLY_ONCE_DESIGN.md)

---

## Roadmap

- Phase 1: Web scraping and data ingestion - complete.
- Phase 2: NLP processing and sentiment analysis - complete.
- Phase 3: Event detection and AI summarization - complete.
- Phase 4: Knowledge graph and deep linking - complete.
- Phase 5: Interactive dashboards and API development - complete.
- Future: predictive analytics, real-time fact-checking, and news verification.

---

## Contact and Contributions

- GitHub Issues: report bugs and request features.
- Pull Requests: contributions welcome - see CONTRIBUTING.md for guidelines.
- Email: ikey168@proton.me
- License: MIT
