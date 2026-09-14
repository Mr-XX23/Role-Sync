"""What happens to a stock count when stock is received, sold, shipped, damaged, lost,
returned or recounted, and how the history and totals read back.

"Update Stock" used to replace the count whatever the reason: 10 on hand plus 20 received
left 20, a sale left whatever number was typed, and nothing said who bought it or where a
shipment went. Now each kind of event moves the count one way, and only an owner or admin
can replace a count, with a note. Runs against the catalog test database.
"""

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import text

from catalog.database import SessionLocal, get_engine, init_catalog_db
from catalog.migrations import run_migrations
from catalog.models import InventoryLevel, StockMovement
from catalog.schemas import (
    CategoryCreate,
    LocationCreate,
    ProductCreate,
    ProductOptionCreate,
    OptionValueCreate,
    RecordMovementRequest,
    VariantCreate,
)
from catalog.service import ProductService
from catalog.stock_movements import StockConflictError, StockPermissionError


@pytest.fixture(scope="module", autouse=True)
def setup_catalog():
    init_catalog_db()


@pytest.fixture
def service():
    session = SessionLocal()
    try:
        yield ProductService(session)
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def env(service):
    tenant = uuid.uuid4()
    service.upsert_category(tenant, CategoryCreate(key="chairs", label="Chairs"))
    product = service.upsert_product(tenant, ProductCreate(name="Desk Chair", category="chairs", status="ACTIVE"), "u1")
    (color,) = service.set_options(
        tenant,
        product.id,
        [
            ProductOptionCreate(
                name="Color",
                values=[OptionValueCreate(value="Black", position=0), OptionValueCreate(value="Grey", position=1)],
            )
        ],
    )
    black, grey = color.values
    variants = service.upsert_variants(
        tenant,
        product.id,
        [
            VariantCreate(sku="CHAIR-BLK", price=Decimal("120.00"), option_value_ids=[black.id]),
            VariantCreate(sku="CHAIR-GRY", price=Decimal("120.00"), option_value_ids=[grey.id]),
        ],
    )
    by_sku = {variant.sku: variant for variant in variants}  # returned in no particular order
    return {
        "tenant": tenant,
        "variant": by_sku["CHAIR-BLK"],
        "other_variant": by_sku["CHAIR-GRY"],
        "main": service.upsert_location(tenant, LocationCreate(name="Main Warehouse", priority=10)),
        "store": service.upsert_location(tenant, LocationCreate(name="City Store", type="STORE", priority=20)),
        "cage": service.upsert_location(tenant, LocationCreate(name="Returns Cage", priority=30, sellable=False)),
    }


def record(service, env, kind, qty, *, at="main", variant="variant", can_correct=False, **fields):
    if "to" in fields:
        fields["to_location_id"] = env[fields.pop("to")].id
    return service.record_movement(
        env["tenant"],
        RecordMovementRequest(type=kind, variant_id=env[variant].id, location_id=env[at].id, qty=qty, **fields),
        created_by="user-1",
        can_correct=can_correct,
    )


def stock(service, env, at="main", variant="variant"):
    level = (
        service.db.query(InventoryLevel)
        .filter(InventoryLevel.variant_id == env[variant].id, InventoryLevel.location_id == env[at].id)
        .one_or_none()
    )
    return (level.qty_on_hand, level.qty_reserved) if level else (0, 0)


def opening_stock(service, env, qty, at="main", variant="variant"):
    service.set_stock(env["tenant"], env[variant].id, env[at].id, qty)


