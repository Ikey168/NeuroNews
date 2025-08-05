#!/usr/bin/env python3
"""
Verification script to ensure all BDU Milestone 3 issue requirements are met.
"""

import json
import sys

def verify_issues():
    """Verify all issue requirements are satisfied."""
    
    # Load the generated issues
    try:
        with open('bdu_milestone3_issues.json', 'r') as f:
            issues = json.load(f)
    except FileNotFoundError:
        print("❌ ERROR: bdu_milestone3_issues.json not found!")
        print("Run: python3 scripts/create_bdu_milestone3_issues.py --json")
        return False
    
    print("🔍 VERIFYING BDU MILESTONE 3 ISSUES")
    print("=" * 50)
    
    # Expected issues and their labels
    expected_issues = [
        ("Define D1 schema & write migrations", ["infra", "cloudflare-workers", "d1"]),
        ("Implement `GET /api/users` & `POST /api/users`", ["backend", "api", "cloudflare-workers"]),
        ("Implement `GET /api/events` & `POST /api/events`", ["backend", "api", "cloudflare-workers"]),
        ("Implement `POST /api/registrations` & `GET /api/registrations`", ["backend", "api", "cloudflare-workers"]),
        ("Add authentication via Pages Members", ["backend", "auth", "cloudflare-workers"]),
        ("Input validation middleware", ["backend", "validation", "cloudflare-workers"]),
        ("Error-handling & logging", ["backend", "observability", "cloudflare-workers"]),
        ("Unit tests for each endpoint", ["test", "unit-tests", "cloudflare-workers"]),
        ("Integration tests with real D1", ["test", "integration-tests", "ci"]),
        ("Update API documentation", ["documentation", "api"])
    ]
    
    # Verify count
    if len(issues) != 10:
        print(f"❌ Expected 10 issues, found {len(issues)}")
        return False
    print(f"✅ Correct number of issues: {len(issues)}")
    
    # Verify each issue
    all_passed = True
    for i, (expected_title, expected_labels) in enumerate(expected_issues):
        issue = issues[i]
        
        print(f"\n📋 Issue {i+1}/10: {issue['title']}")
        
        # Check title
        if issue['title'] != expected_title:
            print(f"❌ Title mismatch. Expected: {expected_title}")
            all_passed = False
        else:
            print("✅ Title correct")
        
        # Check labels
        if set(issue['labels']) != set(expected_labels):
            print(f"❌ Labels mismatch. Expected: {expected_labels}, Got: {issue['labels']}")
            all_passed = False
        else:
            print(f"✅ Labels correct: {', '.join(issue['labels'])}")
        
        # Check milestone
        if issue['milestone'] != "3":
            print(f"❌ Milestone should be '3', got '{issue['milestone']}'")
            all_passed = False
        else:
            print("✅ Milestone correct: 3")
        
        # Check for checkboxes in body
        if "- [ ]" not in issue['body']:
            print("❌ No checkboxes found in issue body")
            all_passed = False
        else:
            checkbox_count = issue['body'].count("- [ ]")
            print(f"✅ Contains {checkbox_count} checkboxes")
        
        # Check for description and acceptance criteria
        if "## Description" not in issue['body'] or "## Acceptance Criteria" not in issue['body']:
            print("❌ Missing Description or Acceptance Criteria section")
            all_passed = False
        else:
            print("✅ Contains Description and Acceptance Criteria")
    
    print("\n" + "=" * 50)
    if all_passed:
        print("🎉 ALL REQUIREMENTS SATISFIED!")
        print("✅ 10 issues created with correct titles")
        print("✅ All issues have appropriate labels")
        print("✅ All issues assigned to milestone 3")
        print("✅ All issues contain checkboxes for tasks")
        print("✅ All issues have proper structure (Description + Acceptance Criteria)")
        print("\n🚀 Ready to create issues in Ikey168/BDU repository!")
    else:
        print("❌ SOME REQUIREMENTS NOT MET!")
        print("Please fix the issues above and try again.")
    
    return all_passed

def show_summary():
    """Show a summary of what will be created."""
    try:
        with open('bdu_milestone3_issues.json', 'r') as f:
            issues = json.load(f)
    except FileNotFoundError:
        print("❌ bdu_milestone3_issues.json not found!")
        return
    
    print("\n📊 SUMMARY OF ISSUES TO BE CREATED")
    print("=" * 50)
    
    # Group by label type
    label_groups = {}
    for issue in issues:
        for label in issue['labels']:
            if label not in label_groups:
                label_groups[label] = []
            label_groups[label].append(issue['title'])
    
    print(f"Total Issues: {len(issues)}")
    print(f"Milestone: 3")
    print("\nIssues by Label:")
    for label, titles in sorted(label_groups.items()):
        print(f"  {label} ({len(titles)} issues):")
        for title in titles:
            print(f"    - {title}")
    
    print(f"\nAll labels used: {', '.join(sorted(label_groups.keys()))}")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--summary":
        show_summary()
    else:
        verify_issues()