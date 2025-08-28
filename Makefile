.PHONY: help airflow-up airflow-down airflow-logs marquez-ui airflow-init airflow-status airflow-build airflow-test-openlineage mlflow-up mlflow-down mlflow-ui rag-up rag-down rag-migrate rag-connect rag-reset rag-logs rag-index contract.publish contract.validate db.seed cdc.run iceberg.compact iceberg.expire

# Default target
help:
	@echo "NeuroNews Makefile"
	@echo ""
	@echo "Airflow & Marquez Orchestration:"
	@echo "  airflow-build    - Build custom Airflow image with OpenLineage"
	@echo "  airflow-up       - Start Airflow and Marquez services"
	@echo "  airflow-down     - Stop Airflow and Marquez services"
	@echo "  airflow-logs     - Show Airflow logs"
	@echo "  airflow-init     - Initialize Airflow (run once)"
	@echo "  airflow-status   - Show status of all services"
	@echo "  airflow-test-openlineage - Test OpenLineage integration"
	@echo "  airflow-test-env-config  - Test environment configuration (Issue #188)"
	@echo "  airflow-test-news-pipeline - Test news pipeline DAG (Issue #189)"
	@echo "  airflow-test-timezone-sla - Test timezone and SLA configuration (Issue #190)"
	@echo "  airflow-test-lineage-naming - Test lineage naming convention (Issue #193)"
	@echo "  airflow-bootstrap - Bootstrap Airflow connections and variables (Issue #194)"
	@echo "  airflow-test-bootstrap - Test bootstrap script functionality (Issue #194)"
	@echo "  marquez-ui       - Open Marquez UI in browser"
	@echo ""
	@echo "MLflow Model Tracking:"
	@echo "  mlflow-up        - Start MLflow tracking server with Postgres backend"
	@echo "  mlflow-down      - Stop MLflow tracking server"
	@echo "  mlflow-ui        - Open MLflow UI in browser"
	@echo ""
	@echo "dbt Analytics:"
	@echo "  dbt-deps         - Install dbt packages"
	@echo "  dbt-build        - Build all dbt models"
	@echo "  dbt-build-snowflake - Build dbt models on Snowflake (no-op locally)"
	@echo "  dbt-docs         - Generate and serve dbt documentation"
	@echo "  dbt-test         - Run dbt tests"
	@echo "  dbt-clean        - Clean dbt artifacts"
	@echo ""
	@echo "Vector Store & RAG:"
	@echo "  rag-up           - Start PostgreSQL with pgvector extension"
	@echo "  rag-down         - Stop vector store services"
	@echo "  rag-migrate      - Run database migrations for vector store"
	@echo "  rag-connect      - Connect to vector database"
	@echo "  rag-reset        - Reset vector database (WARNING: deletes all data)"
	@echo "  rag-logs         - Show vector store logs"
	@echo "  rag-index        - Run RAG indexer on sample data (Issue #230)"
	@echo ""
	@echo "Contract Management (Issue #357):"
	@echo "  contract.publish - Publish Avro schema to Schema Registry"
	@echo "  contract.validate - Validate JSON events against schemas"
	@echo ""
	@echo "CDC Database (Issue #345):"
	@echo "  db.seed          - Seed PostgreSQL with demo articles schema and data"
	@echo ""
	@echo "CDC Streaming (Issue #347):"
	@echo "  cdc.run          - Start Spark CDC to Iceberg streaming job"
	@echo ""
	@echo "Iceberg Maintenance (Issue #348):"
	@echo "  iceberg.compact  - Run manual Iceberg table compaction"
	@echo "  iceberg.expire   - Run manual Iceberg snapshot expiration"
	@echo ""
	@echo "URLs:"
	@echo "  Airflow UI:  http://localhost:8080 (airflow/airflow)"
	@echo "  Marquez UI:  http://localhost:3000"
	@echo "  MLflow UI:   http://localhost:5001"
	@echo "  pgAdmin:     http://localhost:5050 (admin@neuronews.com/admin)"

# Airflow and Marquez orchestration targets

