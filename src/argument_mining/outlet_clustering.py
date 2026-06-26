"""
Outlet editorial-framing cluster analysis — issue #115.

Embeds each news outlet as a 7-dimensional frame-score vector (from
``document_frames`` aggregated over the last 90 days), runs k-means and
hierarchical (Ward) clustering, picks the best k by silhouette score, and
projects down to 2D via PCA for scatter-plot visualisation.

Public API
----------
  build_outlet_vectors(conn, date_range="90d") -> (sources, matrix)
  run_clustering(sources, matrix, k_min?, k_max?) -> ClusterResult
  store_clusters(result, conn) -> None
  run_cluster_pipeline(conn, lock, date_range?, k_min?, k_max?) -> dict
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# Frame dimension order — matches FRAME_LABELS from dataset.py
FRAME_LABELS = ["economic", "security", "humanitarian", "legal",
                 "political", "scientific", "other"]

_DOMINANT_THRESHOLD = 0.50   # single frame dominates
_BALANCED_GAP = 0.12         # top-2 within this gap → balanced label


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class OutletVector:
    source: str
    source_type: str
    doc_count: int
    vector: np.ndarray          # shape (7,), L2-normalised


@dataclass
class OutletCluster:
    source: str
    source_type: str
    cluster_id: int
    cluster_label: str
    pca_x: float
    pca_y: float
    dominant_frame: str
    doc_count: int
    computed_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class ClusterResult:
    outlets: List[OutletCluster]
    k: int
    method: str          # "kmeans" | "hierarchical"
    silhouette: float
    n_outlets: int
    date_range: str
    computed_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# ---------------------------------------------------------------------------
# Data extraction
# ---------------------------------------------------------------------------

def _date_cutoff(date_range: str) -> Optional[str]:
    from datetime import timedelta
    mapping = {"7d": 7, "30d": 30, "90d": 90, "180d": 180, "365d": 365}
    days = mapping.get(date_range, 90)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    return cutoff


def build_outlet_vectors(conn, date_range: str = "90d") -> Tuple[List[OutletVector], np.ndarray]:
    """
    Aggregate per-outlet frame distributions from DuckDB and return
    (outlet_list, matrix) where matrix is shape (n_outlets, 7).

    Outlets with fewer than 3 documents are excluded to avoid noisy vectors.
    """
    cutoff = _date_cutoff(date_range)
    cutoff_clause = f"AND n.publish_date >= '{cutoff}'" if cutoff else ""

    # news branch — join to news_articles for outlet name
    news_rows = conn.execute(f"""
        SELECT n.source,
               'news' AS source_type,
               df.frame,
               AVG(df.score)                  AS avg_score,
               COUNT(DISTINCT df.document_id) AS doc_count
        FROM document_frames df
        JOIN news_articles n ON df.document_id = n.id
        WHERE n.source IS NOT NULL
          {cutoff_clause}
        GROUP BY n.source, df.frame
    """).fetchall()

    # non-news branch — source_type as proxy for outlet name
    other_rows = conn.execute(f"""
        SELECT df.source_type AS source,
               df.source_type,
               df.frame,
               AVG(df.score)                  AS avg_score,
               COUNT(DISTINCT df.document_id) AS doc_count
        FROM document_frames df
        WHERE df.source_type != 'news'
        GROUP BY df.source_type, df.frame
    """).fetchall()

    # Aggregate into per-outlet dicts
    raw: Dict[str, Dict[str, object]] = {}
    for src, src_type, frame, avg_score, doc_count in list(news_rows) + list(other_rows):
        key = f"{src_type}::{src}"
        if key not in raw:
            raw[key] = {"source": src, "source_type": src_type,
                        "frames": {}, "doc_count": 0}
        raw[key]["frames"][frame] = float(avg_score)       # type: ignore[index]
        raw[key]["doc_count"] = max(int(raw[key]["doc_count"]), int(doc_count))  # type: ignore[arg-type]

    outlets: List[OutletVector] = []
    for data in raw.values():
        if data["doc_count"] < 3:  # type: ignore[operator]
            continue
        vec = np.array([
            float(data["frames"].get(f, 0.0))  # type: ignore[union-attr]
            for f in FRAME_LABELS
        ], dtype=np.float32)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        outlets.append(OutletVector(
            source=str(data["source"]),
            source_type=str(data["source_type"]),
            doc_count=int(data["doc_count"]),  # type: ignore[arg-type]
            vector=vec,
        ))

    if not outlets:
        return [], np.empty((0, len(FRAME_LABELS)), dtype=np.float32)

    matrix = np.stack([o.vector for o in outlets])
    return outlets, matrix


# ---------------------------------------------------------------------------
# Cluster labelling
# ---------------------------------------------------------------------------

def _label_cluster(centroid: np.ndarray) -> Tuple[str, str]:
    """Return (cluster_label, dominant_frame) from a normalised centroid vector."""
    scores = {f: float(centroid[i]) for i, f in enumerate(FRAME_LABELS)}
    ranked = sorted(scores.items(), key=lambda x: -x[1])
    top_frame, top_score = ranked[0]
    second_frame, second_score = ranked[1]

    dominant = top_frame
    if top_score > _DOMINANT_THRESHOLD:
        label = f"{top_frame}-dominant"
    elif (top_score - second_score) < _BALANCED_GAP:
        label = f"balanced-{top_frame}-{second_frame}"
        dominant = top_frame
    else:
        label = f"{top_frame}-focused"

    return label, dominant


# ---------------------------------------------------------------------------
# Clustering
# ---------------------------------------------------------------------------

def run_clustering(
    outlets: List[OutletVector],
    matrix: np.ndarray,
    k_min: int = 2,
    k_max: int = 8,
) -> ClusterResult:
    """
    Run k-means (k_min..k_max) + Ward hierarchical clustering; choose the
    best (method, k) pair by silhouette score.

    Falls back to k=2 with a dummy label when the matrix is too small to score.
    """
    from sklearn.cluster import KMeans, AgglomerativeClustering
    from sklearn.decomposition import PCA
    from sklearn.metrics import silhouette_score

    n = len(outlets)
    date_range = "90d"  # communicated to caller via ClusterResult

    # Need at least 2 samples and 2 clusters to compute silhouette
    effective_kmax = min(k_max, n - 1)
    effective_kmin = min(k_min, effective_kmax)

    best_score = -1.0
    best_labels: np.ndarray = np.zeros(n, dtype=int)
    best_k = effective_kmin
    best_method = "kmeans"

    for k in range(effective_kmin, effective_kmax + 1):
        # k-means
        try:
            km = KMeans(n_clusters=k, n_init="auto", random_state=42)
            km_labels = km.fit_predict(matrix)
            if len(set(km_labels)) > 1:
                s = silhouette_score(matrix, km_labels)
                if s > best_score:
                    best_score = s
                    best_labels = km_labels
                    best_k = k
                    best_method = "kmeans"
        except Exception:
            pass

        # hierarchical (Ward)
        try:
            hc = AgglomerativeClustering(n_clusters=k, linkage="ward")
            hc_labels = hc.fit_predict(matrix)
            if len(set(hc_labels)) > 1:
                s = silhouette_score(matrix, hc_labels)
                if s > best_score:
                    best_score = s
                    best_labels = hc_labels
                    best_k = k
                    best_method = "hierarchical"
        except Exception:
            pass

    # PCA 2D projection
    try:
        n_components = min(2, matrix.shape[1], n)
        pca = PCA(n_components=n_components, random_state=42)
        coords_2d = pca.fit_transform(matrix)
        if coords_2d.shape[1] == 1:
            coords_2d = np.hstack([coords_2d, np.zeros((n, 1))])
    except Exception:
        coords_2d = np.zeros((n, 2))

    # Compute per-cluster centroids for labelling
    cluster_centroids: Dict[int, np.ndarray] = {}
    for i, label_id in enumerate(best_labels):
        cid = int(label_id)
        if cid not in cluster_centroids:
            cluster_centroids[cid] = np.zeros(matrix.shape[1])
        cluster_centroids[cid] += matrix[i]

    cluster_counts: Dict[int, int] = {}
    for label_id in best_labels:
        cluster_counts[int(label_id)] = cluster_counts.get(int(label_id), 0) + 1

    cluster_labels_map: Dict[int, str] = {}
    cluster_dominant_map: Dict[int, str] = {}
    for cid, centroid_sum in cluster_centroids.items():
        centroid = centroid_sum / cluster_counts[cid]
        label, dominant = _label_cluster(centroid)
        cluster_labels_map[cid] = label
        cluster_dominant_map[cid] = dominant

    ts = datetime.now(timezone.utc).isoformat()
    result_outlets: List[OutletCluster] = []
    for i, ov in enumerate(outlets):
        cid = int(best_labels[i])
        result_outlets.append(OutletCluster(
            source=ov.source,
            source_type=ov.source_type,
            cluster_id=cid,
            cluster_label=cluster_labels_map.get(cid, f"cluster-{cid}"),
            pca_x=float(coords_2d[i, 0]),
            pca_y=float(coords_2d[i, 1]),
            dominant_frame=cluster_dominant_map.get(cid, "other"),
            doc_count=ov.doc_count,
            computed_at=ts,
        ))

    return ClusterResult(
        outlets=result_outlets,
        k=best_k,
        method=best_method,
        silhouette=round(float(best_score), 4),
        n_outlets=n,
        date_range=date_range,
        computed_at=ts,
    )


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def store_clusters(result: ClusterResult, conn) -> None:
    """Write cluster assignments to ``outlet_clusters`` (full replace)."""
    conn.execute("DELETE FROM outlet_clusters")
    for o in result.outlets:
        conn.execute(
            """
            INSERT INTO outlet_clusters
                (source, source_type, cluster_id, cluster_label,
                 pca_x, pca_y, dominant_frame, doc_count, computed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [o.source, o.source_type, o.cluster_id, o.cluster_label,
             o.pca_x, o.pca_y, o.dominant_frame, o.doc_count, o.computed_at],
        )


# ---------------------------------------------------------------------------
# Pipeline entry point
# ---------------------------------------------------------------------------

def run_cluster_pipeline(
    conn, lock,
    date_range: str = "90d",
    k_min: int = 2,
    k_max: int = 8,
) -> dict:
    """
    Full pipeline: extract vectors → cluster → persist.

    Returns a summary dict suitable for API/MCP responses.
    """
    try:
        with lock:
            outlets, matrix = build_outlet_vectors(conn, date_range=date_range)
    except Exception as e:
        return {"error": f"vector build failed: {e}"}

    if len(outlets) < 2:
        return {
            "error": "not enough outlets with frame data",
            "n_outlets": len(outlets),
        }

    try:
        result = run_clustering(outlets, matrix, k_min=k_min, k_max=k_max)
        result.date_range = date_range
    except Exception as e:
        return {"error": f"clustering failed: {e}"}

    try:
        with lock:
            store_clusters(result, conn)
    except Exception as e:
        return {"error": f"store failed: {e}"}

    return {
        "n_outlets": result.n_outlets,
        "k": result.k,
        "method": result.method,
        "silhouette": result.silhouette,
        "date_range": date_range,
        "computed_at": result.computed_at,
    }
