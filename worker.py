"""pgqueuer worker entry point."""

import asyncio
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import asyncpg

from app.logging import setup_logging

# Configure logging with job context
setup_logging()

logger = logging.getLogger(__name__)


class HealthHandler(BaseHTTPRequestHandler):
    """Simple health check handler."""

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        pass  # Suppress request logs


def start_health_server(port: int = 8001):
    """Start HTTP health server in a background thread."""
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info(f"Health server started on port {port}")


async def ensure_pgqueuer_installed():
    """Ensure pgqueuer tables exist."""
    from asyncpg.exceptions import DuplicateObjectError

    from pgqueuer.queries import Queries

    from app.config import settings

    conn = await asyncpg.connect(settings.database_url)
    try:
        queries = Queries.from_asyncpg_connection(conn)
        await queries.install()
        logger.info("pgqueuer tables installed")
    except DuplicateObjectError:
        # Tables already exist from previous run - this is fine
        logger.debug("pgqueuer tables already exist, skipping install")
    finally:
        await conn.close()


async def main():
    """Start the pgqueuer worker."""
    from app.database import init_db
    from app.jobs.tasks import create_pgqueuer

    # Initialize database tables
    init_db()

    logger.info("Starting pgqueuer worker...")

    # Start health server for container healthchecks
    start_health_server()

    # Ensure pgqueuer tables are installed
    await ensure_pgqueuer_installed()

    pgq = await create_pgqueuer()

    logger.info("Worker ready, processing jobs...")
    await pgq.run()


if __name__ == "__main__":
    asyncio.run(main())