# Build custom Airflow image with OpenLineage (Issue #187)
airflow-build:
	@echo "🔨 Building custom Airflow image with OpenLineage provider..."
	@cd docker/airflow && docker build -t neuronews/airflow:2.8.1-openlineage .
	@echo "✅ Custom Airflow image built successfully!"
	@echo "🏷️  Image: neuronews/airflow:2.8.1-openlineage"

airflow-up:
	@echo "🚀 Starting Airflow and Marquez services..."
	@cd docker/airflow && docker-compose -f docker-compose.airflow.yml up -d
	@echo ""
	@echo "✅ Services started!"
	@echo "📊 Airflow UI: http://localhost:8080 (username: airflow, password: airflow)"
	@echo "📈 Marquez UI: http://localhost:3000"
	@echo ""
	@echo "Use 'make airflow-logs' to view logs"
	@echo "Use 'make airflow-status' to check service health"

airflow-down:
	@echo "🛑 Stopping Airflow and Marquez services..."
	@cd docker/airflow && docker-compose -f docker-compose.airflow.yml down
	@echo "✅ Services stopped!"

airflow-logs:
	@echo "📋 Showing Airflow logs..."
	@cd docker/airflow && docker-compose -f docker-compose.airflow.yml logs -f

airflow-init:
	@echo "🔧 Initializing Airflow..."
	@cd docker/airflow && docker-compose -f docker-compose.airflow.yml up airflow-init
	@echo "✅ Airflow initialized!"

airflow-status:
	@echo "📊 Service Status:"
	@cd docker/airflow && docker-compose -f docker-compose.airflow.yml ps

# Test OpenLineage integration (Issue #187)
airflow-test-openlineage:
	@echo "🧪 Testing OpenLineage integration..."
	@echo "1. Checking if services are running..."
	@cd docker/airflow && docker-compose -f docker-compose.airflow.yml ps
	@echo ""
	@echo "2. Triggering test DAG..."
	@cd docker/airflow && docker-compose -f docker-compose.airflow.yml exec airflow-webserver \
		airflow dags trigger test_openlineage_integration
	@echo ""
	@echo "3. Checking webserver logs for OpenLineage..."
	@echo "   Look for 'OpenLineage' messages in the logs:"
	@cd docker/airflow && docker-compose -f docker-compose.airflow.yml logs airflow-webserver | grep -i openlineage || echo "No OpenLineage logs found yet"
	@echo ""
	@echo "✅ Test triggered! Check Airflow UI for DAG execution: http://localhost:8080"

# Test Airflow → Marquez environment configuration (Issue #188)
airflow-test-env-config:
	@echo "🔧 Testing Airflow → Marquez environment configuration..."
	@python3 demo/demo_airflow_marquez_env_config.py

# Test news pipeline DAG (Issue #189)
airflow-test-news-pipeline:
	@echo "📰 Testing news pipeline DAG..."
	@python3 demo/demo_news_pipeline_dag.py

# Test timezone and SLA configuration (Issue #190)
airflow-test-timezone-sla:
	@echo "🕰️ Testing timezone and SLA configuration..."
	@python3 demo/demo_timezone_sla_config.py

# Test lineage naming convention (Issue #193)
airflow-test-lineage-naming:
	@echo "🔗 Testing lineage naming convention..."
	@python3 demo/demo_lineage_naming.py

# Bootstrap Airflow connections and variables (Issue #194)
airflow-bootstrap:
	@echo "🚀 Bootstrapping Airflow connections and variables..."
	@docker exec $$(docker-compose -f docker/airflow/docker-compose.airflow.yml ps -q airflow-webserver) bash -c 'cd /opt/airflow && ./scripts/airflow_bootstrap.sh --verbose'

# Test bootstrap script functionality (Issue #194)
airflow-test-bootstrap:
	@echo "🧪 Testing bootstrap script..."
	@python3 demo/demo_airflow_bootstrap.py