# --- each event moves the count one way -------------------------------------
def test_received_stock_is_added_to_the_count_not_put_in_its_place(service, env):
    opening_stock(service, env, 10)

    result = record(service, env, "RECEIVED", 20, counterparty="Acme Supply", reference="PO-89410")

    assert stock(service, env) == (30, 0)
    assert result.changed is True
    assert [(level.qty_on_hand_before, level.qty_on_hand) for level in result.levels] == [(10, 30)]
    (row,) = result.movements
    assert (row.type, row.reason, row.delta, row.on_hand_after) == ("RECEIVED", "RESTOCK", 20, 30)
    assert (row.counterparty, row.reference, row.created_by) == ("Acme Supply", "PO-89410", "user-1")
    assert (row.product_name, row.sku, row.variant_label, row.location_name) == (
        "Desk Chair", "CHAIR-BLK", "Black", "Main Warehouse"
    )


def test_a_sale_takes_available_units_and_says_who_bought_them(service, env):
    opening_stock(service, env, 10)
    service.reserve(env["tenant"], "CHAIR-BLK", 3, location_id=env["main"].id)

    result = record(service, env, "SOLD", 7, counterparty="Northwind Traders", reference="INV-1234")

    assert stock(service, env) == (3, 3)
    (row,) = result.movements
    assert (row.type, row.delta, row.counterparty, row.reference) == ("SOLD", -7, "Northwind Traders", "INV-1234")

    # The 3 left are promised to a customer.
    with pytest.raises(ValueError, match=r"Insufficient available stock at Main Warehouse: 0 available \(3 on hand, 3 reserved\)"):
        record(service, env, "SOLD", 1)
    assert stock(service, env) == (3, 3)


def test_nothing_is_sold_from_a_location_that_is_not_sellable(service, env):
    opening_stock(service, env, 5, at="cage")

    with pytest.raises(ValueError, match="Returns Cage is not a sellable location"):
        record(service, env, "SOLD", 1, at="cage")
    assert stock(service, env, at="cage") == (5, 0)


def test_shipping_takes_stock_from_one_location_and_adds_it_at_the_other(service, env):
    opening_stock(service, env, 10)
    opening_stock(service, env, 2, at="store")

    result = record(service, env, "SHIPPED", 3, to="store", reference="SHIP-7")

    assert stock(service, env) == (7, 0)
    assert stock(service, env, at="store") == (5, 0)
    assert [(level.location_name, level.qty_on_hand_before, level.qty_on_hand) for level in result.levels] == [
        ("Main Warehouse", 10, 7),
        ("City Store", 2, 5),
    ]
    out_row, in_row = result.movements
    assert (out_row.type, out_row.delta, out_row.other_location_name) == ("SHIPPED_OUT", -3, "City Store")
    assert (in_row.type, in_row.delta, in_row.other_location_name) == ("SHIPPED_IN", 3, "Main Warehouse")
    assert out_row.ref_id == in_row.ref_id == result.ref_id


def test_a_shipment_needs_a_different_destination_and_enough_available_stock(service, env):
    opening_stock(service, env, 4)

    with pytest.raises(ValueError, match="Choose the location"):
        record(service, env, "SHIPPED", 1)
    with pytest.raises(ValueError, match="already at"):
        record(service, env, "SHIPPED", 1, to="main")
    with pytest.raises(ValueError, match="so 5 can't be shipped"):
        record(service, env, "SHIPPED", 5, to="store")
    assert stock(service, env) == (4, 0)
    assert stock(service, env, at="store") == (0, 0)


def test_the_transfer_route_and_a_shipment_are_the_same_operation(service, env):
    opening_stock(service, env, 6)

    transfer = service.transfer(env["tenant"], "CHAIR-BLK", env["main"].id, env["store"].id, 2, note="Rebalance")

    history = service.list_movements(env["tenant"], variant_id=env["variant"].id, reasons=["TRANSFER_OUT", "TRANSFER_IN"])
    assert {(row.type, row.delta, row.other_location_name, row.note) for row in history.items} == {
        ("SHIPPED_OUT", -2, "City Store", "Rebalance"),
        ("SHIPPED_IN", 2, "Main Warehouse", "Rebalance"),
    }
    assert {row.ref_id for row in history.items} == {transfer.ref_id}


