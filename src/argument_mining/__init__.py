"""
Argument Mining — claim detection, stance classification, frame analysis, position extraction,
position follow-through tracking, contested-claim conflict graph, and attribution classification.

Entry points:
    from src.argument_mining.models import predict_claims, predict_stance
    from src.argument_mining.frames import predict_frames
    from src.argument_mining.positions import extract_positions, run_position_pipeline
    from src.argument_mining.position_tracker import check_position_followthrough, run_followthrough_batch
    from src.argument_mining.conflict_graph import compute_claim_conflicts, build_conflict_graph, cosine_similarity
    from src.argument_mining.attribution import classify_attribution, run_attribution_batch
    from src.argument_mining.metadata import extract_actors, store_actors, run_actor_batch
    from src.argument_mining.outlet_clustering import run_cluster_pipeline, build_outlet_vectors, run_clustering
    from src.argument_mining.outlet_scorer import compute_outlet_scores, run_scorer_batch
"""