marquez-ui:
	@echo "🌐 Opening Marquez UI..."
	@if command -v xdg-open > /dev/null; then \
		xdg-open http://localhost:3000; \
	elif command -v open > /dev/null; then \
		open http://localhost:3000; \
	else \
		echo "Please open http://localhost:3000 in your browser"; \
	fi

# Additional utility targets
airflow-webserver-logs:
	@cd docker/airflow && docker-compose -f docker-compose.airflow.yml logs -f airflow-webserver

airflow-scheduler-logs:
	@cd docker/airflow && docker-compose -f docker-compose.airflow.yml logs -f airflow-scheduler

marquez-logs:
	@cd docker/airflow && docker-compose -f docker-compose.airflow.yml logs -f marquez

airflow-clean:
	@echo "🧹 Cleaning up Airflow volumes and containers..."
	@cd docker/airflow && docker-compose -f docker-compose.airflow.yml down -v
	@docker system prune -f
	@echo "✅ Cleanup complete!"

# dbt Analytics targets (Issue #203)

dbt-deps:
	@echo "📦 Installing dbt packages..."
	@cd dbt/neuro_news && dbt deps --profiles-dir ../
	@echo "✅ dbt packages installed!"

dbt-build:
	@echo "🔨 Building all dbt models..."
	@cd dbt/neuro_news && dbt build --profiles-dir ../
	@echo "✅ dbt models built successfully!"

dbt-build-snowflake:
	@echo "🏔️  Building dbt models on Snowflake..."
	@if [ -z "$$SNOWFLAKE_ACCOUNT" ]; then \
		echo "⚠️  SNOWFLAKE_ACCOUNT not set - skipping Snowflake build"; \
		echo "ℹ️  This is expected in local development"; \
		echo "ℹ️  To use Snowflake: uncomment target in profiles.yml and set env vars"; \
	else \
		echo "🔗 Connecting to Snowflake account: $$SNOWFLAKE_ACCOUNT"; \
		cd dbt/neuro_news && dbt build --profiles-dir ../ --target prod; \
	fi

dbt-docs:
	@echo "📚 Generating dbt documentation..."
	@cd dbt/neuro_news && dbt docs generate --profiles-dir ../
	@echo "🌐 Serving dbt documentation..."
	@cd dbt/neuro_news && dbt docs serve --profiles-dir ../

dbt-test:
	@echo "🧪 Running dbt tests..."
	@cd dbt/neuro_news && dbt test --profiles-dir ../

dbt-clean:
	@echo "🧹 Cleaning dbt artifacts..."
	@cd dbt/neuro_news && dbt clean --profiles-dir ../
	@echo "✅ dbt artifacts cleaned!"

# MLflow Model Tracking targets (Issue #215)

mlflow-up:
	@echo "🚀 Starting MLflow tracking server with Postgres backend..."
	@cd docker/mlflow && docker-compose -f docker-compose.mlflow.yml up -d
	@echo ""
	@echo "✅ MLflow services started!"
	@echo "📊 MLflow UI: http://localhost:5001"
	@echo "📈 Database: PostgreSQL on port 5433"
	@echo ""
	@echo "Use 'make mlflow-down' to stop services"
	@echo "Use 'make mlflow-ui' to open MLflow UI"

mlflow-down:
	@echo "🛑 Stopping MLflow tracking server..."
	@cd docker/mlflow && docker-compose -f docker-compose.mlflow.yml down
	@echo "✅ MLflow services stopped!"

mlflow-ui:
	@echo "🌐 Opening MLflow UI..."
	@if command -v xdg-open > /dev/null; then \
		xdg-open http://localhost:5001; \
	elif command -v open > /dev/null; then \
		open http://localhost:5001; \
	else \
		echo "Please open http://localhost:5001 in your browser"; \
	fi

# Vector Store & RAG targets (Issue #227)

rag-up:
	@echo "🚀 Starting PostgreSQL with pgvector extension..."
	@cd docker/vector && docker-compose -f docker-compose.rag.yml up -d
	@echo ""
	@echo "✅ Vector store services started!"
	@echo "🐘 PostgreSQL: localhost:5433"
	@echo "🔍 pgAdmin: http://localhost:5050 (admin@neuronews.com/admin)"
	@echo "🗄️  Database: neuronews_vector"
	@echo "👤 User: neuronews"
	@echo ""
	@echo "Use 'make rag-migrate' to initialize schema"
	@echo "Use 'make rag-down' to stop services"

