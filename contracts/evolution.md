# Data Contracts Evolution Playbook

This document provides a comprehensive guide for managing schema evolution and versioning in the NeuroNews data contracts ecosystem. It establishes clear rules, strategies, and step-by-step procedures for safely evolving data contracts while maintaining compatibility.

## Table of Contents

- [Evolution Rules](#evolution-rules)
- [Versioning Strategy](#versioning-strategy)
- [Dual-Write Strategy](#dual-write-strategy)
- [Dual-Read with Fallback](#dual-read-with-fallback)
- [Step-by-Step Procedures](#step-by-step-procedures)
- [Rollback Procedures](#rollback-procedures)
- [Monitoring and Validation](#monitoring-and-validation)
- [Examples](#examples)

## Evolution Rules

### 1. Safe Changes (Backward Compatible)

These changes can be made without breaking existing consumers:

#### ✅ Additive Changes
- **Add optional fields** with default values
- **Add new message types** to existing topics
- **Add new enums** without removing existing values
- **Add documentation** and comments

```json
// Before
{
  "name": "ArticleIngest",
  "fields": [
    {"name": "article_id", "type": "string"},
    {"name": "title", "type": ["null", "string"], "default": null}
  ]
}

// After - Safe addition
{
  "name": "ArticleIngest", 
  "fields": [
    {"name": "article_id", "type": "string"},
    {"name": "title", "type": ["null", "string"], "default": null},
    {"name": "category", "type": ["null", "string"], "default": null}  // ✅ New optional field
  ]
}
```

#### ✅ Default Value Updates
- **Modify default values** for optional fields
- **Add defaults** to previously required fields (making them optional)

```json
// Before
{"name": "priority", "type": ["null", "string"], "default": null}

// After - Safe default change
{"name": "priority", "type": ["null", "string"], "default": "medium"}  // ✅ Better default
```

### 2. Unsafe Changes (Breaking Compatibility)

These changes require careful migration procedures:

#### ❌ Destructive Changes
- **Remove fields** that consumers depend on
- **Change field types** (string → int, optional → required)
- **Rename fields** without maintaining compatibility
- **Remove enum values** that are in use
- **Change required fields** to have different constraints

```json
// ❌ BREAKING: Removing a field
{
  "name": "ArticleIngest",
  "fields": [
    {"name": "article_id", "type": "string"}
    // {"name": "title", "type": ["null", "string"]}  // ❌ Removed field
  ]
}

// ❌ BREAKING: Changing field type
{"name": "sentiment_score", "type": "string"}  // Was: ["null", "double"]
```

### 3. Deprecation Strategy

For fields that need to be removed, use a phased deprecation approach:

#### Phase 1: Mark as Deprecated (nullable + default)
```json
{
  "name": "old_field",
  "type": ["null", "string"],
  "default": null,
  "doc": "@deprecated Use new_field instead. Will be removed in v3.0"
}
```

#### Phase 2: Dual Fields (transition period)
```json
{
  "fields": [
    {
      "name": "old_field", 
      "type": ["null", "string"], 
      "default": null,
      "doc": "@deprecated Use new_field instead. Will be removed in v3.0"
    },
    {
      "name": "new_field",
      "type": ["null", "string"], 
      "default": null,
      "doc": "Replacement for old_field"
    }
  ]
}
```

#### Phase 3: Remove Deprecated Field (next major version)
```json
{
  "fields": [
    {
      "name": "new_field",
      "type": ["null", "string"], 
      "default": null
    }
  ]
}
```

### 4. Rename Strategy (add + backfill + drop)

To rename a field safely:

#### Step 1: Add new field
```json
{
  "fields": [
    {"name": "title", "type": ["null", "string"], "default": null},
    {"name": "headline", "type": ["null", "string"], "default": null}  // New name
  ]
}
```

#### Step 2: Backfill data (producer sends both)
```python
# Producer code
article_event = {
    "title": article.title,      # Old field
    "headline": article.title    # New field (same data)
}
```

#### Step 3: Consumer migration
```python
# Consumer code - handle both fields
def get_headline(article_data):
    # Prefer new field, fallback to old
    return article_data.get("headline") or article_data.get("title")
```

#### Step 4: Drop old field (next major version)
```json
{
  "fields": [
    {"name": "headline", "type": ["null", "string"], "default": null}
  ]
}
```

## Versioning Strategy

### Semantic Versioning for Schemas

Use semantic versioning (MAJOR.MINOR.PATCH) for schema versions:

- **MAJOR**: Breaking changes that require consumer updates
- **MINOR**: Backward-compatible additions (new optional fields)
- **PATCH**: Documentation, default value changes, bug fixes

### Version Naming Convention

```
{schema-name}-v{major}.{minor}.{patch}

Examples:
- article-ingest-v1.0.0
- article-ingest-v1.1.0  (added optional field)
- article-ingest-v2.0.0  (breaking change)
```

### Schema Registry Organization

```
contracts/schemas/avro/
├── article-ingest-v1.avsc       # Current stable version
├── article-ingest-v2.avsc       # Next major version (in development)
└── archive/
    ├── article-ingest-v1.0.0.avsc
    ├── article-ingest-v1.1.0.avsc
    └── article-ingest-v1.2.0.avsc
```

## Dual-Write Strategy

For major version migrations, implement dual-write to both versions simultaneously:

### Duration
- **Minimum**: 7 days
- **Recommended**: 14 days
- **High-traffic topics**: 30 days

### Implementation Pattern

```python
class ArticleProducer:
    def __init__(self):
        self.v1_producer = self._create_producer("article-ingest-v1")
        self.v2_producer = self._create_producer("article-ingest-v2")
        self.dual_write_enabled = config.get("DUAL_WRITE_ENABLED", False)
    
    def publish_article(self, article_data):
        """Publish article to both v1 and v2 topics during migration."""
        
        # Always publish to current stable version
        v1_message = self._transform_to_v1(article_data)
        self.v1_producer.produce("news.articles.ingested.v1", v1_message)
        
        # Conditionally publish to new version during migration
        if self.dual_write_enabled:
            v2_message = self._transform_to_v2(article_data)
            self.v2_producer.produce("news.articles.ingested.v2", v2_message)
            
        # Log dual-write metrics
        self._record_dual_write_metrics()
```

### Monitoring Dual-Write

```python
# Metrics to track during dual-write period
dual_write_metrics = {
    "v1_messages_sent": counter,
    "v2_messages_sent": counter, 
    "dual_write_lag_ms": histogram,
    "transformation_errors": counter,
    "schema_validation_failures": counter
}
```

## Dual-Read with Fallback

Consumers should read from new version with fallback to old version:

### Consumer Implementation

```python
class ArticleConsumer:
    def __init__(self):
        self.v2_consumer = self._create_consumer("news.articles.ingested.v2")
        self.v1_consumer = self._create_consumer("news.articles.ingested.v1") 
        self.fallback_enabled = config.get("FALLBACK_ENABLED", True)
    
    def consume_articles(self):
        """Consume from v2 with fallback to v1."""
        
        try:
            # Try v2 first
            message = self.v2_consumer.poll(timeout=1.0)
            if message and not message.error():
                return self._process_v2_message(message)
                
        except Exception as e:
            logger.warning(f"v2 consumer error: {e}")
            self._record_fallback_metric("v2_error")
        
        # Fallback to v1 if v2 fails or has no messages
        if self.fallback_enabled:
            try:
                message = self.v1_consumer.poll(timeout=1.0)
                if message and not message.error():
                    return self._process_v1_message(message)
            except Exception as e:
                logger.error(f"Both v1 and v2 consumers failed: {e}")
                raise
                
        return None
```

### Graceful Degradation

```python
def _process_message_with_fallback(self, message_data):
    """Process message with field-level fallbacks."""
    
    processed = {}
    
    # New field with fallback to old field
    processed["headline"] = (
        message_data.get("headline") or 
        message_data.get("title") or 
        "Unknown Title"
    )
    
    # Handle type changes gracefully
    try:
        processed["sentiment"] = float(message_data.get("sentiment_score", 0.0))
    except (TypeError, ValueError):
        # Fallback if type conversion fails
        processed["sentiment"] = 0.0
        logger.warning("Could not parse sentiment_score, using default")
    
    return processed
```

## Step-by-Step Procedures

### 1. Adding a New Optional Field

#### Prerequisites
- Field has appropriate default value
- Field documentation is complete
- Consumer impact assessment completed

#### Steps

1. **Update schema**
   ```bash
   # Edit schema file
   vim contracts/schemas/avro/article-ingest-v1.avsc
   
   # Add new field with default
   {"name": "author_id", "type": ["null", "string"], "default": null}
   ```

2. **Validate schema**
   ```bash
   # Run schema validation
   python scripts/contracts/validate_schema.py contracts/schemas/avro/article-ingest-v1.avsc
   ```

3. **Run compatibility check**
   ```bash
   # Check backward compatibility
   python scripts/contracts/diff_schema.py
   ```

4. **Update version (minor bump)**
   ```bash
   # v1.1.0 → v1.2.0
   cp contracts/schemas/avro/article-ingest-v1.avsc contracts/schemas/avro/archive/article-ingest-v1.2.0.avsc
   ```

5. **Test with golden fixtures**
   ```bash
   # Create test fixture with new field
   echo '{"article_id": "test", "author_id": "john-doe"}' > contracts/examples/valid/valid-with-author.json
   
   # Run E2E tests
   python -m pytest contracts/tests/test_contracts_e2e.py -v
   ```

6. **Deploy and monitor**
   ```bash
   git add . && git commit -m "Add optional author_id field to article-ingest v1.2.0"
   git push origin feature/add-author-id
   ```

### 2. Breaking Change Migration (Major Version)

#### Prerequisites
- All consumers identified and migration plan created
- Dual-write strategy implemented
- Rollback plan prepared

#### Steps

1. **Create new major version schema**
   ```bash
   # Copy current schema to new version
   cp contracts/schemas/avro/article-ingest-v1.avsc contracts/schemas/avro/article-ingest-v2.avsc
   
   # Make breaking changes to v2
   vim contracts/schemas/avro/article-ingest-v2.avsc
   ```

2. **Implement dual-write producer**
   ```python
   # Update producer to write to both versions
   # See dual-write strategy section above
   ```

3. **Deploy dual-write producer**
   ```bash
   # Enable dual-write via feature flag
   export DUAL_WRITE_ENABLED=true
   
   # Deploy producer changes
   kubectl apply -f k8s/producers/
   ```

4. **Validate dual-write**
   ```bash
   # Monitor metrics for 24 hours
   # Ensure both topics receive messages
   # Check for transformation errors
   ```

5. **Update consumers gradually**
   ```python
   # Deploy updated consumers with dual-read capability
   # Start with non-critical consumers
   # Monitor error rates and performance
   ```

6. **Monitor migration**
   ```bash
   # Check consumer lag on both topics
   kafka-consumer-groups --bootstrap-server localhost:9092 --describe --group article-processors
   
   # Monitor error rates
   # Validate data consistency between versions
   ```

7. **Switch consumers to v2**
   ```bash
   # After validation period (7-30 days)
   # Disable fallback to v1
   export FALLBACK_ENABLED=false
   
   # Update consumer configuration
   kubectl apply -f k8s/consumers/
   ```

8. **Disable dual-write**
   ```bash
   # After all consumers migrated
   export DUAL_WRITE_ENABLED=false
   
   # Stop producing to v1 topic
   kubectl apply -f k8s/producers/
   ```

9. **Cleanup old version**
   ```bash
   # Archive old schema
   mv contracts/schemas/avro/article-ingest-v1.avsc contracts/schemas/avro/archive/
   
   # Update documentation
   # Delete old topic (after retention period)
   ```

### 3. Field Deprecation Process

#### Steps

1. **Mark field as deprecated**
   ```json
   {
     "name": "legacy_field",
     "type": ["null", "string"],
     "default": null,
     "doc": "@deprecated Since v1.3.0. Use new_field instead. Will be removed in v2.0.0"
   }
   ```

2. **Add replacement field**
   ```json
   {
     "name": "new_field", 
     "type": ["null", "string"],
     "default": null,
     "doc": "Replacement for legacy_field"
   }
   ```

3. **Update producer to populate both**
   ```python
   event_data = {
       "legacy_field": value,  # Keep for backward compatibility
       "new_field": value      # New preferred field
   }
   ```

4. **Notify consumers**
   ```bash
   # Send notification to all consumer teams
   # Include migration timeline
   # Provide code examples
   ```

5. **Monitor usage**
   ```python
   # Track field usage in consumers
   deprecated_field_usage = counter("deprecated_field_access")
   new_field_usage = counter("new_field_access")
   ```

6. **Remove deprecated field in next major version**
   ```json
   // v2.0.0 - only keep new field
   {"name": "new_field", "type": ["null", "string"], "default": null}
   ```

## Rollback Procedures

### Emergency Rollback

If issues are detected during migration:

1. **Immediate Actions**
   ```bash
   # Disable dual-write if causing issues
   export DUAL_WRITE_ENABLED=false
   
   # Revert consumers to previous version
   export FALLBACK_ENABLED=true
   
   # Alert all stakeholders
   ```

2. **Assess Impact**
   ```bash
   # Check consumer lag and error rates
   # Identify affected services
   # Estimate data loss/corruption
   ```

3. **Implement Fix**
   ```bash
   # Fix schema or producer issues
   # Validate fix in staging environment
   # Prepare hotfix deployment
   ```

4. **Gradual Recovery**
   ```bash
   # Re-enable dual-write after fix
   # Monitor metrics closely
   # Gradually re-migrate consumers
   ```

### Planned Rollback

If migration needs to be postponed:

1. **Coordinate with Teams**
   ```bash
   # Notify all consumer teams
   # Update migration timeline
   # Document rollback reasons
   ```

2. **Revert Changes**
   ```bash
   # Keep dual-write disabled
   # Maintain old version support
   # Update documentation
   ```

## Monitoring and Validation

### Key Metrics

```yaml
# Schema Evolution Metrics
schema_compatibility_checks:
  - backward_compatibility_violations
  - forward_compatibility_violations
  - schema_validation_failures

dual_write_metrics:
  - messages_written_v1
  - messages_written_v2
  - dual_write_latency
  - transformation_errors

consumer_metrics:
  - v1_consumer_lag
  - v2_consumer_lag
  - fallback_activations
  - deserialization_errors

migration_progress:
  - consumers_migrated_count
  - consumers_remaining_count
  - migration_completion_percentage
```

### Alerts

```yaml
# Critical Alerts
- name: schema_validation_failure_rate_high
  condition: schema_validation_failures > 5% for 5 minutes
  action: page_oncall_engineer

- name: dual_write_lag_high
  condition: dual_write_latency > 1000ms for 10 minutes
  action: alert_data_team

- name: consumer_migration_stalled
  condition: migration_completion_percentage unchanged for 24 hours
  action: alert_platform_team

# Warning Alerts  
- name: deprecated_field_usage_detected
  condition: deprecated_field_access > 0 for 24 hours
  action: notify_consumer_teams
```

### Validation Checklist

Before deploying schema changes:

- [ ] Schema passes backward compatibility check
- [ ] All required fields have appropriate defaults
- [ ] Documentation is complete and accurate
- [ ] Golden fixtures updated and tests pass
- [ ] Consumer impact assessment completed
- [ ] Rollback plan documented
- [ ] Monitoring alerts configured
- [ ] Stakeholder notifications sent

## Examples

### Example 1: Adding Optional Category Field

**Scenario**: Add optional category classification to articles

**Schema Change**:
```json
// Before (v1.2.0)
{
  "name": "ArticleIngest",
  "namespace": "neuronews.events", 
  "fields": [
    {"name": "article_id", "type": "string"},
    {"name": "title", "type": ["null", "string"], "default": null},
    {"name": "body", "type": ["null", "string"], "default": null}
  ]
}

// After (v1.3.0)
{
  "name": "ArticleIngest",
  "namespace": "neuronews.events",
  "fields": [
    {"name": "article_id", "type": "string"},
    {"name": "title", "type": ["null", "string"], "default": null},
    {"name": "body", "type": ["null", "string"], "default": null},
    {"name": "category", "type": ["null", "string"], "default": null, "doc": "Article category (politics, sports, technology, etc.)"}
  ]
}
```

**Migration Steps**:
1. Minor version bump (1.2.0 → 1.3.0)
2. Update producer to include category field
3. Consumers automatically compatible (optional field)
4. No consumer migration required

### Example 2: Breaking Change - Split Name Field

**Scenario**: Split `author` field into `first_name` and `last_name`

**Schema Changes**:
```json
// v1.x.x (deprecated)
{
  "name": "author",
  "type": ["null", "string"], 
  "default": null,
  "doc": "@deprecated Use first_name and last_name instead. Will be removed in v2.0"
}

// v2.0.0 (new structure)
{
  "fields": [
    {"name": "first_name", "type": ["null", "string"], "default": null},
    {"name": "last_name", "type": ["null", "string"], "default": null}
  ]
}
```

**Migration Timeline**:
- **Week 1**: Deploy v1.4.0 with deprecated `author` field
- **Week 2**: Add `first_name`, `last_name` fields to v1.5.0  
- **Week 3-4**: Producer sends both old and new fields
- **Week 5-8**: Consumers migrate to use new fields
- **Week 9**: Deploy v2.0.0 removing `author` field
- **Week 10**: Switch all consumers to v2.0.0

### Example 3: Type Change Migration

**Scenario**: Change `sentiment_score` from string to double

**Migration Strategy**:
```json
// Phase 1: v1.x.x - Current problematic schema
{"name": "sentiment_score", "type": ["null", "string"], "default": null}

// Phase 2: v1.y.y - Add new typed field
{
  "fields": [
    {
      "name": "sentiment_score", 
      "type": ["null", "string"], 
      "default": null,
      "doc": "@deprecated Use sentiment_value instead"
    },
    {
      "name": "sentiment_value",
      "type": ["null", "double"], 
      "default": null,
      "doc": "Numeric sentiment score (-1.0 to 1.0)"
    }
  ]
}

// Phase 3: v2.0.0 - Remove old string field
{"name": "sentiment_value", "type": ["null", "double"], "default": null}
```

**Consumer Migration Code**:
```python
def get_sentiment_score(article_data):
    """Get sentiment score with fallback handling."""
    
    # Prefer new double field
    if "sentiment_value" in article_data and article_data["sentiment_value"] is not None:
        return float(article_data["sentiment_value"])
    
    # Fallback to string field with conversion
    if "sentiment_score" in article_data and article_data["sentiment_score"] is not None:
        try:
            return float(article_data["sentiment_score"])
        except (ValueError, TypeError):
            logger.warning(f"Could not convert sentiment_score to float: {article_data['sentiment_score']}")
            return 0.0
    
    # Default if neither field available
    return 0.0
```

---

## Quick Reference

### Safe Changes ✅
- Add optional fields with defaults
- Update default values
- Add documentation
- Add new enum values
- Make required fields optional (with defaults)

### Unsafe Changes ❌
- Remove fields
- Change field types
- Rename fields (without dual-field strategy)
- Remove enum values
- Make optional fields required

### Version Bumps
- **Patch** (x.x.+1): Documentation, default values
- **Minor** (x.+1.0): New optional fields, new enum values
- **Major** (+1.0.0): Breaking changes, field removal/rename

### Migration Checklist
1. [ ] Impact assessment completed
2. [ ] Schema compatibility validated
3. [ ] Golden fixtures updated
4. [ ] Consumer migration plan created
5. [ ] Dual-write strategy implemented
6. [ ] Monitoring configured
7. [ ] Rollback plan documented

---

*For questions or support with schema evolution, contact the Data Platform team or create an issue in this repository.*