def test_damaged_and_lost_are_separate_write_offs_of_available_units(service, env):
    opening_stock(service, env, 10)

    record(service, env, "DAMAGED", 2, note="Crushed in delivery")
    record(service, env, "LOST", 1)

    assert stock(service, env) == (7, 0)
    summary = service.movement_summary(env["tenant"], location_id=env["main"].id)
    assert (summary.totals.damaged, summary.totals.lost) == (2, 1)
    with pytest.raises(ValueError, match="so 8 can't be written off as lost"):
        record(service, env, "LOST", 8)


def test_a_customer_return_goes_back_on_sale_or_is_written_off(service, env):
    opening_stock(service, env, 5)

    record(service, env, "RETURNED", 2, counterparty="Northwind Traders", reference="RMA-1")
    assert stock(service, env) == (7, 0)

    result = record(service, env, "RETURNED", 3, resellable=False, counterparty="Contoso")
    assert stock(service, env) == (7, 0)  # back in the building, but not stock anyone can sell
    assert [(row.type, row.delta, row.on_hand_after, row.counterparty) for row in result.movements] == [
        ("RETURNED", 3, 10, "Contoso"),
        ("DAMAGED", -3, 7, "Contoso"),
    ]
    summary = service.movement_summary(env["tenant"], location_id=env["main"].id)
    assert (summary.totals.returned, summary.totals.damaged, summary.totals.net_change) == (5, 3, 7)


def test_every_event_but_a_count_correction_needs_at_least_one_unit(service, env):
    for kind in ("RECEIVED", "SOLD", "DAMAGED", "LOST", "RETURNED"):
        with pytest.raises(ValueError, match="at least 1"):
            record(service, env, kind, 0)


# --- replacing a count ------------------------------------------------------
def test_only_owners_and_admins_correct_a_count_and_they_must_say_why(service, env):
    opening_stock(service, env, 10)

    with pytest.raises(StockPermissionError, match="Only workspace owners and admins"):
        record(service, env, "COUNT_CORRECTION", 8, note="Shelf count", expected_on_hand=10)
    with pytest.raises(ValueError, match="needs a note"):
        record(service, env, "COUNT_CORRECTION", 8, note="   ", expected_on_hand=10, can_correct=True)
    assert stock(service, env) == (10, 0)

    result = record(service, env, "COUNT_CORRECTION", 8, note="Shelf count", expected_on_hand=10, can_correct=True)

    assert stock(service, env) == (8, 0)
    (row,) = result.movements
    assert (row.type, row.reason, row.delta, row.on_hand_after, row.note) == ("CORRECTION", "ADJUST", -2, 8, "Shelf count")


def test_a_count_that_matches_changes_nothing(service, env):
    opening_stock(service, env, 10)

    result = record(service, env, "COUNT_CORRECTION", 10, note="Checked", expected_on_hand=10, can_correct=True)

    assert result.changed is False and result.movements == []
    assert service.list_movements(env["tenant"], variant_id=env["variant"].id).total == 1  # the opening stock


def test_a_correction_is_refused_when_the_count_changed_while_counting(service, env):
    opening_stock(service, env, 10)
    record(service, env, "SOLD", 1)  # someone sells one while the shelf is being counted

    with pytest.raises(StockConflictError, match="it is now 9, not 10"):
        record(service, env, "COUNT_CORRECTION", 12, note="Recount", expected_on_hand=10, can_correct=True)
    assert stock(service, env) == (9, 0)


def test_a_correction_cannot_go_below_reserved_units(service, env):
    opening_stock(service, env, 10)
    service.reserve(env["tenant"], "CHAIR-BLK", 4, location_id=env["main"].id)

    with pytest.raises(ValueError, match="count can't go below 4"):
        record(service, env, "COUNT_CORRECTION", 3, note="Recount", can_correct=True)
    assert stock(service, env) == (10, 4)


