"""
Demo: Chunking & Normalization Pipeline
Issue #229: Chunking & normalization pipeline

This demo shows the complete pipeline for normalizing articles and chunking them
into appropriately sized pieces with metadata preservation.
"""

import logging
import yaml
from pathlib import Path
from services.rag.normalization import ArticleNormalizer
from services.rag.chunking import TextChunker, ChunkConfig, SplitStrategy

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_chunking_config(content_type: str = "default") -> ChunkConfig:
    """Load chunking configuration from YAML file."""
    config_path = Path("configs/chunking.yaml")
    
    if not config_path.exists():
        logger.warning(f"Config file not found: {config_path}, using defaults")
        return ChunkConfig()
    
    with open(config_path, 'r') as f:
        config_data = yaml.safe_load(f)
    
    # Get configuration for content type
    if content_type in config_data.get('content_types', {}):
        config = config_data['content_types'][content_type]
    else:
        config = config_data.get('default', {})
    
    return ChunkConfig(
        max_chars=config.get('max_chars', 1000),
        overlap_chars=config.get('overlap_chars', 100),
        split_on=SplitStrategy(config.get('split_on', 'sentence')),
        min_chunk_chars=config.get('min_chunk_chars', 50),
        preserve_sentences=config.get('preserve_sentences', True),
        language=config.get('language', 'en'),
    )


def demo_html_article():
    """Demo with HTML article content."""
    print("\n" + "="*60)
    print("DEMO: HTML Article Processing")
    print("="*60)
    
    html_content = """
    <html>
    <head>
        <title>AI Breakthrough in Medical Diagnosis</title>
        <meta name="author" content="Dr. Sarah Johnson">
        <meta name="published" content="2024-08-26T09:00:00">
        <link rel="canonical" href="https://neuronews.com/ai-medical-breakthrough">
    </head>
    <body>
        <article>
            <h1>Artificial Intelligence Revolutionizes Medical Diagnosis</h1>
            <p class="byline">By Dr. Sarah Johnson, Medical Technology Correspondent</p>
            <time datetime="2024-08-26T09:00:00">August 26, 2024</time>
            
            <p>A groundbreaking study published today in the Journal of Medical AI demonstrates 
            that machine learning algorithms can now diagnose certain medical conditions with 
            greater accuracy than human doctors. The research, conducted over three years at 
            leading medical institutions, represents a significant milestone in the integration 
            of artificial intelligence into healthcare.</p>
            
            <p>The AI system, trained on over 100,000 medical images and patient records, 
            achieved a diagnostic accuracy rate of 94.2% compared to the 87.8% average 
            accuracy of experienced physicians. The system showed particular strength in 
            identifying early-stage conditions that are often missed in routine examinations.</p>
            
            <p>"This technology has the potential to save countless lives by catching diseases 
            earlier and more accurately," said Dr. Michael Chen, lead researcher on the project. 
            "However, we want to emphasize that this is meant to assist doctors, not replace them. 
            The human element in medicine remains irreplaceable."</p>
            
            <p>The research team is now working on expanding the system to cover additional 
            medical specialties and has announced plans for clinical trials at major hospitals 
            beginning next year. Regulatory approval processes are already underway in several 
            countries.</p>
            
            <p>Industry experts predict that this advancement could lead to significant cost 
            savings in healthcare systems worldwide while improving patient outcomes. The 
            technology is expected to be particularly valuable in underserved areas where 
            access to specialist physicians is limited.</p>
        </article>
    </body>
    </html>
    """
    
    # Step 1: Normalize the article
    normalizer = ArticleNormalizer()
    normalized = normalizer.normalize_article(html_content)
    
    print("STEP 1: Article Normalization")
    print("-" * 30)
    print(f"Title: {normalized['title']}")
    print(f"Author: {normalized['byline']}")
    print(f"Published: {normalized['timestamp']}")
    print(f"URL: {normalized['url']}")
    print(f"Language: {normalized['language']}")
    print(f"Word Count: {normalized['word_count']}")
    print(f"Character Count: {normalized['char_count']}")
    print(f"\nContent Preview:\n{normalized['content'][:200]}...")
    
    # Step 2: Chunk the normalized content
    config = load_chunking_config("news_long")
    chunker = TextChunker(config)
    chunks = chunker.chunk_text(normalized['content'], {
        'title': normalized['title'],
        'author': normalized['byline'],
        'source_url': normalized['url'],
        'published_date': str(normalized['timestamp']) if normalized['timestamp'] else None,
    })
    
    print(f"\nSTEP 2: Text Chunking")
    print("-" * 30)
    print(f"Configuration: max_chars={config.max_chars}, overlap={config.overlap_chars}, strategy={config.split_on.value}")
    print(f"Generated {len(chunks)} chunks:")
    
    for i, chunk in enumerate(chunks):
        print(f"\nChunk {chunk.chunk_id + 1}:")
        print(f"  Words: {chunk.word_count}, Characters: {chunk.char_count}")
        print(f"  Offset: {chunk.start_offset}-{chunk.end_offset}")
        print(f"  Text: {chunk.text[:100]}..." if len(chunk.text) > 100 else f"  Text: {chunk.text}")
    
    return normalized, chunks


