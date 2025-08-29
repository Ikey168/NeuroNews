# kubectl-cost Developer Quick Reference

## 🏷️ Immediate Cost Insights

Get instant cost feedback for your development work:

```bash
# Quick overview
./scripts/kubectl-cost-dev.sh

# Pipeline-specific costs
./scripts/kubectl-cost-dev.sh pipelines

# Generate PR cost summary
./scripts/kubectl-cost-dev.sh pr
```

## 📊 Nightly Cost Reports

Automated cost analysis posted daily to:
- **GitHub Discussions**: Searchable cost history  
- **Slack #finops-team**: Summary with quick access links

## 💰 PR Cost Transparency

Add cost impact to your pull requests:

```bash
./scripts/kubectl-cost-dev.sh pr
# Copy pr-cost-summary.md content to PR description
```

## 🔗 Cost Monitoring Stack

- **Real-time**: kubectl-cost developer tool
- **Daily**: Nightly automated reports  
- **Trends**: [FinOps Dashboard](http://grafana:3000/d/neuronews-finops/)
- **Alerts**: [Budget Monitoring](http://prometheus:9090/alerts)

## 📚 Full Documentation

See [kubectl-cost Integration Guide](docs/finops/kubectl-cost-integration.md) for complete setup and usage instructions.
