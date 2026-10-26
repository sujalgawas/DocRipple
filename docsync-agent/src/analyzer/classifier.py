"""Rule engine for classifying changes into semantic categories."""

import logging

from src.contracts.schemas import ChangeClass, ChangedSymbol

logger = logging.getLogger(__name__)

# Heuristic keyword sets
_API_INDICATORS = {"route", "endpoint", "router", "controller", "api", "rest"}
_CLI_INDICATORS = {"argparse", "click", "typer", "arg", "flag", "cli", "command"}
_ENV_INDICATORS = {"env", "config", "settings", "os.environ", "getenv", "dotenv"}
_DEPS_INDICATORS = {"requirements", "pyproject", "Cargo.toml", "package.json", "go.mod"}


async def classify_change(symbol: ChangedSymbol) -> list[ChangeClass]:
    """Apply heuristics to categorise a changed symbol."""
    classes: list[ChangeClass] = []

    sig_lower = symbol.signature.lower()
    name_lower = symbol.name.lower()
    combined = f"{name_lower} {sig_lower}"

    if any(kw in combined for kw in _API_INDICATORS):
        classes.append(ChangeClass.API_SURFACE)
    if any(kw in combined for kw in _CLI_INDICATORS):
        classes.append(ChangeClass.CLI)
    if any(kw in combined for kw in _ENV_INDICATORS):
        classes.append(ChangeClass.ENV_CONFIG)
    if any(kw in symbol.file_path for kw in _DEPS_INDICATORS):
        classes.append(ChangeClass.DEPS)

    if not classes:
        classes.append(ChangeClass.BEHAVIOR)

    return classes