rag-down:
	@echo "🛑 Stopping vector store services..."
	@cd docker/vector && docker-compose -f docker-compose.rag.yml down
	@echo "✅ Vector store services stopped!"

rag-migrate:
	@echo "🔄 Running vector store migrations..."
	@echo "Waiting for PostgreSQL to be ready..."
	@timeout 60 sh -c 'until docker exec neuronews-postgres-vector pg_isready -U neuronews -d neuronews_vector; do sleep 2; done'
	@echo "Running migration 0001_init_pgvector.sql..."
	@docker exec -i neuronews-postgres-vector psql -U neuronews -d neuronews_vector < migrations/pg/0001_init_pgvector.sql
	@echo "Running migration 0002_schema_chunks.sql..."
	@docker exec -i neuronews-postgres-vector psql -U neuronews -d neuronews_vector < migrations/pg/0002_schema_chunks.sql
	@echo ""
	@echo "✅ Vector store migrations completed!"
	@echo "📊 Tables created: documents, chunks, embeddings, inverted_terms, search_logs"
	@echo "🔍 Indexes created: IVFFlat vector indexes for optimal similarity search"
	@echo "⚡ Functions created: search_similar_documents(), cosine_similarity(), etc."

rag-connect:
	@echo "🔌 Connecting to vector database..."
	@docker exec -it neuronews-postgres-vector psql -U neuronews -d neuronews_vector

rag-reset:
	@echo "⚠️  WARNING: This will delete ALL vector store data!"
	@read -p "Are you sure? Type 'yes' to continue: " confirm && [ "$$confirm" = "yes" ] || exit 1
	@echo "🗑️  Resetting vector database..."
	@cd docker/vector && docker-compose -f docker-compose.rag.yml down -v
	@cd docker/vector && docker-compose -f docker-compose.rag.yml up -d
	@echo "Waiting for PostgreSQL to be ready..."
	@timeout 60 sh -c 'until docker exec neuronews-postgres-vector pg_isready -U neuronews -d neuronews_vector; do sleep 2; done'
	@make rag-migrate
	@echo "✅ Vector database reset complete!"

rag-logs:
	@echo "📄 Showing vector store logs..."
	@cd docker/vector && docker-compose -f docker-compose.rag.yml logs -f

# RAG Indexer target (Issue #230)
rag-index:
	@echo "🔍 Running RAG indexer on sample data..."
	@if [ -z "$(SAMPLE_PATH)" ]; then \
		echo "⚠️  SAMPLE_PATH not specified, using default: data/silver/news/*.parquet"; \
		SAMPLE_PATH="data/silver/news/*.parquet"; \
	fi; \
	echo "📂 Processing: $$SAMPLE_PATH"; \
	python jobs/rag/cli_indexer.py "$$SAMPLE_PATH" --config configs/indexer.yaml
	@echo "✅ RAG indexing complete! Check database for upserted records."

# Contract Management targets (Issue #357)

contract.publish:
	@echo "📄 Publishing Avro schema to Schema Registry..."
	@python scripts/contracts/publish_schema.py \
		contracts/schemas/avro/article-ingest-v1.avsc \
		--registry-url http://localhost:8081 \
		--subject neuronews.ArticleIngest-value
	@echo "✅ Schema published successfully!"

contract.validate:
	@echo "🔍 Validating JSON events against schemas..."
	@if [ -d "contracts/examples/article-ingest-v1" ]; then \
		python scripts/contracts/validate_event.py contracts/examples/article-ingest-v1/ \
			--avro-schema contracts/schemas/avro/article-ingest-v1.avsc \
			--json-schema contracts/schemas/jsonschema/article-ingest-v1.json \
			--directory; \
	else \
		echo "⚠️  Example events directory not found: contracts/examples/article-ingest-v1"; \
		echo "Creating sample validation with any JSON files in schemas/..."; \
		find contracts/schemas/ -name "*.json" | head -1 | xargs -I {} python scripts/contracts/validate_event.py {} \
			--avro-schema contracts/schemas/avro/article-ingest-v1.avsc; \
	fi
	@echo "✅ Event validation complete!"