def demo_plain_text_article():
    """Demo with plain text article."""
    print("\n" + "="*60)
    print("DEMO: Plain Text Article Processing")
    print("="*60)
    
    text_content = """
    Climate Summit Reaches Historic Agreement
    
    World leaders gathered in Geneva this week reached a landmark agreement on climate action 
    that goes beyond previous commitments. The agreement, signed by representatives from 195 
    countries, includes specific targets for carbon reduction and substantial funding commitments 
    for developing nations.
    
    The three-day summit was marked by intense negotiations. Key provisions include a commitment 
    to reduce global carbon emissions by 45% by 2030 and achieve net-zero emissions by 2050. 
    Additionally, developed countries pledged $200 billion annually to support climate adaptation 
    and mitigation efforts in developing nations.
    
    Environmental groups have cautiously welcomed the agreement while emphasizing the importance 
    of implementation. "This is a significant step forward, but the real test will be whether 
    countries follow through on their commitments," said Maria Gonzalez, director of the Global 
    Climate Alliance.
    
    The business community has also responded positively, with many corporations announcing 
    accelerated sustainability initiatives. Stock markets worldwide showed strong performance 
    in green energy sectors following the announcement.
    
    Critics argue that the targets may still be insufficient to prevent the most catastrophic 
    effects of climate change. However, most experts agree that this represents the most 
    comprehensive global climate action plan to date.
    """
    
    # Step 1: Normalize
    normalizer = ArticleNormalizer()
    normalized = normalizer.normalize_article(text_content)
    
    print("STEP 1: Article Normalization")
    print("-" * 30)
    print(f"Extracted Title: {normalized['title']}")
    print(f"Word Count: {normalized['word_count']}")
    print(f"Character Count: {normalized['char_count']}")
    print(f"Language: {normalized['language']}")
    
    # Step 2: Chunk with different strategy
    config = load_chunking_config("news_short")
    chunker = TextChunker(config)
    chunks = chunker.chunk_text(normalized['content'], {
        'content_type': 'climate_news',
        'processing_date': '2024-08-26',
    })
    
    print(f"\nSTEP 2: Text Chunking")
    print("-" * 30)
    print(f"Configuration: max_chars={config.max_chars}, overlap={config.overlap_chars}, strategy={config.split_on.value}")
    print(f"Generated {len(chunks)} chunks:")
    
    for chunk in chunks:
        print(f"\nChunk {chunk.chunk_id + 1}: {chunk.word_count} words")
        print(f"  Preview: {chunk.text[:80]}...")
    
    return normalized, chunks


