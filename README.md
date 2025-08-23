# NeuroNews – AI-Powered News Intelligence Pipeline

📡 **Real-Time ETL Pipeline for Politics & Technology News** | 🚀 **AI-Driven Insights** | 📊 **Sentiment & Trend Analysis**

---

## 🔍 Overview

**NeuroNews** is an advanced **ETL pipeline** designed to **scrape, analyze, and visualize** politics and technology news using **AI-powered NLP, sentiment analysis, and knowledge graph-based insights**. Built on **AWS cloud infrastructure**, it enables **real-time event detection, entity linking, and customizable dashboards** for deeper news intelligence.

---

## ⚡ Features

✅ **Automated News Scraping** – Extracts articles from multiple sources using **Scrapy + Playwright/Selenium**.

✅ **AI-Powered Event Detection** – Clusters related news articles into significant political & tech events.

✅ **NLP & Sentiment Analysis** – Extracts **named entities, sentiment scores, and keyword trends**.

✅ **Knowledge Graph Integration** – Links entities, policies, and historical context using **AWS Neptune**.

✅ **Custom Dashboards & Reports** – Generates **interactive visualizations and AI-driven summaries**.

✅ **Historical News Context** – Tracks **timeline-based evolution** of news topics.

✅ **API for Insights & Reporting** – REST API for accessing structured **event summaries, trends, and sentiment data**.

✅ **AWS Cloud Integration** – Serverless processing with **AWS Lambda, Redshift, S3, Step Functions & SageMaker**.

---

## 📌 Use Cases

🔹 **Journalists & Analysts** – Quickly access AI-generated summaries and sentiment shifts.

🔹 **Policy Makers & Think Tanks** – Track **legislative impact & policy evolution**.

🔹 **Business Intelligence Teams** – Analyze **tech industry trends & company sentiment**.

🔹 **Researchers & Data Scientists** – Leverage **knowledge graph insights & historical data**.

---

## 🛠️ Tech Stack

🔹 **Backend & Scraping**: Python, Scrapy, Selenium, Playwright, AWS Lambda
🔹 **NLP & AI Models**: Hugging Face Transformers, AWS Comprehend, GPT-4, Pegasus
🔹 **Database & Storage**: AWS Redshift, AWS Neptune (Graph DB), S3, DynamoDB
🔹 **Event Detection & Summarization**: BERT Embeddings, k-Means Clustering
🔹 **Visualization & Reporting**: AWS QuickSight, Streamlit, Matplotlib

---

## 🚀 Getting Started

### 📁 Project Structure

This project is organized for clean development and maintenance. See [`docs/PROJECT_STRUCTURE.md`](docs/PROJECT_STRUCTURE.md) for a detailed overview of the directory structure and organization guidelines.

### 1️⃣ Clone the Repository

```bash

git clone https://github.com/your-username/newsgraph-ai.git
cd newsgraph-ai

```text

### 2️⃣ Install Dependencies

```bash

pip install -r requirements.txt

```text

### 3️⃣ Docker Development (Recommended)

```bash

# Run with Docker Compose for development

docker compose up --build

# Run tests in containerized environment

docker compose -f docker-compose.test-minimal.yml up --build --abort-on-container-exit

```text

### 4️⃣ Configure AWS Credentials

- Add your **AWS_ACCESS_KEY_ID** & **AWS_SECRET_ACCESS_KEY**.

- Ensure **IAM roles** have permissions for Lambda, S3, Redshift, and Neptune.

### 5️⃣ Run Tests and Generate Coverage Report

Before running the test suite make sure the Terraform CLI is installed. On
Ubuntu you can install it from HashiCorp's APT repository:

```bash

sudo apt-get install -y gnupg software-properties-common curl
curl -fsSL https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list
sudo apt-get update && sudo apt-get install terraform

```text

This ensures the Terraform validation steps succeed.

```bash

# Initialize and validate the Terraform code just like the CI workflow

terraform -chdir=deployment/terraform init -backend=false
terraform -chdir=deployment/terraform validate

```text

```bash

# Run tests with coverage reporting

pytest

# View the coverage report

# Open coverage_report/index.html in your browser

```text

The coverage report provides:

- Line-by-line code coverage analysis

- Branch coverage statistics

- Untested code identification

- Module-level coverage summaries

### 6️⃣ Run Demo Scripts

```bash

# Explore available demos

ls demo/

# Run specific demo (example)

python demo/demo_sentiment_pipeline.py

```text

### 7️⃣ Run the Scraper

```bash

python src/scraper.py

```text

### 8️⃣ Run the NLP Pipeline

```bash

python src/nlp_processor.py

```text

### 9️⃣ Access Dashboards & Reports

- AWS QuickSight for **visualizations & insights**.

- REST API for **news sentiment, event tracking, and historical context**.

---

## 📅 Roadmap

🛠 **Phase 1:** Web Scraping & Data Ingestion ✅

🛠 **Phase 2:** NLP Processing & Sentiment Analysis ✅

🛠 **Phase 3:** Event Detection & AI Summarization ✅

🛠 **Phase 4:** Knowledge Graph & Deep Linking ✅

🛠 **Phase 5:** Interactive Dashboards & API Development ✅

🚀 **Future Expansion:** Predictive analytics, real-time fact-checking, blockchain-based news verification

---

## 📬 Contact & Contributions

🔗 **GitHub Issues:** Report bugs & request features.

🔗 **Pull Requests:** Contributions welcome! See **CONTRIBUTING.md** for guidelines.

📧 **Email:** ikey168@proton.me

🔖 **License:** MIT

