"""Structured logging with job context."""

import logging
from contextvars import ContextVar

# Context variable for current job ID
job_context: ContextVar[str] = ContextVar("job_id", default="none")


class JobContextFilter(logging.Filter):
    """Inject job_id into all log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, 'job_id'):
            record.job_id = job_context.get()
        return True


def setup_logging(level: int = logging.INFO) -> None:
    """Configure logging with job context filter."""
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - [job:%(job_id)s] - %(message)s"
    )

    job_filter = JobContextFilter()
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Clear any existing handlers to start fresh
    root_logger.handlers.clear()

    # Add a single properly configured handler
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    handler.addFilter(job_filter)
    root_logger.addHandler(handler)
