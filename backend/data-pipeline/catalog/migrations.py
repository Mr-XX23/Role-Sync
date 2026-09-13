import logging
from sqlalchemy import text
from catalog.database import Base, get_engine
import catalog.models  # Ensure all models are registered with Base.metadata
from catalog.models import STOCK_MOVEMENT_REASON_CHECK, STOCK_MOVEMENT_REASONS

logger = logging.getLogger("catalog.migrations")

# create_all() makes missing tables but never changes existing ones, so columns, indexes
# and checks added to a table after it first shipped are applied here.
STOCK_MOVEMENT_NEW_COLUMNS = [
    ("reference", "VARCHAR(255)"),
    ("counterparty", "VARCHAR(255)"),
    ("on_hand_after", "INTEGER"),
]
STOCK_MOVEMENT_NEW_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_stock_mov_tenant_at ON catalog.stock_movement (tenant_id, at);",
]


def _upgrade_stock_movement(conn) -> None:
    existing = set(
        conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'catalog' AND table_name = 'stock_movement'"
            )
        ).scalars()
    )
    for column, column_type in STOCK_MOVEMENT_NEW_COLUMNS:
        if column not in existing:  # checked first: ALTER TABLE locks the table even when it does nothing
            conn.execute(text(f"ALTER TABLE catalog.stock_movement ADD COLUMN {column} {column_type};"))
            logger.info("Added catalog.stock_movement.%s.", column)
    for index_sql in STOCK_MOVEMENT_NEW_INDEXES:
        conn.execute(text(index_sql))
    _ensure_stock_movement_reasons(conn)


def _ensure_stock_movement_reasons(conn) -> None:
    """Widen the ledger's reason check when new reasons were added (LOST, RETURN)."""
    current = conn.execute(
        text(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conname = 'ck_stock_movement_reason' AND conrelid = 'catalog.stock_movement'::regclass"
        )
    ).scalar()
    if current is not None and all(f"'{reason}'" in current for reason in STOCK_MOVEMENT_REASONS):
        return
    conn.execute(text("ALTER TABLE catalog.stock_movement DROP CONSTRAINT IF EXISTS ck_stock_movement_reason;"))
    conn.execute(
        text(f"ALTER TABLE catalog.stock_movement ADD CONSTRAINT ck_stock_movement_reason CHECK ({STOCK_MOVEMENT_REASON_CHECK});")
    )
    logger.info("Stock movement reasons updated to %s.", ", ".join(STOCK_MOVEMENT_REASONS))

VIEW_DDL = """
CREATE OR REPLACE VIEW catalog.v_variant_availability AS
SELECT il.tenant_id, il.variant_id,
       GREATEST(0, COALESCE(SUM(GREATEST(0, il.qty_on_hand - il.qty_reserved)), 0)) AS qty_available
FROM catalog.inventory_level il
JOIN catalog.location loc ON loc.id = il.location_id
WHERE loc.sellable = true
GROUP BY il.tenant_id, il.variant_id;
"""

GIN_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_product_keywords_gin ON catalog.product USING gin (keywords);",
    "CREATE INDEX IF NOT EXISTS idx_product_use_cases_gin ON catalog.product USING gin (use_cases);",
    "CREATE INDEX IF NOT EXISTS idx_product_target_industries_gin ON catalog.product USING gin (target_industries);",
    "CREATE INDEX IF NOT EXISTS idx_product_competitors_beats_gin ON catalog.product USING gin (competitors_beats);",
    "CREATE INDEX IF NOT EXISTS idx_product_sales_tags_gin ON catalog.product USING gin (sales_tags);",
]


def run_migrations(engine=None) -> None:
    if engine is None:
        engine = get_engine()

    # 1. Ensure schema exists
    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS catalog;"))

    # 2. Create tables
    Base.metadata.create_all(bind=engine)
    logger.info("Catalog tables verified/created.")

    # 2b. Bring tables created by earlier versions up to date
    with engine.begin() as conn:
        _upgrade_stock_movement(conn)

    # 3. Create GIN indexes & View
    with engine.begin() as conn:
        for idx_sql in GIN_INDEXES:
            try:
                conn.execute(text(idx_sql))
            except Exception as e:
                logger.warning(f"Could not create GIN index '{idx_sql}': {e}")

        conn.execute(text(VIEW_DDL))
        logger.info("View catalog.v_variant_availability verified/created.")
