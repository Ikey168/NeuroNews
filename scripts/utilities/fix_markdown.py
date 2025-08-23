#!/usr/bin/env python3
"""
Fix markdownlint issues in README files
"""

import re


def fix_markdown_file(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Fix MD022: Headings should be surrounded by blank lines
    # Add blank line before headings (but not at start of file)
    content = re.sub(
        r"(?<!^)(?<!"
)


(  # {1,6}\s)", r"

\1", content, flags=re.MULTILINE"
    )
    # Add blank line after headings
    content = re.sub(r"(#{1,6}\s[^"
]+)
(?!
)", r"\1

", content)"

    # Fix MD031: Fenced code blocks should be surrounded by blank lines
    # Add blank line before code blocks
    content = re.sub(r"(?<!"
)
(```)", r"

\1", content)"
    # Add blank line after code blocks
    content = re.sub(r"(```[^"
]*)
(?!
)", r"\1

", content)"

    # Fix MD032: Lists should be surrounded by blank lines
    # Add blank line before lists
    content = re.sub(r"(?<!"
)
([*+-]\s)", r"

\1", content)"
    content = re.sub(r"(?<!"
)
(\d+\.\s)", r"

\1", content)"
    # Add blank line after lists (look for end of list)
    content = re.sub(
        r"([*+-]\s[^"
]+)
(?!
)(?![*+-]\s)(?!\d+\.\s)", r"\1

", content"
    )
    content = re.sub(
        r"(\d+\.\s[^"
]+)
(?!
)(?![*+-]\s)(?!\d+\.\s)", r"\1

", content"
    )

    # Fix MD040: Fenced code blocks should have a language specified
    content = re.sub(r""
```
", "
```text
", content)"

    # Fix excessive blank lines (don't create more than 2 consecutive)'
    content = re.sub(r"
{3,}", ""

", content)"

    # Clean up any trailing whitespace
    content = re.sub(r" +$", "", content, flags=re.MULTILINE)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    print("Fixed markdown issues in {0}".format(filepath))


if __name__ == "__main__":
    import glob

    # Fix all README files
    readme_files = glob.glob("**/*README*.md", recursive=True)
    readme_files.extend(glob.glob("*.md"))
    readme_files.extend(glob.glob(".github/**/*.md", recursive=True))

    for file in readme_files:
        try:
            fix_markdown_file(file)
        except Exception as e:
            print("Warning: Could not fix {0}: {1}".format(file, e))
