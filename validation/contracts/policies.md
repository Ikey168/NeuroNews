# Data Contracts Governance Policies

This document defines the governance policies, procedures, and standards for data contracts in the NeuroNews ecosystem.

## Table of Contents

- [Schema Design Principles](#schema-design-principles)
- [Compatibility Policies](#compatibility-policies)
- [Approval Workflows](#approval-workflows)
- [Naming Conventions](#naming-conventions)
- [Quality Standards](#quality-standards)
- [Security and Privacy](#security-and-privacy)
- [Monitoring and Compliance](#monitoring-and-compliance)

## Schema Design Principles

### 1. Consumer-First Design

**Principle**: Design schemas based on consumer needs, not producer convenience.

**Guidelines**:
- Interview downstream consumers before schema design
- Provide only necessary fields to minimize coupling
- Use clear, descriptive field names
- Include comprehensive documentation

**Example**:
```json
// Good: Consumer-focused article schema
{
  "type": "record",
  "name": "ArticlePublished",
  "fields": [
    {"name": "articleId", "type": "string", "doc": "Unique article identifier"},
    {"name": "title", "type": "string", "doc": "Article headline for display"},
    {"name": "summary", "type": "string", "doc": "Brief article summary (max 500 chars)"},
    {"name": "publishedAt", "type": "long", "logicalType": "timestamp-millis"}
  ]
}
```

### 2. Evolutionary Design

**Principle**: Design schemas to evolve gracefully over time.

**Guidelines**:
- Always provide default values for new fields
- Use unions for optional fields: `["null", "string"]`
- Prefer field addition over modification
- Plan for future extensibility

### 3. Self-Documenting Schemas

**Principle**: Schemas should be understandable without external documentation.

**Guidelines**:
- Include `doc` fields for all types and fields
- Use descriptive names over abbreviations
- Specify units for numeric fields (bytes, seconds, etc.)
- Include validation constraints in documentation

## Compatibility Policies

### BACKWARD_TRANSITIVE Policy

**Scope**: Applied to ALL event subjects in schema registry

**Rules**:

✅ **Allowed Changes**:
- Adding optional fields with default values
- Adding new enum values (at the end)
- Widening numeric types (int32 → int64)
- Adding new union branches
- Documentation updates

❌ **Prohibited Changes**:
- Removing fields
- Changing field types (except widening)
- Changing field names
- Removing enum values
- Making optional fields required

### Compatibility Matrix

| Change Type | Backward | Forward | Full | Impact |
|-------------|----------|---------|------|---------|
| Add optional field | ✅ | ❌ | ❌ | Low |
| Remove field | ❌ | ✅ | ❌ | High |
| Change field type | ❌ | ❌ | ❌ | Critical |
| Rename field | ❌ | ❌ | ❌ | Critical |
| Add enum value | ✅ | ❌ | ❌ | Medium |
| Remove enum value | ❌ | ✅ | ❌ | High |

### Breaking Change Process

When breaking changes are unavoidable:

1. **Create new schema subject** with version suffix
   - Old: `news.article.ingested-value`
   - New: `news.article.ingested-v2-value`

2. **Dual publishing period** (minimum 30 days)
   - Producers send to both subjects
   - Consumers gradually migrate

3. **Deprecation notice** (minimum 60 days)
   - Mark old subject as deprecated
   - Provide migration documentation

4. **Sunset old subject**
   - Stop publishing to old subject
   - Archive schema for reference

## Approval Workflows

### Automatic Approval

**Criteria**: Non-breaking changes that pass all validation

**Process**:
1. Developer commits schema changes
2. CI/CD pipeline validates schema
3. Compatibility check passes
4. Schema automatically registered in development

**Validation Checks**:
- Schema syntax validation
- Backward compatibility check
- Naming convention compliance
- Documentation completeness

### Manual Approval

**Criteria**: Breaking changes or high-impact modifications

**Process**:
1. Developer creates pull request with schema changes
2. Data platform team reviews within 2 business days
3. Stakeholder consultation for significant changes
4. Approval requires 2+ data team members
5. Manual registration in production registry

**Review Checklist**:
- [ ] Business justification for breaking change
- [ ] Migration plan for affected consumers
- [ ] Updated documentation
- [ ] Rollback strategy defined

### Emergency Changes

**Criteria**: Critical production issues requiring immediate schema changes

**Process**:
1. Incident manager approves emergency change
2. Minimal viable schema modification
3. Immediate registration in production
4. Post-incident review within 24 hours
5. Proper governance process for permanent fix

## Naming Conventions

### Subject Naming

**Pattern**: `{domain}.{entity}.{event_type}[-{version}]`

**Examples**:
- `news.article.ingested-value`
- `analytics.sentiment.calculated-value`
- `search.query.executed-value`
- `user.profile.updated-v2-value` (breaking change)

### Field Naming

**Guidelines**:
- Use camelCase for field names
- Be explicit: `publishedAt` not `date`
- Include units: `timeoutSeconds`, `sizeBytes`
- Use boolean prefixes: `isPublished`, `hasImages`

**Examples**:
```avro
{
  "name": "createdAt",           // Timestamp fields
  "name": "contentLengthBytes",  // Size with units
  "name": "isBreakingNews",      // Boolean flags
  "name": "maxRetryCount",       // Limits and constraints
  "name": "sourceUrl"            // References to external resources
}
```

### Enum Values

**Guidelines**:
- Use UPPER_SNAKE_CASE
- Be descriptive and unambiguous
- Plan for extensibility

**Example**:
```avro
{
  "type": "enum",
  "name": "ArticleStatus",
  "symbols": [
    "DRAFT",
    "UNDER_REVIEW", 
    "PUBLISHED",
    "ARCHIVED",
    "DELETED"
  ]
}
```

## Quality Standards

### Schema Validation

**Required Checks**:
- Syntax validation (Avro/JSON Schema)
- Semantic validation (business rules)
- Compatibility testing
- Documentation completeness
- Performance impact assessment

### Testing Requirements

**Unit Tests**:
- Schema serialization/deserialization
- Compatibility with sample data
- Edge case handling

**Integration Tests**:
- End-to-end data flow validation
- Consumer compatibility testing
- Performance benchmarking

### Documentation Standards

**Required Documentation**:
- Field descriptions with business context
- Usage examples with sample data
- Migration guides for version changes
- Performance characteristics
- Known limitations

**Example**:
```avro
{
  "type": "record",
  "name": "ArticleIngested",
  "doc": "Event published when a news article is successfully ingested into the system",
  "fields": [
    {
      "name": "articleId",
      "type": "string",
      "doc": "Globally unique article identifier (UUID v4 format)"
    },
    {
      "name": "sourceTimestamp",
      "type": "long",
      "logicalType": "timestamp-millis",
      "doc": "Original publication timestamp from source (milliseconds since epoch)"
    }
  ]
}
```

## Security and Privacy

### Data Classification

**Public**: No restrictions
- Article titles and summaries
- Public metrics and counts
- System health data

**Internal**: Company employees only
- User behavior analytics
- Performance metrics
- System configuration data

**Confidential**: Restricted access
- User personal information
- Financial data
- Security logs

**Restricted**: Highest protection
- Authentication credentials
- Encryption keys
- Audit logs

### PII Handling

**Guidelines**:
- Never include PII in event schemas
- Use tokenized references (user IDs)
- Implement field-level encryption for sensitive data
- Apply data retention policies

**Example**:
```avro
// ❌ Bad: Contains PII
{
  "name": "userEmail",
  "type": "string"
}

// ✅ Good: Uses tokenized reference
{
  "name": "userId",
  "type": "string",
  "doc": "Tokenized user identifier (no PII)"
}
```

### Encryption Requirements

**At Rest**: All schemas stored in encrypted registries
**In Transit**: TLS 1.3 for all registry communication
**Field Level**: Sensitive fields encrypted with envelope encryption

## Monitoring and Compliance

### Registry Monitoring

**Metrics**:
- Schema registration rate
- Compatibility check failures
- Consumer lag by schema version
- Validation error rates

**Alerts**:
- Breaking change attempts
- Schema registry downtime
- High validation error rates
- Unauthorized schema access

### Compliance Reporting

**Monthly Reports**:
- Schema evolution summary
- Compatibility violation incidents
- Consumer adoption rates
- Data quality metrics

**Quarterly Reviews**:
- Governance policy effectiveness
- Schema design pattern analysis
- Consumer satisfaction survey
- Performance impact assessment

### Audit Trail

**Tracked Events**:
- Schema registration/modification
- Compatibility check results
- Access attempts and authorization
- Policy violation incidents

**Retention**: 2 years for compliance
**Access**: Data governance team only

## Enforcement

### Automated Enforcement

**CI/CD Gates**:
- Schema validation in pull requests
- Compatibility checks before merge
- Automated testing requirements
- Documentation completeness verification

### Policy Violations

**Severity Levels**:

**Critical**: Breaking change without approval
- Immediate rollback required
- Incident escalation
- Mandatory post-mortem

**High**: Missing documentation or validation
- Block deployment until resolved
- Data team notification
- Fix required within 24 hours

**Medium**: Naming convention violations
- Warning notifications
- Fix required within 1 week
- No deployment blocking

**Low**: Style guide deviations
- Informational warnings
- Fix in next development cycle

### Escalation Process

1. **Automated Detection**: Policy violation detected
2. **Notification**: Relevant teams notified immediately
3. **Investigation**: Data platform team investigates within 2 hours
4. **Resolution**: Violation resolved according to severity
5. **Post-Mortem**: Critical violations require incident review

## Review and Updates

**Policy Review**: Quarterly review of governance policies
**Process Improvement**: Monthly retrospectives on workflow efficiency
**Community Feedback**: Regular surveys of schema producers/consumers
**Industry Standards**: Annual review of industry best practices

---

**Last Updated**: August 28, 2025
**Next Review**: November 28, 2025
**Owner**: Data Platform Team
