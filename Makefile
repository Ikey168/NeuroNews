.PHONY: help airflow-up airflow-down airflow-logs marquez-ui airflow-init airflow-status airflow-build airflow-test-openlineage mlflow-up mlflow-down mlflow-ui

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
	@echo "URLs:"
	@echo "  Airflow UI:  http://localhost:8080 (airflow/airflow)"
	@echo "  Marquez UI:  http://localhost:3000"
	@echo "  MLflow UI:   http://localhost:5001"

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
