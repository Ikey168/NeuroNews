# Disabled Workflows

This directory contains GitHub Actions workflow files that have been temporarily disabled due to configuration issues.

## Files in this directory:

- `ci.yml` - Had commented out name and triggers
- `s3-storage.yml` - Had commented out name and triggers  
- `ci-cd-containers.yml` - Had commented out name and triggers
- `neptune-cd.yml` - Had commented out name and triggers
- `tests.yml` - Had commented out name and triggers

## Issues found:

These workflow files had their `name:` and `on:` sections commented out, which makes them invalid YAML for GitHub Actions. This was causing workflow parsing errors.

## To re-enable:

1. Uncomment the `name:` and `on:` sections
2. Ensure the workflow configuration is valid
3. Move back to `.github/workflows/` directory
4. Test the workflow runs successfully

## Current Active Workflows:

- `pr-validation.yml` - Main PR validation pipeline
- `ci-cd-pipeline.yml` - Main CI/CD pipeline  
- `canary-deployment.yml` - Canary deployment workflow
- `pr-testing.yml` - PR testing workflow
- `containerized-tests.yml` - Container-based tests
- `deploy.yml` - Deployment workflow
- `terraform.yml` - Infrastructure testing
- `test-news-api.yml` - API testing
