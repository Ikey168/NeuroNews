#!/usr/bin/env python3
"""Fix multi-line f-string expressions that are invalid on Python < 3.12.

Joins lines where an f-string opens an expression with `{` at end of line,
e.g.:
    f"Error processing article {
        e}"
becomes:
    f"Error processing article {e}"
"""
import re
import sys


def try_compile(source, filename):
    try:
        compile(source, filename, "exec")
        return None
    except SyntaxError as e:
        return e


def fix_file(path, max_iters=500):
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    changed = False
    for _ in range(max_iters):
        err = try_compile("".join(lines), path)
        if err is None:
            break
        lineno = err.lineno
        if lineno is None or lineno > len(lines):
            return False, err
        line = lines[lineno - 1]
        # Pattern: line ends with `{` (an opened f-string expression)
        if re.search(r"\{\s*$", line) and not re.search(r"\{\{\s*$", line):
            nxt = lines[lineno] if lineno < len(lines) else ""
            lines[lineno - 1] = line.rstrip("\n").rstrip() + nxt.lstrip()
            del lines[lineno]
            changed = True
            continue
        # Pattern: error points at a continuation line; check previous line
        prev = lines[lineno - 2] if lineno >= 2 else ""
        if re.search(r"\{\s*$", prev) and not re.search(r"\{\{\s*$", prev):
            lines[lineno - 2] = prev.rstrip("\n").rstrip() + line.lstrip()
            del lines[lineno - 1]
            changed = True
            continue
        # Fallback: an f-string opened an expression whose continuation spans
        # multiple lines (e.g. a call with arguments on their own lines).
        # Join the next line onto the reported line and re-try compilation.
        if (
            "unterminated string literal" in err.msg
            and re.search(r"""f["']""", line)
            and lineno < len(lines)
        ):
            nxt = lines[lineno]
            joined = line.rstrip("\n").rstrip() + nxt.lstrip()
            lines[lineno - 1] = joined
            del lines[lineno]
            changed = True
            continue
        return False, err

    err = try_compile("".join(lines), path)
    if err is not None:
        return False, err
    if changed:
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines)
    return True, None


def main():
    ok, failed = [], []
    for path in sys.argv[1:]:
        success, err = fix_file(path)
        if success:
            ok.append(path)
        else:
            failed.append((path, err))
    print(f"Fixed: {len(ok)}")
    for path, err in failed:
        print(f"MANUAL: {path}: line {err.lineno}: {err.msg}")


if __name__ == "__main__":
    main()
