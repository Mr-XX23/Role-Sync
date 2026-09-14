"""The catalog tools that match the Product Management page: listing and reading items, the catalog's
setup (categories, stock locations), SKUs and options of existing items, restoring retired items,
and stock reservations. Runs against the in-memory data-pipeline double."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from app.core.context import AgentContext, RunMode
from app.tools.adapters.catalog import catalog_tools
from app.tools.adapters.catalog_setup import catalog_setup_tools
from app.tools.adapters.catalog_writes import catalog_write_tools
from app.tools.registry import ToolDefinition
from app.tools.types import ToolAccessDenied, ToolFailed, ToolInputError, ToolInvocation, UndoInvocation
from tests.fake_data_pipeline import MAIN_WAREHOUSE, STORE, FakeDataPipeline, stock_of

CTX = AgentContext(tenant_id=uuid4(), user_id=uuid4(), session_id=uuid4(), mode=RunMode.INTERACTIVE, turn=1)


class Directory:
    def __init__(self, role: str | None = "MEMBER") -> None:
        self.role = role

    async def role_in(self, user_id: UUID, tenant_id: UUID) -> str | None:
        return self.role


def _tools(pipeline: FakeDataPipeline, role: str = "MEMBER") -> dict[str, ToolDefinition]:
    client, directory = pipeline.client(), Directory(role)
    definitions = [*catalog_tools(client), *catalog_write_tools(client, directory), *catalog_setup_tools(client, directory)]
    return {definition.name: definition for definition in definitions}


async def _read(definition: ToolDefinition, **arguments: Any):
    return await definition.handler(ToolInvocation(CTX, "orchestrator", "r1", definition.input_model.model_validate(arguments)))


async def _run(definition: ToolDefinition, arguments: dict[str, Any], *, call_id: str = "c1"):
    """Like the gate: check arguments and access, build the approval preview, then run."""
    args = definition.input_model.model_validate(arguments)
    if definition.acl is not None:
        await definition.acl(CTX, args)
    preview = await definition.build_preview(CTX, args)
    return preview, await definition.handler(ToolInvocation(CTX, "orchestrator", call_id, args))


async def _undo(definition: ToolDefinition, output) -> str:
    assert output.undo is not None and definition.undo_handler is not None
    return await definition.undo_handler(UndoInvocation(CTX, output.undo.args))


def _sent(pipeline: FakeDataPipeline, method: str, suffix: str) -> list[Any]:
    return [body for verb, path, body in pipeline.requests if verb == method and path.endswith(suffix)]


# --------------------------------------------------------------------------- reads


async def test_listing_shows_active_and_draft_items_newest_first_with_their_stock():
    pipeline = FakeDataPipeline()
    pipeline.locations.append({"id": STORE, "name": "Store", "sellable": True, "priority": 2})
    pipeline.add_product(name="Starter plan", sku="START-1", price="19.00", on_hand=5)
    pipeline.add_product(name="Retired plan", sku="OLD-1", price="9.00", status="RETIRED")
    draft = pipeline.add_product(name="Pro plan", sku="PRO-1", price="99.00", status="DRAFT")
    pipeline.add_product(name="Headset", sku="HS-1", price="59.00", on_hand=2, location=STORE)
    tools = _tools(pipeline)

    listed = await _read(tools["list_catalog_items"], with_stock=True)

    assert [item["name"] for item in listed.data["items"]] == ["Headset", "Pro plan", "Starter plan"]
    assert listed.data["items"][1]["status"] == "DRAFT" and listed.data["items"][1]["product_id"] == draft["id"]
    assert listed.data["items"][0]["skus"] == [
        {"sku": "HS-1", "price": "59.00", "currency": "USD", "status": "ACTIVE", "options": "Standard", "on_hand": 2, "reserved": 0, "available": 2}
    ]
    assert [item["name"] for item in (await _read(tools["list_catalog_items"], status="RETIRED")).data["items"]] == ["Retired plan"]
    # Price and stock filters apply to the same SKU.
    cheap_in_stock = await _read(tools["list_catalog_items"], max_price=60, in_stock=True)
    assert [item["name"] for item in cheap_in_stock.data["items"]] == ["Headset", "Starter plan"]
    at_store = await _read(tools["list_catalog_items"], in_stock=True, location="store")
    assert [item["name"] for item in at_store.data["items"]] == ["Headset"]

    first = await _read(tools["list_catalog_items"], limit=2)
    assert (first.data["more"], first.data["next_offset"]) == (True, 2) and "more after offset 2" in first.summary
    assert [item["name"] for item in (await _read(tools["list_catalog_items"], limit=2, offset=2)).data["items"]] == ["Starter plan"]
    with pytest.raises(ValueError, match="pass in_stock true"):
        tools["list_catalog_items"].input_model.model_validate({"location": "Store"})


async def test_one_item_shows_its_options_and_each_skus_stock_by_location():
    pipeline = FakeDataPipeline()
    pipeline.locations.append({"id": STORE, "name": "Store", "sellable": False, "priority": 2})
    tee = pipeline.add_item(
        name="Team Tee",
        options={"Size": ["S", "M"], "Color": ["Black"]},
        skus=[("TEE-S", "20.00", {"Size": "S", "Color": "Black"}), ("TEE-M", "22.00", {"Size": "M", "Color": "Black"})],
    )
    medium = pipeline.variant_by_sku("TEE-M")
    pipeline.stock[(medium["id"], MAIN_WAREHOUSE)] = {"on_hand": 7, "reserved": 2}
    pipeline.stock[(medium["id"], STORE)] = {"on_hand": 3, "reserved": 0}
    tools = _tools(pipeline)

    output = await _read(tools["get_catalog_item"], sku="TEE-M")

    item = output.data
    assert item["product_id"] == tee["id"] and item["options"] == [{"name": "Size", "values": ["S", "M"]}, {"name": "Color", "values": ["Black"]}]
    by_sku = {sku["sku"]: sku for sku in item["skus"]}
    assert by_sku["TEE-M"]["options"] == {"Size": "M", "Color": "Black"}
    assert by_sku["TEE-M"]["stock"] == {
        "on_hand": 10, "reserved": 2, "available": 5,
        "locations": [
            {"location": "Main warehouse", "on_hand": 7, "reserved": 2, "available": 5, "sellable": True},
            {"location": "Store", "on_hand": 3, "reserved": 0, "available": 0, "sellable": False},
        ],
    }
    assert by_sku["TEE-S"]["stock"]["locations"] == []
    assert output.summary == "'Team Tee' (active): 2 SKUs, 5 available to sell"
    with pytest.raises(ValueError, match="either product_id or sku"):
        tools["get_catalog_item"].input_model.model_validate({})


async def test_the_catalog_setup_lists_categories_locations_and_option_names():
    pipeline = FakeDataPipeline()
    pipeline.category_details["apparel"] = {"label": "Apparel", "parent_key": None}
    pipeline.locations[0]["address"] = {"city": "Kathmandu", "priority_label": "Primary"}
    pipeline.add_item(name="Team Tee", options={"Size": ["M"]}, skus=[("TEE-M", "20.00", {"Size": "M"})])

    output = await _read(_tools(pipeline)["describe_catalog"])

    assert output.data["categories"] == [
        {"key": "apparel", "label": "Apparel", "parent_key": None},
        {"key": "software", "label": "Software", "parent_key": None},
    ]
    assert output.data["locations"] == [
        {"location_id": MAIN_WAREHOUSE, "name": "Main warehouse", "type": None, "sellable": True, "priority": 1, "city": "Kathmandu"}
    ]
    assert output.data["option_names"] == ["Size"] and output.summary == "2 categories and 1 stock location"


async def test_open_reservations_are_listed_and_a_release_shows_what_it_frees():
    pipeline = FakeDataPipeline()
    pipeline.add_product(name="Tee", sku="TEE-M", price="20.00", on_hand=10)
    tools = _tools(pipeline)
    _, held = await _run(tools["reserve_stock"], {"sku": "TEE-M", "quantity": 4}, call_id="a")
    await _run(tools["reserve_stock"], {"sku": "TEE-M", "quantity": 1}, call_id="b")

    listed = await _read(tools["list_stock_reservations"], sku="TEE-M")
    assert listed.data["open"] == 2 and listed.summary == "2 open reservations of TEE-M"
    first = next(item for item in listed.data["reservations"] if item["reservation_id"] == held.ref_id)
    assert (first["quantity"], first["locations"], first["reserved_by_you"], first["status"]) == (
        4, [{"location": "Main warehouse", "quantity": 4}], True, "open"
    )

    preview, _ = await _run(tools["release_stock"], {"reservation_id": held.ref_id})
    assert (preview["sku"], preview["quantity"], preview["reserved_by_you"]) == ("TEE-M", 4, True)
    assert stock_of(pipeline, "TEE-M")["reserved"] == 1

    after = await _read(tools["list_stock_reservations"])
    assert after.data["open"] == 1 and len(after.data["reservations"]) == 1
    everything = await _read(tools["list_stock_reservations"], include_released=True)
    assert sorted(item["status"] for item in everything.data["reservations"]) == ["open", "released"]
    # A release that can't happen is refused before anyone is asked to approve it.
    with pytest.raises(ToolInputError, match="already released"):
        await tools["release_stock"].build_preview(CTX, tools["release_stock"].input_model.model_validate({"reservation_id": held.ref_id}))
    with pytest.raises(ToolInputError, match="no reservation"):
        await tools["release_stock"].build_preview(CTX, tools["release_stock"].input_model.model_validate({"reservation_id": str(uuid4())}))


# --------------------------------------------------------------------------- items and SKUs


async def test_one_sku_is_retired_and_its_details_changed_and_undo_puts_them_back():
    pipeline = FakeDataPipeline()
    product = pipeline.add_product(name="Headset", sku="HS-1", price="59.00")
    update = _tools(pipeline)["update_catalog_item"]

    preview, output = await _run(
        update, {"product_id": product["id"], "type": "SERVICE", "sku_changes": [{"sku": "HS-1", "status": "RETIRED", "barcode": "", "weight": 2}]}
    )

    assert preview["changes"] == [{"field": "type", "before": "PRODUCT", "after": "SERVICE"}]
    assert preview["sku_changes"] == [
        {"sku": "HS-1", "field": "barcode", "before": "BAR-HS-1", "after": None},
        {"sku": "HS-1", "field": "weight", "before": "1.50", "after": "2.00"},
        {"sku": "HS-1", "field": "status", "before": "ACTIVE", "after": "RETIRED"},
    ]
    assert preview["warnings"] == ["'Headset' will have no active SKU left, so it can't be sold or quoted until one is reactivated"]
    variant = pipeline.variant_by_sku("HS-1")
    assert (variant["status"], variant["barcode"], variant["weight"], variant["price"]) == ("RETIRED", None, "2.00", "59.00")
    assert product["type"] == "SERVICE" and product["status"] == "ACTIVE"

    await _undo(update, output)
    assert (variant["status"], variant["barcode"], variant["weight"]) == ("ACTIVE", "BAR-HS-1", "1.50") and product["type"] == "PRODUCT"


async def test_a_retired_item_comes_back_only_through_restore():
    pipeline = FakeDataPipeline()
    product = pipeline.add_product(name="Legacy plan", sku="OLD-1", price="10.00", status="RETIRED")
    update = _tools(pipeline)["update_catalog_item"]
    with pytest.raises(ToolInputError, match="restore_catalog_item"):
        await _run(update, {"product_id": product["id"], "status": "ACTIVE"})
    with pytest.raises(ToolInputError, match="restore_catalog_item"):
        await _run(update, {"product_id": product["id"], "sku_changes": [{"sku": "OLD-1", "status": "ACTIVE"}]})


async def test_a_retired_item_is_restored_with_the_skus_named_and_undo_retires_it_again():
    pipeline = FakeDataPipeline()
    item = pipeline.add_item(
        name="Team Tee", options={"Size": ["S", "M"]}, skus=[("TEE-S", "20.00", {"Size": "S"}), ("TEE-M", "20.00", {"Size": "M"})], status="RETIRED"
    )
    tools = _tools(pipeline)
    with pytest.raises(ToolInputError, match="has no SKU TEE-XL"):
        await _run(tools["restore_catalog_item"], {"product_id": item["id"], "skus": ["TEE-XL"]})

    preview, output = await _run(tools["restore_catalog_item"], {"product_id": item["id"], "skus": ["TEE-M"]})

    assert (preview["kind"], preview["skus"], preview["staying_retired"]) == ("catalog_restore", ["TEE-M"], ["TEE-S"])
    assert item["status"] == "ACTIVE"
    assert {v["sku"]: v["status"] for v in item["variants"]} == {"TEE-S": "RETIRED", "TEE-M": "ACTIVE"}
    assert [v["option_values"][0]["value"] for v in item["variants"]] == ["S", "M"]  # still sized
    with pytest.raises(ToolInputError, match="isn't retired"):
        await _run(tools["restore_catalog_item"], {"product_id": item["id"]}, call_id="c2")

    assert "retired 'Team Tee' again with 1 SKU" == await _undo(tools["restore_catalog_item"], output)
    assert item["status"] == "RETIRED" and {v["status"] for v in item["variants"]} == {"RETIRED"}


async def test_new_items_can_have_options_and_every_sku_names_them():
    pipeline = FakeDataPipeline()
    create = _tools(pipeline)["create_catalog_item"]
    item = {
        "name": "Hoodie", "category": "apparel", "status": "ACTIVE",
        "variants": [
            {"sku": "HOOD-S-BLK", "price": 45, "barcode": "123", "options": [{"name": "Size", "value": "S"}, {"name": "Color", "value": "Black"}]},
            {"sku": "HOOD-M-BLK", "price": 45, "options": [{"name": "size", "value": "M"}, {"name": "Color", "value": "Black"}]},
        ],
    }
    with pytest.raises(ValueError, match="same options"):
        create.input_model.model_validate({**item, "variants": [item["variants"][0], {"sku": "HOOD-X", "price": 1, "options": [{"name": "Size", "value": "L"}]}]})
    with pytest.raises(ValueError, match="same option values"):
        create.input_model.model_validate({**item, "variants": [item["variants"][0], {**item["variants"][0], "sku": "HOOD-COPY"}]})

    preview, output = await _run(create, item)

    assert preview["options"] == [{"name": "Size", "values": ["S", "M"]}, {"name": "Color", "values": ["Black"]}]
    created = pipeline.products[output.ref_id]
    assert [(option["name"], [value["value"] for value in option["values"]]) for option in created["options"]] == [
        ("Size", ["S", "M"]), ("Color", ["Black"])
    ]
    linked = {v["sku"]: sorted(value["value"] for value in v["option_values"]) for v in created["variants"]}
    assert linked == {"HOOD-S-BLK": ["Black", "S"], "HOOD-M-BLK": ["Black", "M"]}
    assert pipeline.variant_by_sku("HOOD-S-BLK")["barcode"] == "123"
    assert "in 2 Size × 1 Color" in output.summary


async def test_skus_are_added_with_new_option_values_and_the_others_stay_linked():
    pipeline = FakeDataPipeline()
    tee = pipeline.add_item(name="Team Tee", options={"Size": ["S", "M"]}, skus=[("TEE-S", "20.00", {"Size": "S"}), ("TEE-M", "20.00", {"Size": "M"})])
    size_ids = [value["id"] for value in tee["options"][0]["values"]]
    add = _tools(pipeline)["add_catalog_skus"]

    for wrong, message in (
        ({"sku": "TEE-XL", "price": 24}, "say each new SKU's Size"),
        ({"sku": "TEE-XL", "price": 24, "options": [{"name": "Size", "value": "XL"}, {"name": "Fit", "value": "Slim"}]}, "has no option Fit"),
        ({"sku": "TEE-M2", "price": 24, "options": [{"name": "Size", "value": "m"}]}, "TEE-M already has Size m"),
        ({"sku": "TEE-S", "price": 24, "options": [{"name": "Size", "value": "XS"}]}, "already in use"),
    ):
        with pytest.raises(ToolInputError, match=message):
            await _run(add, {"product_id": tee["id"], "skus": [wrong]})

    preview, output = await _run(add, {"product_id": tee["id"], "skus": [{"sku": "TEE-XL", "price": 24, "options": [{"name": "size", "value": "XL"}]}]})

    assert preview["new_option_values"] == [{"name": "Size", "values": ["XL"]}]
    [options_sent] = _sent(pipeline, "PUT", "/options")
    assert options_sent == {"options": [{"name": "Size", "position": 0, "values": [
        {"value": "S", "position": 0}, {"value": "M", "position": 1}, {"value": "XL", "position": 2}
    ]}]}
    assert [value["id"] for value in tee["options"][0]["values"]][:2] == size_ids  # S and M keep their ids
    assert {v["sku"]: [value["value"] for value in v["option_values"]] for v in tee["variants"]} == {
        "TEE-S": ["S"], "TEE-M": ["M"], "TEE-XL": ["XL"]
    }

    assert await _undo(add, output) == "retired 1 SKU of 'Team Tee'"
    assert pipeline.variant_by_sku("TEE-XL")["status"] == "RETIRED" and pipeline.variant_by_sku("TEE-S")["status"] == "ACTIVE"
    assert "already retired" in await _undo(add, output)  # an undo step may run twice


async def test_skus_are_not_added_to_a_retired_item():
    pipeline = FakeDataPipeline()
    product = pipeline.add_product(name="Legacy plan", sku="OLD-1", price="10.00", status="RETIRED")
    with pytest.raises(ToolInputError, match="restore_catalog_item first"):
        await _run(_tools(pipeline)["add_catalog_skus"], {"product_id": product["id"], "skus": [{"sku": "OLD-2", "price": 5}]})


# --------------------------------------------------------------------------- categories and stock locations


async def test_categories_are_added_renamed_and_removed_only_while_nothing_uses_them():
    pipeline = FakeDataPipeline()
    pipeline.add_product(name="Pro plan", sku="PRO-1", price="99.00")  # in "software"
    tools = _tools(pipeline)
    save, delete = tools["save_catalog_category"], tools["delete_catalog_category"]

    with pytest.raises(ToolInputError, match="e.g. 'office_chairs'"):
        await _run(save, {"key": "Office Chairs", "label": "Office chairs"})
    preview, added = await _run(save, {"key": "office_chairs", "label": "Office chairs", "parent_key": "apparel"})
    assert (preview["action"], preview["parent_key"], preview["before"]) == ("create", "apparel", None)
    assert pipeline._category("office_chairs") == {"key": "office_chairs", "label": "Office chairs", "parent_key": "apparel"}

    with pytest.raises(ToolInputError, match="'office_chairs' is inside 'apparel', so it can't be its parent"):
        await _run(save, {"key": "apparel", "label": "Apparel", "parent_key": "office_chairs"}, call_id="c2")
    preview, renamed = await _run(save, {"key": "office_chairs", "label": "Seating"}, call_id="c3")
    assert preview["before"] == {"label": "Office chairs", "parent_key": "apparel"} and preview["parent_key"] == "apparel"  # parent kept

    with pytest.raises(ToolInputError, match="is the parent of office_chairs"):
        await _run(delete, {"key": "apparel"})
    with pytest.raises(ToolInputError, match="used by 'Pro plan'"):
        await _run(delete, {"key": "software"})

    assert "is 'Office chairs' again" in await _undo(save, renamed)
    assert await _undo(save, added) == "removed category 'office_chairs'"
    assert "office_chairs" not in pipeline.categories

    preview, removed = await _run(delete, {"key": "apparel"}, call_id="c4")
    assert (preview["action"], preview["label"]) == ("delete", "Apparel") and "apparel" not in pipeline.categories
    await _undo(delete, removed)
    assert "apparel" in pipeline.categories


async def test_a_new_category_that_got_used_is_kept_on_undo():
    pipeline = FakeDataPipeline()
    tools = _tools(pipeline)
    _, added = await _run(tools["save_catalog_category"], {"key": "audio", "label": "Audio"})
    await _run(tools["create_catalog_item"], {"name": "Headset", "category": "audio"}, call_id="c2")
    with pytest.raises(ToolFailed, match="in use now"):
        await _undo(tools["save_catalog_category"], added)


async def test_stock_locations_are_added_changed_and_removed_only_if_never_used():
    pipeline = FakeDataPipeline()
    pipeline.locations[0]["address"] = {"priority_label": "Primary"}
    pipeline.add_product(name="Tee", sku="TEE-M", price="20.00", on_hand=6)
    tools = _tools(pipeline)
    create, update, delete = tools["create_stock_location"], tools["update_stock_location"], tools["delete_stock_location"]

    with pytest.raises(ToolInputError, match="already a stock location called"):
        await _run(create, {"name": "main WAREHOUSE"})
    preview, added = await _run(create, {"name": "Pop-up store", "type": "STORE", "priority": 5, "city": "Pokhara"})
    assert preview["location"] == {"name": "Pop-up store", "type": "STORE", "sellable": True, "priority": 5, "address": {"city": "Pokhara"}}
    popup = next(location for location in pipeline.locations if location["name"] == "Pop-up store")

    preview, changed = await _run(update, {"location": "main warehouse", "sellable": False, "city": "Kathmandu"}, call_id="c2")
    assert preview["changes"] == [
        {"field": "sellable", "before": True, "after": False},
        {"field": "city", "before": None, "after": "Kathmandu"},
    ]
    assert preview["warnings"] == ["its 6 units on hand will no longer count as available to sell or reserve"]
    [full] = [body for verb, path, body in pipeline.requests if verb == "PUT" and "/locations/" in path]
    assert full == {"name": "Main warehouse", "type": "WAREHOUSE", "sellable": False, "priority": 1,
                    "address": {"priority_label": "Primary", "city": "Kathmandu"}}  # every field, keeping what it had
    await _undo(update, changed)
    assert pipeline.locations[0]["sellable"] is True and pipeline.locations[0]["address"] == {"priority_label": "Primary"}

    with pytest.raises(ToolInputError, match="holds 6 units"):
        await _run(delete, {"location": "Main warehouse"})
    await _run(tools["record_stock_movement"], {"sku": "TEE-M", "type": "SHIPPED", "quantity": 6, "location": "Main warehouse", "to_location": "Pop-up store"}, call_id="c3")
    await _run(tools["record_stock_movement"], {"sku": "TEE-M", "type": "SHIPPED", "quantity": 6, "location": "Pop-up store", "to_location": "Main warehouse"}, call_id="c4")
    with pytest.raises(ToolInputError, match="has stock history"):
        await _run(delete, {"location": "Pop-up store"})
    with pytest.raises(ToolFailed, match="has held stock since"):
        await _undo(create, added)
    assert popup in pipeline.locations

    _, spare = await _run(create, {"name": "Spare room", "sellable": False}, call_id="c5")
    preview, removed = await _run(delete, {"location": "spare room"}, call_id="c6")
    assert preview["action"] == "delete" and all(location["name"] != "Spare room" for location in pipeline.locations)
    assert await _undo(delete, removed) == "added stock location 'Spare room' back"
    assert "already there" in await _undo(delete, removed)
    assert spare.ref_id  # the location it replaced had this id; the one added back gets a new one


async def test_viewers_cannot_set_up_the_catalog():
    pipeline = FakeDataPipeline()
    tools = _tools(pipeline, role="VIEWER")
    with pytest.raises(ToolAccessDenied, match="viewers"):
        await _run(tools["save_catalog_category"], {"key": "audio", "label": "Audio"})
    assert not [path for verb, path, _ in pipeline.requests if verb != "GET"]
