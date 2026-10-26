"""Analyzer service — parse diff, extract symbols, classify changes."""

import logging

from src.contracts.schemas import WebhookJob, ChangeReport, ChangedSymbol
from src.analyzer.ast_extractor import extract_symbols
from src.analyzer.classifier import classify_change
from src.analyzer.schemas import FileChange

logger = logging.getLogger(__name__)


async def analyze_diff(job: WebhookJob) -> ChangeReport:
    """Parse a unified diff, extract changed symbols, and classify them.

    Deterministic — no LLM calls are made here.
    """
    report = ChangeReport(job_id=job.job_id)

    files = _parse_diff(job.diff)
    report.files_changed = [f.path for f in files]

    for file_change in files:
        spans = await extract_symbols(file_change)
        for span in spans:
            symbol = ChangedSymbol(
                name=span.name,
                kind=span.kind,
                signature=span.source,
                file_path=file_change.path,
                diff_hunk="",
            )
            report.symbols.append(symbol)

    # Classify all symbols
    all_classes = set()
    for sym in report.symbols:
        classes = await classify_change(sym)
        all_classes.update(classes)
    report.change_classes = list(all_classes)

    logger.info(
        "Analyzed job %s: %d symbols, %d classes",
        job.job_id,
        len(report.symbols),
        len(report.change_classes),
    )
    return report


def _parse_diff(diff: str) -> list[FileChange]:
    """Parse unified diff into per-file FileChange objects."""
    if not diff.strip():
        return []
    files: list[FileChange] = []
    current: FileChange | None = None
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            if current:
                files.append(current)
            current = FileChange(path="")
        elif line.startswith("--- a/") and current:
            current.path = line[6:]
        elif line.startswith("+++ b/") and current and not current.path:
            current.path = line[6:]
        elif current:
            if line.startswith("@@"):
                current.hunks.append(line)
            elif line.startswith("+") and not line.startswith("+++"):
                current.added_lines.append(line[1:])
            elif line.startswith("-") and not line.startswith("---"):
                current.removed_lines.append(line[1:])
    if current and current.path:
        files.append(current)
    return files