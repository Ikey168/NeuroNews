# NeuroNews Streamlit Dashboard (Issue #50)

## Overview

A comprehensive interactive dashboard built with Streamlit for visualizing NeuroNews data including entity relationships, news trends, and event clusters.

## Features ✨

### 1. Custom Dashboard with Streamlit Framework ✅
- Interactive web-based interface
- Responsive design with wide layout
- Real-time data updates
- Configurable sidebar controls

### 2. Interactive Graphs for Entity Relationships ✅
- Network visualization using NetworkX and Plotly
- Entity nodes colored by type (PERSON, ORG, GPE, EVENT)
- Interactive hover information
- Relationship mapping between entities

### 3. Latest News Trends Visualization ✅
- Time series charts showing article counts over time
- Topic-based filtering
- Dynamic date range selection
- Article preview cards with expandable details

### 4. Event Clusters Detection and Display ✅
- Bubble chart visualization of event impact vs trending scores
- Event cluster size representation
- Category-based color coding
- Timeline view of events

### 5. API Integration with Dynamic Filtering ✅
- Real-time data fetching from NeuroNews API
- Configurable topic and time filters
- Article limit controls
- Error handling and retry logic

## Installation

### Prerequisites
- Python 3.8+
- NeuroNews API running on localhost:8000

### Install Dependencies
```bash
pip install -r requirements.txt
```

Required packages:
- `streamlit>=1.28.0`
- `plotly>=5.17.0`
- `networkx>=3.1`
- `pandas>=1.3.0`
- `requests>=2.28.0`

## Usage

### Quick Start
```bash
# Run the dashboard
streamlit run src/dashboards/streamlit_dashboard.py

# Or use the launcher script
python launch_dashboard.py
```

### Advanced Usage
```bash
# Run with custom configuration
python launch_dashboard.py --port 8502 --host 0.0.0.0 --api-url http://api.neuronews.com

# Development mode
python launch_dashboard.py --dev --skip-checks
```

## Dashboard Components

### Main Interface
- **Topic Filter**: Search articles by specific topics
- **Time Range**: Select hours of data to display (1-168 hours)
- **Article Limit**: Control number of articles fetched (10-200)
- **Refresh Button**: Clear cache and reload data

### Visualizations

#### News Trends Chart
- Line chart showing article counts over time
- Interactive tooltips with date/count information
- Supports category-based color coding

#### Entity Relationship Network
- Interactive network graph of entities and relationships
- Node size represents connection count
- Color-coded by entity type
- Draggable and zoomable interface

#### Event Clusters Visualization
- Bubble chart showing impact vs trending scores
- Size represents cluster size (number of articles)
- Color represents event type
- Interactive hover data

### Data Cards
- Recent articles with expandable previews
- Entity statistics by type
- Top events by impact and trending scores
- Real-time metrics display

## API Endpoints Used

| Endpoint | Description | Parameters |
|----------|-------------|------------|
| `/news/articles/topic/{topic}` | Fetch articles by topic | `limit` |
| `/api/v1/breaking-news` | Get breaking news events | `hours`, `limit` |
| `/graph/entities` | Fetch knowledge graph entities | `limit` |
| `/graph/entity/{id}/relationships` | Get entity relationships | - |

## Configuration

### Environment Variables
- `NEURONEWS_API_URL`: API base URL (default: http://localhost:8000)
- `STREAMLIT_SERVER_PORT`: Dashboard port (default: 8501)
- `ENVIRONMENT`: Environment mode (development/production)

### Dashboard Configuration
The dashboard uses configuration files in `src/dashboards/`:
- `dashboard_config.py`: Main configuration settings
- `api_client.py`: API client with caching
- `visualization_components.py`: Advanced chart components

## Architecture

```
src/dashboards/
├── streamlit_dashboard.py      # Main dashboard application
├── dashboard_config.py         # Configuration settings
├── api_client.py              # Enhanced API client
└── visualization_components.py # Advanced visualizations

Supporting Files:
├── launch_dashboard.py         # Dashboard launcher script
├── test_streamlit_dashboard.py # Validation tests
└── requirements.txt           # Updated dependencies
```

## Features in Detail

### Caching Strategy
- Uses Streamlit's `@st.cache_data` for API responses
- 5-minute TTL in production, 1-minute in development
- Resource caching for API clients

### Error Handling
- Graceful degradation when API is unavailable
- Retry logic with exponential backoff
- User-friendly error messages

### Performance Optimizations
- Lazy loading of large datasets
- Chunked data processing
- Limited node counts for network graphs
- Efficient relationship batching

### Responsive Design
- Wide layout for optimal screen usage
- Collapsible sidebar for mobile
- Adaptive chart sizing
- Progressive loading indicators

## Development

### Running Tests
```bash
python test_streamlit_dashboard.py
```

### Adding New Visualizations
1. Create component in `visualization_components.py`
2. Add configuration in `dashboard_config.py`
3. Import and use in `streamlit_dashboard.py`

### API Client Extension
The `api_client.py` provides:
- Automatic retry logic
- Response caching
- Batch requests
- Error handling

## Troubleshooting

### Common Issues

**Dashboard won't start**
- Check if Streamlit is installed: `pip install streamlit`
- Verify port availability: `netstat -an | grep 8501`

**No data displayed**
- Ensure NeuroNews API is running on localhost:8000
- Check API health: `curl http://localhost:8000/health`
- Verify network connectivity

**Performance issues**
- Reduce article/entity limits in sidebar
- Clear browser cache
- Check system resources

### API Connection Issues
```bash
# Test API connectivity
curl -X GET "http://localhost:8000/health"
curl -X GET "http://localhost:8000/news/articles/topic/technology?limit=5"
```

## Contributing

1. Follow existing code structure
2. Add appropriate error handling
3. Update configuration as needed
4. Test with `test_streamlit_dashboard.py`
5. Update this README for new features

## License

Part of the NeuroNews project. See main project LICENSE file.

---

**Issue #50 Implementation Status: ✅ COMPLETE**

All requirements have been successfully implemented:
- ✅ Custom dashboard with Streamlit framework
- ✅ Interactive graphs for entity relationships  
- ✅ Latest news trends visualization
- ✅ Event clusters detection and display
- ✅ API integration with dynamic filtering
