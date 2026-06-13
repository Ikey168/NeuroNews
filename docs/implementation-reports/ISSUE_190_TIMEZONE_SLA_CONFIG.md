# Issue #190: Airflow Timezone & SLA Configuration

## 🎯 Implementation Summary

Successfully configured Airflow timezone to Europe/Berlin and implemented SLA monitoring for the clean task in the news_pipeline DAG.

## ✅ Requirements Fulfilled

### Timezone Configuration
- ✅ Set default timezone to Europe/Berlin via environment variable
- ✅ Configuration applied to all Airflow containers
- ✅ Schedule displays correctly in Berlin timezone
- ✅ Documented UI caveat (displays UTC by default)

### SLA Configuration  
- ✅ Added SLA parameter to clean task (15 minutes)
- ✅ Enabled SLA checking in Airflow configuration
- ✅ Implemented SLA miss callback for logging/alerting
- ✅ SLA misses visible in task instance details/logs

## 🔧 Technical Implementation

### Files Modified

#### 1. `docker/airflow/docker-compose.airflow.yml`
```yaml
environment:
  # Timezone configuration (Issue #190)
  AIRFLOW__CORE__DEFAULT_TIMEZONE: Europe/Berlin
  # SLA configuration (Issue #190)  
  AIRFLOW__CORE__CHECK_SLAS: 'true'
  AIRFLOW__EMAIL__EMAIL_BACKEND: airflow.providers.sendgrid.utils.emailer.send_email
```

#### 2. `docker/airflow/.env.example`
```bash
# Timezone Configuration (Issue #190)
AIRFLOW__CORE__DEFAULT_TIMEZONE=Europe/Berlin
AIRFLOW__CORE__CHECK_SLAS=true
```

#### 3. `airflow/dags/news_pipeline.py`
```python
# Configure SLA for the clean task (Issue #190)
if hasattr(news_pipeline_dag, 'get_task') and news_pipeline_dag.get_task('clean', None):
    clean_task = news_pipeline_dag.get_task('clean')
    clean_task.sla = timedelta(minutes=15)
    
    # Add SLA miss callback for logging
    def sla_miss_callback(dag, task_list, blocking_task_list, slas, blocking_tis):
        # Logs SLA violations for monitoring and alerting
        ...
    
    news_pipeline_dag.sla_miss_callback = sla_miss_callback
```

### Testing Infrastructure

#### 4. `demo/demo_timezone_sla_config.py`
- Comprehensive validation script for timezone and SLA configuration
- Tests service health, timezone settings, SLA configuration, and DAG execution
- Validates SLA monitoring and logging functionality

#### 5. `Makefile`
```bash
airflow-test-timezone-sla:
    @echo "🕰️ Testing timezone and SLA configuration..."
    @python3 demo/demo_timezone_sla_config.py
```

## 🕰️ Timezone Configuration Details

### Environment Variable
- **Variable**: `AIRFLOW__CORE__DEFAULT_TIMEZONE=Europe/Berlin`
- **Scope**: All Airflow containers (webserver, scheduler, init)
- **Effect**: All DAG schedules and task execution times use Berlin timezone

### Schedule Behavior
- DAG schedule: `'0 8 * * *'` = Daily at 08:00 Europe/Berlin
- Execution date calculation uses Berlin timezone
- Task logs show Berlin timezone timestamps

### UI Display Caveat
⚠️ **Important**: Airflow UI displays times in UTC by default, but execution uses Berlin timezone.

To verify correct timezone behavior:
1. Check DAG schedule in UI (shows UTC equivalent of Berlin time)
2. Check task logs (show Berlin timezone timestamps)  
3. Verify actual execution times match Berlin schedule

## ⏰ SLA Configuration Details

### Clean Task SLA
- **SLA Duration**: 15 minutes
- **Task**: `clean` in `news_pipeline` DAG
- **Purpose**: Demonstrate SLA monitoring capabilities

### SLA Monitoring
- **Global Setting**: `AIRFLOW__CORE__CHECK_SLAS=true`
- **Miss Detection**: Automatic via Airflow scheduler
- **Logging**: Custom callback logs SLA violations
- **Alerting**: Can be extended with email/Slack notifications

### SLA Miss Callback
```python
def sla_miss_callback(dag, task_list, blocking_task_list, slas, blocking_tis):
    """
    Logs SLA violations and can trigger alerts.
    Called automatically when SLA is missed.
    """
    for sla in slas:
        logger.warning(f"🚨 SLA MISS: Task '{sla.task_id}' missed SLA")
```

## 🚀 Usage Instructions

### Start Services
```bash
make airflow-up
```

### Test Configuration
```bash
# Test timezone and SLA configuration
make airflow-test-timezone-sla

# Test complete news pipeline with SLA monitoring
make airflow-test-news-pipeline
```

### Access UIs
- **Airflow UI**: http://localhost:8080 (airflow/airflow)
- **Marquez UI**: http://localhost:3000

### Verify Implementation

#### 1. Timezone Verification
1. Open Airflow UI at http://localhost:8080
2. Navigate to DAGs → news_pipeline
3. Check "Schedule" shows daily at 08:00 (UTC equivalent)
4. Trigger a manual run and check execution logs for Berlin timestamps

#### 2. SLA Verification  
1. Monitor clean task in news_pipeline DAG
2. Check task instance details for SLA information
3. Review scheduler logs for SLA miss alerts:
   ```bash
   make airflow-scheduler-logs | grep -i sla
   ```

## 📊 Expected Behavior

### Normal Operation
- DAG executes daily at 08:00 Europe/Berlin
- Clean task completes within 15 minutes (no SLA miss)
- All timestamps in logs use Berlin timezone

### SLA Miss Scenario
- If clean task takes >15 minutes:
  - SLA miss logged by scheduler
  - Custom callback function triggered
  - Warning message logged with details
  - Visible in Airflow UI task instance

## 🎉 DoD Verification

### ✅ Requirements Met
1. **Timezone**: Default timezone set to Europe/Berlin ✅
2. **SLA**: Clean task has 15-minute SLA parameter ✅  
3. **Monitoring**: SLA misses logged and visible ✅
4. **Schedule**: news_pipeline shows Berlin schedule ✅
5. **Documentation**: UI caveat documented ✅

### Testing Commands
```bash
# Complete test suite
make airflow-test-timezone-sla

# Manual verification
make airflow-up
# Open http://localhost:8080 and verify DAG schedule
# Trigger news_pipeline and monitor SLA compliance
```

## 🔄 Future Enhancements

### Email Alerts
- Configure SMTP settings for SLA miss emails
- Add email recipients to DAG configuration
- Test email delivery for SLA violations

### Extended SLA Monitoring
- Add SLAs to other tasks (scrape, nlp, publish)
- Configure different SLA thresholds per task
- Implement Slack/Teams notifications

### Timezone Flexibility
- Support multiple timezone environments
- Environment-specific timezone configuration
- Dynamic timezone selection per DAG

## 📚 References

- [Airflow Timezone Documentation](https://airflow.apache.org/docs/apache-airflow/stable/timezone.html)
- [Airflow SLA Documentation](https://airflow.apache.org/docs/apache-airflow/stable/concepts/dags.html#slas)
- [OpenLineage Provider Documentation](https://openlineage.io/docs/integrations/airflow/)

---

**Implementation Complete** ✅  
Issue #190 requirements fully satisfied with comprehensive testing and documentation.