def test_set_stock_is_opening_stock_for_anyone_and_a_correction_over_an_existing_count(service, env):
    tenant, chair, main = env["tenant"], env["variant"].id, env["main"].id

    # Product wizard and CSV import put first stock at a location: anyone who can edit.
    service.set_stock(tenant, chair, main, 5, note="Initial stock")
    with pytest.raises(StockPermissionError):
        service.set_stock(tenant, chair, main, 8)
    with pytest.raises(ValueError, match="needs a note"):
        service.set_stock(tenant, chair, main, 8, can_correct=True)
    service.set_stock(tenant, chair, main, 5)  # same count: nothing to correct
    service.set_stock(tenant, chair, main, 8, note="Recount", can_correct=True)

    rows = service.list_movements(tenant, variant_id=chair).items
    assert [(row.reason, row.delta) for row in reversed(rows)] == [("RESTOCK", 5), ("ADJUST", 3)]
    # ADJUST is a correction even where there is no stock yet.
    with pytest.raises(StockPermissionError):
        service.set_stock(tenant, chair, env["store"].id, 4, reason="ADJUST")


def test_batch_set_stock_is_all_or_nothing_under_the_same_rules(service, env):
    tenant = env["tenant"]
    opening_stock(service, env, 5)
    items = [
        {"variant_id": env["other_variant"].id, "location_id": env["main"].id, "qty": 7},
        {"variant_id": env["variant"].id, "location_id": env["main"].id, "qty": 9},  # replaces 5
    ]

    with pytest.raises(StockPermissionError):
        service.batch_set_stock(tenant, items)
    assert stock(service, env, variant="other_variant") == (0, 0)

    service.batch_set_stock(tenant, [{**item, "note": "Stocktake"} for item in items], can_correct=True)
    assert stock(service, env, variant="other_variant") == (7, 0)
    assert stock(service, env) == (9, 0)


def test_adjust_stock_moves_each_reason_its_own_way(service, env):
    tenant, chair, main = env["tenant"], env["variant"].id, env["main"].id
    opening_stock(service, env, 10)

    with pytest.raises(ValueError, match="RESTOCK adds stock"):
        service.adjust_stock(tenant, chair, main, -1, reason="RESTOCK")
    with pytest.raises(ValueError, match="SALE removes stock"):
        service.adjust_stock(tenant, chair, main, 1, reason="SALE")
    with pytest.raises(ValueError, match="must not be zero"):
        service.adjust_stock(tenant, chair, main, 0, reason="DAMAGE")
    with pytest.raises(StockPermissionError):
        service.adjust_stock(tenant, chair, main, -2, note="Recount")
    assert stock(service, env) == (10, 0)

    service.adjust_stock(tenant, chair, main, -2, reason="SALE")
    service.adjust_stock(tenant, chair, main, -3, note="Recount", can_correct=True)
    assert stock(service, env) == (5, 0)


# --- reading it back --------------------------------------------------------
def test_history_is_newest_first_and_filters_by_product_location_reason_and_date(service, env):
    tenant = env["tenant"]
    opening_stock(service, env, 10)
    opening_stock(service, env, 4, variant="other_variant")
    record(service, env, "SOLD", 2, counterparty="Northwind Traders")
    record(service, env, "SHIPPED", 3, to="store")
    service.reserve(tenant, "CHAIR-BLK", 1, location_id=env["main"].id)

    everything = service.list_movements(tenant)
    assert [(row.sku, row.type, row.location_name) for row in everything.items] == [
        ("CHAIR-BLK", "SHIPPED_IN", "City Store"),
        ("CHAIR-BLK", "SHIPPED_OUT", "Main Warehouse"),
        ("CHAIR-BLK", "SOLD", "Main Warehouse"),
        ("CHAIR-GRY", "RECEIVED", "Main Warehouse"),
        ("CHAIR-BLK", "RECEIVED", "Main Warehouse"),
    ]  # the reservation hold is left out
    assert everything.total == 5
    assert service.list_movements(tenant, include_holds=True).items[0].type == "RESERVED"

    grey = service.list_movements(tenant, variant_id=env["other_variant"].id)
    assert [(row.sku, row.variant_label) for row in grey.items] == [("CHAIR-GRY", "Grey")]
    store = service.list_movements(tenant, location_id=env["store"].id)
    assert [(row.type, row.other_location_name) for row in store.items] == [("SHIPPED_IN", "Main Warehouse")]
    sales = service.list_movements(tenant, reasons=["SALE"])
    assert [(row.delta, row.counterparty) for row in sales.items] == [(-2, "Northwind Traders")]

    page = service.list_movements(tenant, limit=2, offset=2)
    assert [row.type for row in page.items] == ["SOLD", "RECEIVED"] and page.total == 5

    later = datetime.now(timezone.utc) + timedelta(minutes=5)
    assert service.list_movements(tenant, date_from=later).total == 0
    assert service.list_movements(tenant, date_to=later).total == 5

    with pytest.raises(ValueError, match="Unknown movement reason: STOLEN"):
        service.list_movements(tenant, reasons=["STOLEN"])