def demo_edge_cases():
    """Demo with edge cases."""
    print("\n" + "="*60)
    print("DEMO: Edge Cases")
    print("="*60)
    
    edge_cases = [
        ("Very short text", "Short."),
        ("Very long word", "This text contains a supercalifragilisticexpialidocious" + "extraordinary" * 10 + " word."),
        ("Mixed languages", "English text. Texto en español. 中文文本. النص العربي."),
        ("Code block", """
        Here's some code:
        
        def process_data(data):
            # Process the data
            for item in data:
                if item.is_valid():
                    yield transform(item)
        
        This function processes data efficiently.
        """),
        ("Special characters", "Text with émojis 🎉, symbols ©®™, and áccénts!"),
    ]
    
    normalizer = ArticleNormalizer()
    config = ChunkConfig(max_chars=200, overlap_chars=20, split_on=SplitStrategy.SENTENCE)
    chunker = TextChunker(config)
    
    for case_name, content in edge_cases:
        print(f"\n{case_name}:")
        print("-" * len(case_name))
        
        try:
            normalized = normalizer.normalize_article(content)
            chunks = chunker.chunk_text(normalized['content'])
            
            print(f"  Normalized: {normalized['word_count']} words, {normalized['char_count']} chars")
            print(f"  Chunks: {len(chunks)}")
            
            if chunks:
                print(f"  First chunk: {chunks[0].text[:50]}...")
        
        except Exception as e:
            print(f"  Error: {e}")


def demo_configuration_comparison():
    """Demo showing different chunking configurations."""
    print("\n" + "="*60)
    print("DEMO: Configuration Comparison")
    print("="*60)
    
    sample_text = """
    Artificial intelligence is transforming industries across the globe. From healthcare 
    to finance, companies are leveraging machine learning algorithms to improve efficiency 
    and decision-making. The technology has shown remarkable progress in recent years.
    
    Natural language processing, a subset of AI, enables computers to understand and 
    generate human language. This capability is being used in chatbots, translation 
    services, and content analysis tools. The applications are virtually limitless.
    
    However, the rapid advancement of AI also raises important ethical questions. Issues 
    such as bias in algorithms, job displacement, and privacy concerns need to be addressed 
    as the technology becomes more prevalent in society.
    """
    
    normalizer = ArticleNormalizer()
    normalized = normalizer.normalize_article(sample_text)
    
    configurations = [
        ("Small chunks", ChunkConfig(max_chars=200, overlap_chars=20, split_on=SplitStrategy.SENTENCE)),
        ("Medium chunks", ChunkConfig(max_chars=400, overlap_chars=40, split_on=SplitStrategy.SENTENCE)),
        ("Large chunks", ChunkConfig(max_chars=600, overlap_chars=60, split_on=SplitStrategy.PARAGRAPH)),
        ("Word-based", ChunkConfig(max_chars=300, overlap_chars=30, split_on=SplitStrategy.WORD)),
    ]
    
    for config_name, config in configurations:
        chunker = TextChunker(config)
        chunks = chunker.chunk_text(normalized['content'])
        
        print(f"\n{config_name} ({config.split_on.value}):")
        print(f"  Max chars: {config.max_chars}, Overlap: {config.overlap_chars}")
        print(f"  Generated: {len(chunks)} chunks")
        
        for i, chunk in enumerate(chunks):
            print(f"    Chunk {i+1}: {chunk.word_count} words, {chunk.char_count} chars")


def main():
    """Run all demos."""
    print("CHUNKING & NORMALIZATION PIPELINE DEMO")
    print("Issue #229: Chunking & normalization pipeline")
    print("="*60)
    
    try:
        # Demo 1: HTML Article
        html_normalized, html_chunks = demo_html_article()
        
        # Demo 2: Plain Text Article  
        text_normalized, text_chunks = demo_plain_text_article()
        
        # Demo 3: Edge Cases
        demo_edge_cases()
        
        # Demo 4: Configuration Comparison
        demo_configuration_comparison()
        
        print("\n" + "="*60)
        print("DEMO COMPLETE")
        print("="*60)
        print("Key Features Demonstrated:")
        print("✅ HTML → clean text normalization")
        print("✅ Metadata extraction (title, byline, timestamp, URL, language)")
        print("✅ Language-aware chunking with configurable size/overlap")
        print("✅ Multiple splitting strategies (sentence, paragraph, word, character)")
        print("✅ Edge case handling (long words, code blocks, special characters)")
        print("✅ Chunk metadata with offsets for reconstruction")
        print("✅ Configurable parameters via YAML")
        
        # Summary statistics
        total_chunks = len(html_chunks) + len(text_chunks)
        print(f"\nProcessed 2 articles into {total_chunks} chunks total")
        print(f"All chunks include metadata with offsets + clean text ✅")
        
    except Exception as e:
        logger.error(f"Demo failed: {e}")
        raise


if __name__ == "__main__":
    main()
