"""
Influence Network API Routes

This module provides REST API endpoints for influence network analysis
within the knowledge graph.
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, List, Optional
import logging

from src.knowledge_graph.influence_network_analyzer import InfluenceNetworkAnalyzer

# Initialize router
router = APIRouter(prefix="/api/influence", tags=["influence"])

# Initialize analyzer
analyzer = InfluenceNetworkAnalyzer()

logger = logging.getLogger(__name__)


@router.get("/health")
async def health_check():
    """Health check endpoint for influence analysis service."""
    return {"status": "healthy", "service": "influence_network_analyzer"}


@router.get("/stats")
async def get_network_stats():
    """Get influence network statistics."""
    try:
        stats = analyzer.get_network_stats()
        return {"success": True, "data": stats}
    except Exception as e:
        logger.error(f"Error getting network stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/top-influencers")
async def get_top_influencers(limit: int = 10):
    """Get top influential nodes in the network."""
    try:
        if limit > 100:
            limit = 100
        if limit < 1:
            limit = 1
            
        influencers = analyzer.get_top_influencers(n=limit)
        
        return {
            "success": True,
            "data": [
                {
                    "node_id": inf.node_id,
                    "influence_score": inf.influence_score,
                    "connections": inf.connections,
                    "metadata": inf.metadata
                }
                for inf in influencers
            ]
        }
    except Exception as e:
        logger.error(f"Error getting top influencers: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/path/{source}/{target}")
async def get_influence_path(source: str, target: str):
    """Get influence path between two nodes."""
    try:
        path = analyzer.analyze_influence_path(source, target)
        
        if path is None:
            raise HTTPException(
                status_code=404, 
                detail=f"No path found between {source} and {target}"
            )
            
        return {
            "success": True,
            "data": {
                "source": source,
                "target": target,
                "path": path,
                "path_length": len(path) - 1
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting influence path: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/nodes")
async def add_node(node_data: Dict):
    """Add a node to the influence network."""
    try:
        node_id = node_data.get("node_id")
        if not node_id:
            raise HTTPException(status_code=400, detail="node_id is required")
            
        metadata = node_data.get("metadata", {})
        analyzer.add_node(node_id, metadata)
        
        return {
            "success": True,
            "message": f"Node {node_id} added successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding node: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/edges")
async def add_edge(edge_data: Dict):
    """Add an edge to the influence network."""
    try:
        source = edge_data.get("source")
        target = edge_data.get("target")
        weight = edge_data.get("weight", 1.0)
        
        if not source or not target:
            raise HTTPException(
                status_code=400, 
                detail="Both source and target are required"
            )
            
        analyzer.add_edge(source, target, weight)
        
        return {
            "success": True,
            "message": f"Edge {source} -> {target} added successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding edge: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/calculate-scores")
async def calculate_influence_scores():
    """Calculate influence scores for all nodes."""
    try:
        scores = analyzer.calculate_influence_scores()
        
        return {
            "success": True,
            "message": "Influence scores calculated successfully",
            "data": {"scores": scores, "node_count": len(scores)}
        }
    except Exception as e:
        logger.error(f"Error calculating influence scores: {e}")
        raise HTTPException(status_code=500, detail=str(e))