def test_history_narrows_to_the_rows_of_one_action(service, env):
    tenant = env["tenant"]
    opening_stock(service, env, 10)
    opening_stock(service, env, 10, at="store")
    shipment = record(service, env, "SHIPPED", 2, to="store")  # main 8, store 12
    held = service.reserve(tenant, "CHAIR-BLK", 15)  # no one location has 15: 8 at main, 7 at the store
    service.reserve(tenant, "CHAIR-BLK", 1)

    shipped = service.list_movements(tenant, ref_id=shipment.ref_id)
    assert sorted(row.type for row in shipped.items) == ["SHIPPED_IN", "SHIPPED_OUT"]
    # A reservation's holds are only listed when asked for, like any hold.
    assert service.list_movements(tenant, ref_id=held.reservation_id).total == 0
    holds = service.list_movements(tenant, ref_id=held.reservation_id, reasons=["RESERVE", "RELEASE"])
    assert sorted((row.location_name, row.delta) for row in holds.items) == [("City Store", 7), ("Main Warehouse", 8)]

    service.release(tenant, held.reservation_id)
    released = service.list_movements(tenant, ref_id=held.reservation_id, reasons=["RELEASE"])
    assert sum(row.delta for row in released.items) == 15


def test_summary_totals_each_kind_of_event_per_location(service, env):
    tenant = env["tenant"]
    opening_stock(service, env, 50)
    record(service, env, "RECEIVED", 10)
    record(service, env, "SOLD", 12)
    record(service, env, "SHIPPED", 8, to="store")
    record(service, env, "SOLD", 3, at="store")
    record(service, env, "DAMAGED", 2)
    record(service, env, "LOST", 1)
    record(service, env, "RETURNED", 4, resellable=False)
    record(service, env, "COUNT_CORRECTION", 40, note="Stocktake", can_correct=True)
    service.reserve(tenant, "CHAIR-BLK", 5, location_id=env["main"].id)

    summary = service.movement_summary(tenant, variant_id=env["variant"].id)

    by_name = {place.location_name: place for place in summary.locations}
    assert list(by_name) == ["Main Warehouse", "City Store", "Returns Cage"]  # by priority
    main = by_name["Main Warehouse"]
    # 50 + 10 - 12 - 8 - 2 - 1 + (4 - 4) = 37, counted 40
    assert (main.received, main.sold, main.shipped_out, main.damaged, main.lost, main.returned) == (60, 12, 8, 6, 1, 4)
    assert (main.corrected_up, main.corrected_down, main.net_change) == (3, 0, 40)
    assert (main.qty_on_hand, main.qty_reserved, main.qty_available) == (40, 5, 35)
    store = by_name["City Store"]
    assert (store.shipped_in, store.sold, store.net_change, store.qty_on_hand) == (8, 3, 5, 5)
    assert by_name["Returns Cage"].movements == 0
    assert (summary.totals.sold, summary.totals.shipped_out, summary.totals.shipped_in) == (15, 8, 8)
    assert summary.totals.net_change == 45 == main.qty_on_hand + store.qty_on_hand

    later = datetime.now(timezone.utc) + timedelta(minutes=5)
    quiet = service.movement_summary(tenant, date_from=later)
    assert quiet.totals.movements == 0
    assert quiet.locations[0].qty_on_hand == 40  # current stock doesn't depend on the period


