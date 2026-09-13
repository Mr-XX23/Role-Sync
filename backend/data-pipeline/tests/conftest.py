"""Shared pytest configuration for the data-pipeline suite.

Pins the RAG pipeline stores to their in-memory behaviour so unit tests stay
hermetic: they never touch (or pollute) the live Postgres RAG database, and
assertions about counts are not affected by rows left over from earlier runs.

Set RAG_PERSISTENCE=on explicitly to run these against a real database.
"""
import os

os.environ.setdefault("RAG_PERSISTENCE", "off")

# The gatekeeper's semantic scorer makes a live Gemini call per document. Unit
# tests stay offline and deterministic; set GATEKEEPER_SEMANTIC_ENABLED=true to
# exercise it against the real model.
os.environ.setdefault("GATEKEEPER_SEMANTIC_ENABLED", "false")

# The staging queue is Redis-backed in the service. Unit tests must not depend on
# (or write into) a live broker, so they run the in-process fallback; the Redis
# code path is covered by injecting a fake client in test_durable_queue.py.
os.environ.setdefault("INGEST_QUEUE_BACKEND", "memory")


# Test runs must never write into the developer's live services. They did: the
# catalog suites' default database URL is localhost:5432, the published port of
# the real catalog database, so every run left dozens of random-UUID tenants in it
# (1,724 had accumulated). Run inside the container, the suite also wrote test
# documents into the live MongoDB and uploaded fixtures to MinIO, and on the host
# every upload test staged files into the repository's storage/ folder.
#
# Set ROLESYNC_TESTS_USE_LIVE_SERVICES=1 to opt out deliberately.
if os.environ.get("ROLESYNC_TESTS_USE_LIVE_SERVICES", "").strip().lower() not in {"1", "true", "yes", "on"}:
    import atexit
    import shutil
    import tempfile

    _live_catalog = os.environ.get(
        "CATALOG_DATABASE_URL", "postgresql://postgres:root@localhost:5432/rolesync-micro-catalog"
    )
    _base, _, _db = _live_catalog.rpartition("/")
    _db_name = _db.split("?", 1)[0]
    if _db_name and not _db_name.endswith("-test"):
        # Same server and credentials, separate database; catalog.database creates
        # it on first use.
        os.environ["CATALOG_DATABASE_URL"] = f"{_base}/{_db_name}-test"

    # Nothing listens here, so every Mongo-backed store falls back to memory, as it
    # already does on the host, where the compose hostname does not resolve.
    os.environ["MONGODB_URI"] = "mongodb://127.0.0.1:1"

    # Staged upload bytes go to a throwaway directory, not MinIO or the repo.
    os.environ["RAW_STORE_BACKEND"] = "local"
    _vault_dir = tempfile.mkdtemp(prefix="rolesync-test-vault-")
    os.environ["VAULT_STORAGE_DIR"] = _vault_dir
    atexit.register(shutil.rmtree, _vault_dir, True)


import pytest


@pytest.fixture(autouse=True)
def _isolated_ingest_queue():
    """Start every test with an empty ingestion queue.

    The queue is a process-wide singleton, so any test that uploads a document
    leaves jobs behind in it. A later test that starts a worker then spends its
    time draining someone else's jobs before reaching its own - which made queue
    tests pass or fail depending on what ran before them.
    """
    from module_1_document_processing.pipeline.durable_queue import ingest_queue

    ingest_queue.purge()
    yield
    ingest_queue.purge()
