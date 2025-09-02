import os
import re

def get_target_path(test_name):
    if 'sentiment_routes' in test_name:
        return 'routes/test_sentiment_routes.py'
    if 'graph_routes' in test_name:
        return 'routes/test_graph_routes.py'
    if 'news_routes' in test_name:
        return 'routes/test_news_routes.py'
    if 'graph_search_routes' in test_name:
        return 'routes/test_graph_search_routes.py'
    if 'waf_middleware' in test_name:
        return 'security/test_waf_middleware.py'
    if 'event_timeline_service' in test_name:
        return 'services/test_event_timeline_service.py'
    if 'jwt_auth' in test_name:
        return 'auth/test_jwt_auth.py'
    if 'api_key_manager' in test_name:
        return 'auth/test_api_key_manager.py'
    if 'optimized_api' in test_name:
        return 'graph/test_optimized_api.py'
    if 'aws_rate_limiting' in test_name:
        return 'security/test_aws_rate_limiting.py'
    if 'app' in test_name:
        return 'app/test_app.py'
    if 'handler' in test_name:
        return 'handlers/test_handler.py'
    if 'logging_config' in test_name:
        return 'logging/test_logging_config.py'
    if 'rbac' in test_name:
        return 'rbac/test_rbac_system.py'
    if 'error_handlers' in test_name:
        return 'handlers/test_error_handlers.py'
    if 'aws_waf_manager' in test_name:
        return 'security/test_aws_waf_manager.py'
    if 'audit_log' in test_name:
        return 'auth/test_audit_log.py'
    if 'permissions' in test_name:
        return 'auth/test_permissions.py'
    if 'rate_limit_middleware' in test_name:
        return 'middleware/test_rate_limit_middleware.py'
    if 'quicksight' in test_name:
        return 'routes/test_quicksight_routes.py'
    if 'search_routes' in test_name:
        return 'routes/test_search_routes.py'
    if 'veracity' in test_name:
        return 'routes/test_veracity_routes.py'
    if 'topic' in test_name:
        return 'routes/test_topic_routes.py'
    if 'influence' in test_name:
        return 'routes/test_influence_routes.py'
    if 'knowledge_graph' in test_name:
        return 'routes/test_knowledge_graph_routes.py'
    if 'event_timeline_routes' in test_name:
        return 'routes/test_event_timeline_routes.py'
    if 'enhanced_kg_routes' in test_name:
        return 'routes/test_enhanced_kg_routes.py'
    return None

def refactor_tests():
    coverage_dir = 'tests/coverage'
    unit_dir = 'tests/unit'

    if not os.path.exists(unit_dir):
        os.makedirs(unit_dir)

    for filename in os.listdir(coverage_dir):
        if filename.endswith('.py') and filename.startswith('test_'):
            filepath = os.path.join(coverage_dir, filename)
            with open(filepath, 'r') as f:
                content = f.read()

            # Split content into individual tests
            tests = re.split(r'\n(?=def test_)', content)
            class_def = ''
            if tests[0].strip().startswith('class'):
                class_def = tests[0]
                tests = tests[1:]

            for test_content in tests:
                match = re.search(r'def (test_\w+)', test_content)
                if not match:
                    continue
                
                test_name = match.group(1)
                target_path = get_target_path(test_name)

                if target_path:
                    target_filepath = os.path.join(unit_dir, target_path)
                    os.makedirs(os.path.dirname(target_filepath), exist_ok=True)
                    
                    with open(target_filepath, 'a') as f:
                        # Very simplistic, just append the test function
                        # A real implementation would need to handle imports and class structures
                        f.write('\n' + test_content)
            
            # For now, just print that we've processed the file
            print(f"Processed {filename}")
            # os.remove(filepath) # We'll delete the file later

if __name__ == '__main__':
    refactor_tests()
