# Article Clustering and Event Detection Implementation

## Overview

This module implements BERT embeddings + k-means clustering to detect related articles

and identify emerging news events from similar stories.

## Key Components

1. **Article Embedder** - Generate BERT embeddings for articles

2. **Event Clusterer** - K-means clustering for event detection

3. **Event Database** - Store event clusters in Redshift

4. **Breaking News API** - REST endpoints for accessing events

## Database Schema

- `event_clusters` table for storing cluster information

- `article_cluster_assignments` table for article-cluster relationships

## API Endpoints

- `/breaking_news?category=Technology` - Get breaking news by category

- `/events/clusters` - Get all event clusters

- `/events/{cluster_id}/articles` - Get articles in a specific cluster

## Dependencies

- sentence-transformers for BERT embeddings

- scikit-learn for k-means clustering

- psycopg2 for database operations

- FastAPI for REST endpoints

