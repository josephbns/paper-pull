"""Scoped console/file logging with a run identifier on every emitted line."""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class RunFilter(logging.Filter):
    """Attach context to records from all pubmon child loggers."""

    def __init__(self, run_id: str) -> None:
        super().__init__()
        self.run_id = run_id

    def filter(self, record: logging.LogRecord) -> bool:
        """Set the run context without reading credentials or application data."""
        record.run_id = self.run_id
        return True


@contextmanager
def run_logging(path: Path, run_id: str) -> Iterator[None]:
    """Install and clean up handlers so repeated CLI calls do not duplicate logs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("pubmon")
    old_level = logger.level
    handlers = [logging.StreamHandler(), logging.FileHandler(path, encoding="utf-8")]
    for handler in handlers:
        handler.addFilter(RunFilter(run_id))
        handler.setFormatter(logging.Formatter("[run_id=%(run_id)s] %(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        yield
    finally:
        for handler in handlers:
            logger.removeHandler(handler)
            handler.close()
        logger.setLevel(old_level)
