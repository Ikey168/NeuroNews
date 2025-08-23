.PHONY: help airflow-up airflow-down airflow-logs marquez-ui airflow-init airflow-status airflow-build airflow-test-openlineage

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
	@echo "  marquez-ui       - Open Marquez UI in browser"
	@echo ""
	@echo "URLs:"
	@echo "  Airflow UI:  http://localhost:8080 (airflow/airflow)"
	@echo "  Marquez UI:  http://localhost:3000"

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
