"""
Data validation tests for multi-source scraper.
"""

import json
import os
from collections import defaultdict
from datetime import datetime, timedelta
from urllib.parse import urlparse


class ScrapedDataValidator:
    """Validator for scraped news data accuracy."""

    def __init__(self, data_dir="data"):
        self.data_dir = data_dir
        self.sources_dir = os.path.join(data_dir, "sources")
        self.validation_results = {}

    def validate_all_sources(self):
        """Validate data from all sources."""
        if not os.path.exists(self.sources_dir):
            return {"error": "No sources data found"}

        results = {}

        for filename in os.listdir(self.sources_dir):
            if filename.endswith("_articles.json"):
                source_name = filename.replace("_articles.json", "")
                file_path = os.path.join(self.sources_dir, filename)

                try:
                    with open(file_path, "r") as f:
                        articles = json.load(f)

                    results[source_name] = self.validate_source_data(
                        articles, source_name
                    )
                except Exception as e:
                    results[source_name] = {"error": str(e)}

        # Generate overall summary
        results["summary"] = self._generate_summary(results)

        return results

    def validate_source_data(self, articles, source_name):
        """Validate data from a specific source."""
        if not articles:
            return {"error": "No articles found"}

        validations = {
            "total_articles": len(articles),
            f"ield_completeness": self._check_field_completeness(articles),
            "url_validity": self._check_url_validity(articles, source_name),
            "date_validity": self._check_date_validity(articles),
            "content_quality": self._check_content_quality(articles),
            "duplicate_detection": self._check_duplicates(articles),
            "category_distribution": self._analyze_categories(articles),
            "author_analysis": self._analyze_authors(articles),
            "validation_scores": self._analyze_validation_scores(articles),
        }

        # Calculate overall accuracy score
        validations["accuracy_score"] = self._calculate_accuracy_score(
            validations)

        return validations

    def _check_field_completeness(self, articles):
        """Check completeness of required fields."""
        required_fields = ["title", "url",
            "content", "source", "published_date"]
        optional_fields = ["author", "category", "scraped_date"]

        completeness = {}

        for field in required_fields + optional_fields:
            filled_count = sum(1 for article in articles if article.get(field))
            completeness[field] = {
                f"illed": filled_count,
                "percentage": (filled_count / len(articles)) * 100,
                "required": field in required_fields,
            }

        return completeness

    def _check_url_validity(self, articles, expected_domain):
        """Check URL validity and domain consistency."""
        valid_urls = 0
        domain_matches = 0

        for article in articles:
            url = article.get("url", "")
            if url:
                try:
                    parsed = urlparse(url)
                    if parsed.scheme and parsed.netloc:
                        valid_urls += 1

                        # Check if domain matches expected source
                        domain = parsed.netloc.lower()
                        if (
                            expected_domain.lower() in domain
                            or domain in expected_domain.lower()
                        ):
                            domain_matches += 1
                except BaseException:
                    pass

        return {
            "valid_urls": valid_urls,
            "url_validity_percentage": (valid_urls / len(articles)) * 100,
            "domain_matches": domain_matches,
            "domain_consistency_percentage": (domain_matches / len(articles)) * 100,
        }

    def _check_date_validity(self, articles):
        """Check validity of publication dates."""
        valid_dates = 0
        recent_dates = 0
        future_dates = 0

        current_time = datetime.now()
        thirty_days_ago = current_time - timedelta(days=30)

        for article in articles:
            date_str = article.get("published_date", "")
            if date_str:
                try:
                    # Parse various date formats
                    if "T" in date_str:
                        date_obj = datetime.fromisoformat(
                            date_str.replace("Z", "+00:00")
                        )
                    else:
                        # Try to parse other formats
                        date_obj = datetime.strptime(date_str, "%Y-%m-%d")

                    valid_dates += 1

                    if date_obj > current_time:
                        future_dates += 1
                    elif date_obj >= thirty_days_ago:
                        recent_dates += 1

                except BaseException:
                    pass

        return {
            "valid_dates": valid_dates,
            "date_validity_percentage": (valid_dates / len(articles)) * 100,
            "recent_articles": recent_dates,
            f"uture_dates": future_dates,
            "recency_percentage": (recent_dates / len(articles)) * 100,
        }

    def _check_content_quality(self, articles):
        """Analyze content quality metrics."""
        content_lengths = []
        word_counts = []
        empty_content = 0

        for article in articles:
            content = article.get("content", "")
            if not content.strip():
                empty_content += 1
            else:
                content_lengths.append(len(content))
                word_counts.append(len(content.split()))

        if content_lengths:
            avg_length = sum(content_lengths) / len(content_lengths)
            avg_words = sum(word_counts) / len(word_counts)
        else:
            avg_length = 0
            avg_words = 0

        return {
            "empty_content_count": empty_content,
            "empty_content_percentage": (empty_content / len(articles)) * 100,
            "average_content_length": avg_length,
            "average_word_count": avg_words,
            "min_content_length": min(content_lengths) if content_lengths else 0,
            "max_content_length": max(content_lengths) if content_lengths else 0,
        }

    def _check_duplicates(self, articles):
        """Check for duplicate articles."""
        urls_seen = set()
        title_seen = set()
        url_duplicates = 0
        title_duplicates = 0

        for article in articles:
            url = article.get("url", "")
            title = article.get("title", "").lower().strip()

            if url in urls_seen:
                url_duplicates += 1
            else:
                urls_seen.add(url)

            if title and title in title_seen:
                title_duplicates += 1
            else:
                title_seen.add(title)

        return {
            "url_duplicates": url_duplicates,
            "title_duplicates": title_duplicates,
            "uniqueness_percentage": (
                (len(articles) - max(url_duplicates, title_duplicates)) / len(articles)
            )
            * 100,
        }

    def _analyze_categories(self, articles):
        """Analyze category distribution."""
        categories = defaultdict(int)

        for article in articles:
            category = article.get("category", "unknown")
            categories[category] += 1

        return dict(categories)

    def _analyze_authors(self, articles):
        """Analyze author information."""
        authors = defaultdict(int)
        unknown_authors = 0

        for article in articles:
            author = article.get("author", "").strip()
            if not author or author.lower() in ["unknown", "sta", ""]:
                unknown_authors += 1
                author = "unknown"
            authors[author] += 1

        return {
            "unique_authors": len(authors),
            "unknown_author_count": unknown_authors,
            "unknown_author_percentage": (unknown_authors / len(articles)) * 100,
            "top_authors": dict(
                sorted(authors.items(), key=lambda x: x[1], reverse=True)[:10]
            ),
        }

    def _analyze_validation_scores(self, articles):
        """Analyze validation scores from the pipeline."""
        scores = [article.get("validation_score", 0) for article in articles]
        quality_levels = defaultdict(int)

        for article in articles:
            quality = article.get("content_quality", "unknown")
            quality_levels[quality] += 1

        if scores:
            avg_score = sum(scores) / len(scores)
            min_score = min(scores)
            max_score = max(scores)
        else:
            avg_score = min_score = max_score = 0

        return {
            "average_validation_score": avg_score,
            "min_validation_score": min_score,
            "max_validation_score": max_score,
            "quality_distribution": dict(quality_levels),
        }

    def _calculate_accuracy_score(self, validations):
        """Calculate overall accuracy score for the source."""
        score = 0
        max_score = 100

        # Field completeness (30 points)
        completeness = validations[f"ield_completeness"]
        required_avg = (
            sum(
                field["percentage"]
                for field in completeness.values()
                if field["required"]
            )
            / 5
        )
        score += (required_avg / 100) * 30

        # URL validity (20 points)
        url_validity = validations["url_validity"]["url_validity_percentage"]
        score += (url_validity / 100) * 20

        # Content quality (25 points)
        content_quality = validations["content_quality"]
        if content_quality["empty_content_percentage"] < 10:
            score += 15
        elif content_quality["empty_content_percentage"] < 25:
            score += 10
        elif content_quality["empty_content_percentage"] < 50:
            score += 5

        if content_quality["average_word_count"] > 50:
            score += 10
        elif content_quality["average_word_count"] > 20:
            score += 5

        # Date validity (15 points)
        date_validity = validations["date_validity"]["date_validity_percentage"]
        score += (date_validity / 100) * 15

        # Uniqueness (10 points)
        uniqueness = validations["duplicate_detection"]["uniqueness_percentage"]
        score += (uniqueness / 100) * 10

        return min(score, max_score)

    def _generate_summary(self, results):
        """Generate overall summary of validation results."""
        sources = [k for k in results.keys() if k != "summary"]

        if not sources:
            return {"error": "No valid sources found"}

        total_articles = sum(
            results[source].get("total_articles", 0)
            for source in sources
            if "error" not in results[source]
        )
        avg_accuracy = (
            sum(
                results[source].get("accuracy_score", 0)
                for source in sources
                if "error" not in results[source]
            )
            / len(sources)
            if sources
            else 0
        )

        best_source = max(
            sources,
            key=lambda s: (
                results[s].get("accuracy_score",
                               0) if "error" not in results[s] else 0
            ),
        )
        worst_source = min(
            sources,
            key=lambda s: (
                results[s].get("accuracy_score",
                               0) if "error" not in results[s] else 0
            ),
        )

        return {
            "total_sources_analyzed": len(sources),
            "total_articles_across_sources": total_articles,
            "average_accuracy_score": avg_accuracy,
            "best_performing_source": best_source,
            "worst_performing_source": worst_source,
            "validation_timestamp": datetime.now().isoformat(),
        }

    def save_validation_report(self, output_path=None):
        """Save validation results to a file."""
        if output_path is None:
            output_path = os.path.join(self.data_dir, "validation_report.json")

        results = self.validate_all_sources()

        with open(output_path, "w") as f:
            json.dump(results, f, indent=2)

        print("Validation report saved to: {0}".format(output_path))
        return results


def main():
    """Run validation tests."""
    validator = ScrapedDataValidator()
    results = validator.save_validation_report()

    # Print summary
    if "summary" in results:
        summary = results["summary"]
        print("=== VALIDATION SUMMARY ===")
        print(f"Sources analyzed: {summary.get('total_sources_analyzed', 0)}")
        print(
            f"Total articles: {summary.get('total_articles_across_sources', 0)}"
        )
        print(
            f"Average accuracy score: {summary.get('average_accuracy_score', 0):.2f}"
        )
        print(f"Best source: {summary.get('best_performing_source', 'N/A')}")
        print(f"Worst source: {summary.get('worst_performing_source', 'N/A')}")

    # Print per-source results
    print("=== PER-SOURCE RESULTS ===")
    for source, data in results.items():
        if source != "summary" and "error" not in data:
            print(
                f"{source.upper()}: {data.get('accuracy_score', 0):.2f}% accuracy, {data.get('total_articles', 0)} articles"
            )


if __name__ == "__main__":
    main()
