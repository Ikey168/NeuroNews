# Kubernetes Secrets Management

## Security Notice

⚠️ **IMPORTANT**: The `app-secrets.yaml` file contains placeholder values that must be replaced with actual credentials during deployment. Never commit actual secrets to version control.

## Deployment Instructions

### 1. Replace Secret Values

Before deploying, replace all placeholder values in `app-secrets.yaml` with actual base64-encoded credentials:

```bash
# Example: Encode a database URL
echo -n "postgresql://user:password@postgres-service:5432/neuronews" | base64

# Replace REPLACE_WITH_ACTUAL_DATABASE_URL_B64 with the output
```

### 2. Alternative: Use kubectl to create secrets directly

Instead of using the YAML file, create secrets directly with kubectl:

```bash
# Database secrets
kubectl create secret generic neuronews-secrets \
  --from-literal=database-url="postgresql://user:password@postgres-service:5432/neuronews" \
  --from-literal=database-username="user" \
  --from-literal=database-password="password" \
  --from-literal=openai-api-key="sk-your-actual-key" \
  --from-literal=news-api-key="your-news-api-key" \
  --from-literal=jwt-secret="your-jwt-secret" \
  --from-literal=aws-access-key-id="your-aws-access-key" \
  --from-literal=aws-secret-access-key="your-aws-secret-key" \
  --namespace=neuronews

# Docker registry credentials
kubectl create secret docker-registry registry-credentials \
  --docker-server=your-registry-server \
  --docker-username=your-username \
  --docker-password=your-password \
  --docker-email=your-email \
  --namespace=neuronews
```

### 3. Using External Secret Management

For production environments, consider using:

- **AWS Secrets Manager** with External Secrets Operator
- **HashiCorp Vault** with Vault Secrets Operator
- **Azure Key Vault** with Secret Store CSI Driver
- **Google Secret Manager** with Secret Manager CSI Driver

### 4. Security Best Practices

1. **Never commit actual secrets to Git**
2. **Use different secrets for different environments**
3. **Rotate secrets regularly**
4. **Limit secret access with RBAC**
5. **Enable audit logging for secret access**
6. **Use sealed-secrets or external secret management in production**

## Secret Structure

### neuronews-secrets
Contains application-level secrets:
- Database connection credentials
- API keys (OpenAI, News API)
- JWT signing secret
- AWS credentials

### registry-credentials
Contains Docker registry authentication for pulling private images.

## Troubleshooting

### Secret not found errors
```bash
# Check if secrets exist
kubectl get secrets -n neuronews

# Describe secret to see keys (values will be hidden)
kubectl describe secret neuronews-secrets -n neuronews
```

### Base64 encoding/decoding
```bash
# Encode
echo -n "your-secret-value" | base64

# Decode (for verification)
echo "eW91ci1zZWNyZXQtdmFsdWU=" | base64 -d
```