# CDC Database seeding (Issue #345)
db.seed:
	@echo "🌱 Seeding PostgreSQL with demo articles schema and data..."
	@echo "📋 Checking if CDC Postgres container is running..."
	@if [ -z "$$(docker ps --filter 'name=.*postgres.*' --filter 'status=running' --format '{{.Names}}' | head -1)" ]; then \
		echo "❌ No PostgreSQL container running. Please start CDC stack first:"; \
		echo "   cd docker && docker-compose -f docker-compose.cdc.yml up -d postgres"; \
		exit 1; \
	fi
	@echo "✅ PostgreSQL container found!"
	@echo "📂 Loading seed data from db/seed/001_articles.sql..."
	@docker exec -i $$(docker ps --filter 'name=.*postgres.*' --filter 'status=running' --format '{{.Names}}' | head -1) \
		psql -U postgres -d neuronews < db/seed/001_articles.sql
	@echo ""
	@echo "🔍 Verifying data was loaded..."
	@docker exec $$(docker ps --filter 'name=.*postgres.*' --filter 'status=running' --format '{{.Names}}' | head -1) \
		psql -U postgres -d neuronews -c "SELECT COUNT(*) as article_count FROM articles;"
	@echo ""
	@echo "📋 Sample data preview:"
	@docker exec $$(docker ps --filter 'name=.*postgres.*' --filter 'status=running' --format '{{.Names}}' | head -1) \
		psql -U postgres -d neuronews -c "SELECT article_id, source_id, title, language, country FROM articles LIMIT 5;"
	@echo ""
	@echo "✅ Database seeding complete! Articles table ready for CDC streaming."

# CDC Streaming job (Issue #347)
cdc.run:
	@echo "🚀 Starting Spark Structured Streaming CDC to Iceberg job..."
	@echo "📋 Prerequisites:"
	@echo "   - CDC stack running: docker compose -f docker/docker-compose.cdc.yml up -d"
	@echo "   - Database seeded: make db.seed"
	@echo "   - Debezium connector registered"
	@echo ""
	@if ! docker ps --filter 'name=.*redpanda.*' --filter 'status=running' | grep -q redpanda; then \
		echo "❌ Redpanda not running. Start CDC stack first:"; \
		echo "   cd docker && docker-compose -f docker-compose.cdc.yml up -d"; \
		exit 1; \
	fi
	@echo "✅ Kafka (Redpanda) is running"
	@echo "🔄 Starting Spark job..."
	cd spark && python jobs/cdc_to_iceberg.py

# Iceberg maintenance jobs (Issue #348)
iceberg.compact:
	@echo "🔧 Running Iceberg table compaction for CDC tables..."
	@echo "📋 This will consolidate small files and improve query performance"
	@echo ""
	@echo "🔄 Compacting local.news.articles (CDC table)..."
	cd airflow/dags/spark_jobs && python iceberg_compaction.py --table local.news.articles --operation rewrite_data_files
	cd airflow/dags/spark_jobs && python iceberg_compaction.py --table local.news.articles --operation rewrite_manifests
	@echo ""
	@echo "✅ Iceberg compaction completed"

iceberg.expire:
	@echo "🗑️  Running Iceberg snapshot expiration for CDC tables..."
	@echo "📋 This will remove old snapshots while retaining recent ones (7+ days)"
	@echo ""
	@echo "🔄 Expiring snapshots for local.news.articles (CDC table)..."
	cd airflow/dags/spark_jobs && python iceberg_snapshot_expiration.py \
		--table local.news.articles \
		--older_than "$$(date -d '7 days ago' '+%Y-%m-%d %H:%M:%S')" \
		--retain_last 10
	@echo ""
	@echo "✅ Iceberg snapshot expiration completed"