def test_the_ledger_always_explains_the_count(service, env):
    """Summing a location's rows (holds aside) gives its count, and the newest row says so too."""
    tenant = env["tenant"]
    opening_stock(service, env, 30)
    record(service, env, "SOLD", 4)
    record(service, env, "SHIPPED", 6, to="store")
    record(service, env, "RETURNED", 2, at="store", resellable=False)
    service.transfer(tenant, "CHAIR-BLK", env["store"].id, env["cage"].id, 1)
    service.adjust_stock(tenant, env["variant"].id, env["main"].id, -1, reason="DAMAGE")
    record(service, env, "COUNT_CORRECTION", 21, note="Stocktake", can_correct=True)
    service.reserve(tenant, "CHAIR-BLK", 2, location_id=env["main"].id)

    for place in ("main", "store", "cage"):
        rows = service.list_movements(tenant, location_id=env[place].id, limit=200).items
        on_hand, _ = stock(service, env, at=place)
        assert sum(row.delta for row in rows) == on_hand, place
        assert rows[0].on_hand_after == on_hand, place


def test_one_workspace_never_sees_or_moves_another_workspaces_stock(service, env):
    opening_stock(service, env, 10)
    stranger = uuid.uuid4()
    their_store = service.upsert_location(stranger, LocationCreate(name="Their Store"))

    with pytest.raises(ValueError, match="not found"):
        service.record_movement(
            stranger,
            RecordMovementRequest(type="RECEIVED", variant_id=env["variant"].id, location_id=their_store.id, qty=1),
        )
    with pytest.raises(ValueError, match="not found"):
        record(service, env, "SHIPPED", 1, to_location_id=their_store.id)
    assert service.list_movements(stranger).total == 0
    assert service.movement_summary(stranger).totals.movements == 0


# --- upgrading an existing database -----------------------------------------
def test_startup_upgrades_a_ledger_table_created_before_movement_types():
    engine = get_engine()
    old_check = (
        "reason IN ('RESTOCK', 'SALE', 'RESERVE', 'RELEASE', 'TRANSFER_IN', 'TRANSFER_OUT', 'ADJUST', 'DAMAGE')"
    )
    with engine.begin() as conn:
        conn.execute(text("DROP INDEX IF EXISTS catalog.idx_stock_mov_tenant_at"))
        for column in ("reference", "counterparty", "on_hand_after"):
            conn.execute(text(f"ALTER TABLE catalog.stock_movement DROP COLUMN IF EXISTS {column}"))
        conn.execute(text("ALTER TABLE catalog.stock_movement DROP CONSTRAINT IF EXISTS ck_stock_movement_reason"))
        # NOT VALID: rows written by the tests above already use the new reasons.
        conn.execute(
            text(f"ALTER TABLE catalog.stock_movement ADD CONSTRAINT ck_stock_movement_reason CHECK ({old_check}) NOT VALID")
        )

    run_migrations(engine)
    run_migrations(engine)  # and again, as on every restart

    with engine.begin() as conn:
        columns = set(
            conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'catalog' AND table_name = 'stock_movement'"
                )
            ).scalars()
        )
        check = conn.execute(
            text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conname = 'ck_stock_movement_reason' AND conrelid = 'catalog.stock_movement'::regclass"
            )
        ).scalar()
        index = conn.execute(text("SELECT to_regclass('catalog.idx_stock_mov_tenant_at')")).scalar()
    assert {"reference", "counterparty", "on_hand_after"} <= columns
    assert "'LOST'" in check and "'RETURN'" in check
    assert index is not None
