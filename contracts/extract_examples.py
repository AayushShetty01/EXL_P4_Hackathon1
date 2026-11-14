"""Extract the contract example files from docs/PROJECT_CONTEXT.md into contracts/examples/.

Usage, from the repository root: python contracts/extract_examples.py [--check]
With --check nothing is written; the exit code is 1 when the files on disk differ from the document.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
CONTEXT_PATH = REPOSITORY_ROOT / "docs" / "PROJECT_CONTEXT.md"
EXAMPLES_DIR = REPOSITORY_ROOT / "contracts" / "examples"
EXAMPLE_LINE = re.compile(r"^Example file: `contracts/examples/([^`/]+\.json)`")
INCLUDE_KEY = "$include"


class ExtractionError(Exception):
    """Raised when the project context cannot be turned into valid example files."""


def find_opening_fence(lines: list[str], example_line: int) -> int:
    """Return the index of the ```json line that belongs to the example declared at example_line."""
    for index in range(example_line + 1, len(lines)):
        line = lines[index].strip()
        if line == "```json":
            return index
        if EXAMPLE_LINE.match(lines[index]) or line.startswith("#"):
            break
    raise ExtractionError(
        f"line {example_line + 1}: no ```json block follows the example declaration"
    )


def find_closing_fence(lines: list[str], opening_fence: int) -> int:
    """Return the index of the ``` line that closes the block opened at opening_fence."""
    for index in range(opening_fence + 1, len(lines)):
        if lines[index].strip() == "```":
            return index
    raise ExtractionError(f"line {opening_fence + 1}: the ```json block is never closed")


def parse_examples(text: str) -> dict[str, Any]:
    """Return {file name: parsed JSON} for every example declaration in the project context."""
    lines = text.splitlines()
    examples: dict[str, Any] = {}
    index = 0
    while index < len(lines):
        match = EXAMPLE_LINE.match(lines[index])
        if not match:
            index += 1
            continue
        name = match.group(1)
        if name in examples:
            raise ExtractionError(f"line {index + 1}: {name} is declared twice")
        opening = find_opening_fence(lines, index)
        closing = find_closing_fence(lines, opening)
        block = "\n".join(lines[opening + 1 : closing])
        try:
            examples[name] = json.loads(block)
        except json.JSONDecodeError as error:
            raise ExtractionError(
                f"{name}: invalid JSON at line {opening + 1 + error.lineno}, "
                f"column {error.colno} of the project context: {error.msg}"
            ) from error
        index = closing + 1
    if not examples:
        raise ExtractionError("no 'Example file:' declarations found")
    return examples


def resolve_includes(value: Any, examples: dict[str, Any], chain: tuple[str, ...]) -> Any:
    """Replace every {"$include": "file.json"} object with the resolved content of that example."""
    if isinstance(value, dict):
        if INCLUDE_KEY in value:
            if len(value) != 1:
                raise ExtractionError(f"{chain[0]}: an include object must have no other keys")
            target = value[INCLUDE_KEY]
            if target not in examples:
                raise ExtractionError(f"{chain[-1]}: includes {target}, which is not an example file")
            if target in chain:
                raise ExtractionError(f"include cycle: {' -> '.join(chain + (target,))}")
            return resolve_includes(examples[target], examples, chain + (target,))
        return {key: resolve_includes(item, examples, chain) for key, item in value.items()}
    if isinstance(value, list):
        return [resolve_includes(item, examples, chain) for item in value]
    return value


def render(value: Any) -> str:
    """Format one example as indented JSON with a trailing newline."""
    return json.dumps(value, indent=2, ensure_ascii=False) + "\n"


def unexpected_files(expected: dict[str, str]) -> list[str]:
    """List JSON files in contracts/examples/ that the project context does not declare."""
    if not EXAMPLES_DIR.is_dir():
        return []
    return sorted(path.name for path in EXAMPLES_DIR.glob("*.json") if path.name not in expected)


def write_files(expected: dict[str, str]) -> int:
    """Write every example file and warn about files the document no longer declares."""
    EXAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    for name, content in expected.items():
        (EXAMPLES_DIR / name).write_text(content, encoding="utf-8")
        print(f"wrote contracts/examples/{name}")
    for name in unexpected_files(expected):
        print(f"WARNING: contracts/examples/{name} is not declared in the project context", file=sys.stderr)
    print(f"{len(expected)} example files written")
    return 0


def check_files(expected: dict[str, str]) -> int:
    """Compare the files on disk with the document and report every difference."""
    problems = []
    for name, content in expected.items():
        path = EXAMPLES_DIR / name
        if not path.is_file():
            problems.append(f"missing: contracts/examples/{name}")
        elif path.read_text(encoding="utf-8") != content:
            problems.append(f"out of date: contracts/examples/{name}")
    problems.extend(f"not declared: contracts/examples/{name}" for name in unexpected_files(expected))
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        print("Run python contracts/extract_examples.py to regenerate.", file=sys.stderr)
        return 1
    print(f"{len(expected)} example files match the project context")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Parse the project context, resolve includes, then write or check the example files."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="compare only, write nothing")
    arguments = parser.parse_args(argv)
    try:
        if not CONTEXT_PATH.is_file():
            raise ExtractionError(f"{CONTEXT_PATH.relative_to(REPOSITORY_ROOT)} not found")
        examples = parse_examples(CONTEXT_PATH.read_text(encoding="utf-8"))
        expected = {
            name: render(resolve_includes(value, examples, (name,)))
            for name, value in examples.items()
        }
    except ExtractionError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return check_files(expected) if arguments.check else write_files(expected)


if __name__ == "__main__":
    sys.exit(main())
