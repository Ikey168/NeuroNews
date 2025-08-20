#!/usr/bin/env python3
"""
Fix remaining syntax issues in specific files.
"""

import re

fixes = [
    # File: src/nlp/kubernetes/ai_processor.py
    ("src/nlp/kubernetes/ai_processor.py", [
        (r"top_words\[1\]\]\),", "top_words[1]],")
    ]),
    
    # File: src/nlp/language_processor.py  
    ("src/nlp/language_processor.py", [
        (r"hash\(text\[:100\]\)\)\)", "hash(text[:100]))")
    ]),
    
    # File: src/nlp/multi_language_processor.py
    ("src/nlp/multi_language_processor.py", [
        (r"content_hash\[:100\]\]\)", "content_hash[:100])")
    ]),
    
    # File: src/nlp/summary_database.py
    ("src/nlp/summary_database.py", [
        (r"str\(e\)\)", "str(e))")
    ]),
    
    # File: src/nlp/optimized_nlp_pipeline.py
    ("src/nlp/optimized_nlp_pipeline.py", [
        (r"results\['articles_processed'\]\]\)", "results['articles_processed'])")
    ]),
    
    # File: src/scraper/async_scraper_runner.py
    ("src/scraper/async_scraper_runner.py", [
        (r"for s in sources\]\]\)", "for s in sources])")
    ]),
    
    # File: src/scraper/async_scraper_engine.py
    ("src/scraper/async_scraper_engine.py", [
        (r"sources\[i\]\.name, result\)\)", "sources[i].name, result)")
    ]),
    
    # File: src/scraper/enhanced_retry_manager.py
    ("src/scraper/enhanced_retry_manager.py", [
        (r"\.format\(delay\)", ".format(delay:.2f, retry_reason.value)")
    ]),
    
    # File: src/scraper/extensions/cloudwatch_logging.py
    ("src/scraper/extensions/cloudwatch_logging.py", [
        (r"handler\.log_stream_name\)", "handler.log_stream_name)")
    ]),
    
    # File: src/scraper/sns_alert_manager.py
    ("src/scraper/sns_alert_manager.py", [
        (r"\]\)", "]")
    ]),
    
    # File: src/scraper/user_agent_rotator.py  
    ("src/scraper/user_agent_rotator.py", [
        (r'"\{0\} on \{1\}"\.format\(', '"{0} on {1}".format(self.platform, self.browser)')
    ])
]

for file_path, file_fixes in fixes:
    try:
        with open(file_path, 'r') as f:
            content = f.read()
        
        original_content = content
        
        for pattern, replacement in file_fixes:
            content = re.sub(pattern, replacement, content)
        
        if content != original_content:
            with open(file_path, 'w') as f:
                f.write(content)
            print(f"Fixed: {file_path}")
            
    except Exception as e:
        print(f"Error processing {file_path}: {e}")

print("Completed syntax fixes!")
