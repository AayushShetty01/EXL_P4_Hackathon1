"""Checks that quoted evidence really is in the cited file (no LLM).

Whitespace, case and curly quotes are normalised. A quote that is not at the cited lines is searched for
in the whole file and the line numbers are corrected; a quote that is nowhere in the file is UNVERIFIED.
Files are read through the safe reader, so the answer keys can never be used as evidence.
"""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.api_schemas import Evidence
from app.config import Settings
from app.estate_scanner import FileAccessError, read_text_file

QUOTE_REPLACEMENTS = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'})


class EvidenceReply(BaseModel):
    """Evidence as an agent returns it; line numbers may be missing or wrong."""

    model_config = ConfigDict(extra="ignore")

    file: str
    start_line: int | None = None
    end_line: int | None = None
    quote: str = ""


@dataclass(frozen=True)
class EvidenceCheck:
    """The verdict for one piece of evidence, with corrected line numbers when the quote was found."""

    evidence: Evidence
    status: Literal["VERIFIED", "UNVERIFIED"]
    note: str


def normalise(text: str) -> str:
    """Lower case, straight quotes and single spaces."""
    return " ".join(text.translate(QUOTE_REPLACEMENTS).lower().split())


def find_quote(lines: list[str], quote: str) -> tuple[int, int] | None:
    """First and last line (1 based) where the normalised quote appears, also across line breaks."""
    pieces: list[str] = []
    line_of_offset: list[tuple[int, int]] = []
    offset = 0
    for number, line in enumerate(lines, start=1):
        piece = normalise(line)
        if not piece:
            continue
        line_of_offset.append((offset, number))
        pieces.append(piece)
        offset += len(piece) + 1
    position = " ".join(pieces).find(quote)
    if position == -1:
        return None
    last_char = position + len(quote) - 1
    start = max(number for start_offset, number in line_of_offset if start_offset <= position)
    end = max(number for start_offset, number in line_of_offset if start_offset <= last_char)
    return start, end


def verify_evidence(settings: Settings, evidence: EvidenceReply, allowed_folder: str | None = None) -> EvidenceCheck:
    """Verify one quote against its file; allowed_folder limits evidence to one model folder."""
    start = evidence.start_line or 0
    end = evidence.end_line or start
    start, end = min(start, end), max(start, end)
    cited = Evidence(file=evidence.file, start_line=max(start, 1), end_line=max(end, 1), quote=evidence.quote)
    quote = normalise(evidence.quote)
    if not quote:
        return EvidenceCheck(cited, "UNVERIFIED", "The evidence has no quote.")
    if allowed_folder and not evidence.file.startswith(f"{allowed_folder}/"):
        return EvidenceCheck(cited, "UNVERIFIED", f"The file is outside {allowed_folder}.")
    try:
        lines = read_text_file(settings, evidence.file).content.splitlines()
    except FileAccessError as error:
        return EvidenceCheck(cited, "UNVERIFIED", f"The file cannot be read: {error.message}")
    if start >= 1 and quote in normalise(" ".join(lines[start - 1 : end])):
        return EvidenceCheck(cited, "VERIFIED", "Quote found at the cited lines.")
    found = find_quote(lines, quote)
    if found is None:
        return EvidenceCheck(cited, "UNVERIFIED", "Quote not found in the file.")
    corrected = cited.model_copy(update={"start_line": found[0], "end_line": found[1]})
    return EvidenceCheck(corrected, "VERIFIED", f"Quote found at lines {found[0]}-{found[1]}; line numbers corrected.")
