"""
Argument Mining — claim detection, stance classification, frame analysis, position extraction,
position follow-through tracking, and contested-claim conflict graph.

Entry points:
    from src.argument_mining.models import predict_claims, predict_stance
    from src.argument_mining.frames import predict_frames
    from src.argument_mining.positions import extract_positions, run_position_pipeline
    from src.argument_mining.position_tracker import check_position_followthrough, run_followthrough_batch
    from src.argument_mining.conflict_graph import compute_claim_conflicts, build_conflict_graph, cosine_similarity
"""
