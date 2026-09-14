"""Product and service catalog reads over data-pipeline's catalog API (scoped by workspace).

Prices and discount bounds arrive as decimal strings (e.g. ``"199.99"``) and are passed on
unchanged so no rounding creeps in.
"""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from pydantic import Field, model_validator

from app.platform.data_pipeline import DataPipelineClient, DataPipelineError
from app.tools.adapters.catalog_lookup import CatalogLookup, ProductId, Sku, variant_options
from app.tools.adapters.common import as_dict, as_list, clip, pipeline_failure, plural
from app.tools.registry import ToolDefinition
from app.tools.types import ToolCategory, ToolInput, ToolInvocation, ToolKind, ToolOutput, ToolScope

_MAX_RESERVATION_ROWS = 1000  # hold rows read back when listing reservations (newest first)


class SearchCatalogArgs(ToolInput):
    query: str = Field(min_length=2, max_length=300, description="A need, product name, use case or SKU")
    max_results: int = Field(default=5, ge=1, le=10)
    include_inactive: bool = Field(default=False, description="Also return draft and retired items")


class CheckInventoryArgs(ToolInput):
    skus: list[str] = Field(min_length=1, max_length=20)
    quantity: int | None = Field(default=None, ge=1, le=1_000_000, description="Units needed of each SKU")


class ListCatalogItemsArgs(ToolInput):
    status: Literal["ACTIVE", "DRAFT", "RETIRED"] | None = Field(default=None, description="Only this status; default: active and draft items")
    category: str | None = Field(default=None, max_length=100, description="A category key (describe_catalog lists them)")
    type: Literal["PRODUCT", "SERVICE"] | None = None
    keywords: str | None = Field(default=None, min_length=2, max_length=200, description="Words in the name, description or sales fields")
    target_industry: str | None = Field(default=None, max_length=100)
    min_price: float | None = Field(default=None, ge=0, description="Items with a SKU at or above this price")
    max_price: float | None = Field(default=None, ge=0, description="Items with a SKU at or below this price")
    in_stock: bool = Field(default=False, description="Only items with a SKU available to sell (with the price filters, the same SKU)")
    location: str | None = Field(default=None, max_length=255, description="With in_stock: available at this location (name or id)")
    with_stock: bool = Field(default=False, description="Add each SKU's on-hand, reserved and available units")
    limit: int = Field(default=20, ge=1, le=50)
    offset: int = Field(default=0, ge=0, le=5000, description="Skip this many items (to see the next page)")

    @model_validator(mode="after")
    def _filters_fit(self) -> ListCatalogItemsArgs:
        if self.min_price is not None and self.max_price is not None and self.min_price > self.max_price:
            raise ValueError("min_price can't be above max_price")
        if self.location and not self.in_stock:
            raise ValueError("location only narrows in_stock; pass in_stock true with it")
        return self


class GetCatalogItemArgs(ToolInput):
    product_id: ProductId | None = Field(default=None, description="product_id from search_catalog or list_catalog_items")
    sku: Sku | None = Field(default=None, description="Or any SKU of the item")

    @model_validator(mode="after")
    def _one_way(self) -> GetCatalogItemArgs:
        if (self.product_id is None) == (self.sku is None):
            raise ValueError("pass either product_id or sku")
        return self


class DescribeCatalogArgs(ToolInput):
    pass


class ListReservationsArgs(ToolInput):
    sku: Sku | None = Field(default=None, description="Only this SKU")
    location: str | None = Field(default=None, max_length=255, description="Only holds at this location (name or id)")
    include_released: bool = Field(default=False, description="Also list reservations that were released")
    limit: int = Field(default=20, ge=1, le=50)


def catalog_tools(client: DataPipelineClient) -> list[ToolDefinition]:
    lookup = CatalogLookup(client)

    async def search_catalog(invocation: ToolInvocation) -> ToolOutput:
        args = invocation.args
        assert isinstance(args, SearchCatalogArgs)
        ctx = invocation.ctx
        try:
            # Ask for extra matches: drafts and retired items are dropped below unless requested.
            found = await client.search_products(ctx.user_id, ctx.tenant_id, args.query, limit=args.max_results * 2)
        except DataPipelineError as exc:
            raise pipeline_failure(exc) from exc
        items = [
            _item(product, match, include_inactive=args.include_inactive)
            for product, match in found
            if args.include_inactive or product.get("status") == "ACTIVE"
        ][: args.max_results]
        return ToolOutput(data={"items": items}, summary=f"{plural(len(items), 'catalog item')} matching '{args.query}'")

    async def check_inventory(invocation: ToolInvocation) -> ToolOutput:
        args = invocation.args
        assert isinstance(args, CheckInventoryArgs)
        ctx = invocation.ctx
        skus = list(dict.fromkeys(sku.strip() for sku in args.skus if sku.strip()))
        try:
            stock = await asyncio.gather(*(client.availability(ctx.user_id, ctx.tenant_id, sku) for sku in skus))
        except DataPipelineError as exc:
            raise pipeline_failure(exc) from exc
        items = [_stock(sku, entry, args.quantity) for sku, entry in zip(skus, stock, strict=True)]
        return ToolOutput(data={"items": items}, summary=_stock_summary(items, args.quantity))

    async def list_catalog_items(invocation: ToolInvocation) -> ToolOutput:
        args = invocation.args
        assert isinstance(args, ListCatalogItemsArgs)
        ctx = invocation.ctx
        filters: dict[str, Any] = {
            key: value
            for key, value in {
                "category": args.category,
                "type": args.type,
                "keywords": args.keywords,
                "target_industry": args.target_industry,
                "min_price": args.min_price,
                "max_price": args.max_price,
            }.items()
            if value is not None
        }
        if args.in_stock:
            filters["in_stock"] = "true"
        if args.location:
            filters["location_id"] = str((await lookup.location(ctx, args.location)).get("id"))
        statuses = [args.status] if args.status else ["ACTIVE", "DRAFT"]
        # Enough of each status to fill the page after merging them newest first.
        wanted = min(args.offset + args.limit + 1, 5000)
        try:
            pages = await asyncio.gather(
                *(client.list_products(ctx.user_id, ctx.tenant_id, filters | {"status": status, "limit": wanted}) for status in statuses)
            )
        except DataPipelineError as exc:
            raise pipeline_failure(exc) from exc
        merged = sorted((product for page in pages for product in page), key=lambda p: str(p.get("created_at") or ""), reverse=True)
        more = len(merged) > args.offset + args.limit
        products = merged[args.offset : args.offset + args.limit]
        stock: dict[str, dict[str, Any]] = {}
        if args.with_stock:
            skus = [str(v.get("sku")) for p in products for v in map(as_dict, as_list(p.get("variants")))]
            try:
                stock = await client.batch_availability(ctx.user_id, ctx.tenant_id, skus[:500])
            except DataPipelineError as exc:
                raise pipeline_failure(exc) from exc
        items = [_listed_item(product, stock if args.with_stock else None) for product in products]
        described = ", ".join(
            part
            for part in (
                (args.status or "active and draft").lower(),
                f"category {args.category}" if args.category else "",
                "in stock" if args.in_stock else "",
            )
            if part
        )
        more_note = f"; more after offset {args.offset + args.limit}" if more else ""
        return ToolOutput(
            data={"items": items, "more": more, "next_offset": args.offset + args.limit if more else None},
            summary=f"{plural(len(items), 'catalog item')} ({described}){more_note}",
        )

    async def get_catalog_item(invocation: ToolInvocation) -> ToolOutput:
        args = invocation.args
        assert isinstance(args, GetCatalogItemArgs)
        ctx = invocation.ctx
        product_id = args.product_id or str((await lookup.variant(ctx, str(args.sku))).get("product_id"))
        product = await lookup.product(ctx, product_id)
        variants = [as_dict(v) for v in as_list(product.get("variants"))]
        try:
            stock = await client.batch_availability(ctx.user_id, ctx.tenant_id, [str(v.get("sku")) for v in variants])
        except DataPipelineError as exc:
            raise pipeline_failure(exc) from exc
        skus = [
            {
                "sku": v.get("sku"),
                "status": v.get("status"),
                "price": v.get("price"),
                "currency": v.get("currency"),
                "barcode": v.get("barcode"),
                "weight": v.get("weight"),
                "options": variant_options(product, v),
                "stock": _levels(stock.get(str(v.get("sku")))),
            }
            for v in sorted(variants, key=lambda v: str(v.get("sku")))[:50]
        ]
        options = [
            {"name": option.get("name"), "values": [value.get("value") for value in sorted(map(as_dict, as_list(option.get("values"))), key=_position)]}
            for option in sorted(map(as_dict, as_list(product.get("options"))), key=_position)
        ]
        available = sum(int(as_dict(stock.get(str(v.get("sku")))).get("total_available") or 0) for v in variants)
        item = {
            "product_id": product.get("id"),
            "name": product.get("name"),
            "type": product.get("type"),
            "status": product.get("status"),
            "category": product.get("category"),
            "subcategory": product.get("subcategory"),
            "description": clip(product.get("description"), 2000),
            "value_proposition": clip(product.get("value_proposition"), 1000),
            "ideal_customer_profile": clip(product.get("ideal_customer_profile"), 1000),
            "keywords": as_list(product.get("keywords")),
            "use_cases": as_list(product.get("use_cases")),
            "target_industries": as_list(product.get("target_industries")),
            "beats_competitors": as_list(product.get("competitors_beats")),
            "sales_tags": as_list(product.get("sales_tags")),
            "discount_pct": {"min": product.get("min_discount_pct"), "max": product.get("max_discount_pct")},
            "options": options,
            "skus": skus,
            "updated_at": product.get("updated_at"),
        }
        return ToolOutput(
            data=item,
            summary=f"'{product.get('name')}' ({str(product.get('status')).lower()}): {plural(len(variants), 'SKU')}, {available} available to sell",
        )

    async def describe_catalog(invocation: ToolInvocation) -> ToolOutput:
        ctx = invocation.ctx
        try:
            described, locations = await asyncio.gather(
                client.describe_catalog(ctx.user_id, ctx.tenant_id), client.locations(ctx.user_id, ctx.tenant_id)
            )
        except DataPipelineError as exc:
            raise pipeline_failure(exc) from exc
        categories = [
            {"key": item.get("key"), "label": item.get("label"), "parent_key": item.get("parent_key")}
            for item in map(as_dict, as_list(as_dict(described).get("categories")))
        ]
        places = [
            {
                "location_id": item.get("id"),
                "name": item.get("name"),
                "type": item.get("type"),
                "sellable": item.get("sellable"),
                "priority": item.get("priority"),
                **{key: as_dict(item.get("address")).get(key) for key in ("city", "country") if as_dict(item.get("address")).get(key)},
            }
            for item in locations
        ]
        return ToolOutput(
            data={"categories": categories, "locations": places, "option_names": as_list(as_dict(described).get("option_types"))},
            summary=f"{len(categories)} {'category' if len(categories) == 1 else 'categories'} and {plural(len(places), 'stock location')}",
        )

    async def list_stock_reservations(invocation: ToolInvocation) -> ToolOutput:
        args = invocation.args
        assert isinstance(args, ListReservationsArgs)
        ctx = invocation.ctx
        filters: dict[str, Any] = {"reason": ["RESERVE", "RELEASE"], "limit": 200}
        if args.sku:
            filters["variant_id"] = str((await lookup.variant(ctx, args.sku)).get("id"))
        if args.location:
            filters["location_id"] = str((await lookup.location(ctx, args.location)).get("id"))
        rows: list[dict[str, Any]] = []
        complete = False
        try:
            while len(rows) < _MAX_RESERVATION_ROWS:
                page = as_dict(await client.stock_movements(ctx.user_id, ctx.tenant_id, filters | {"offset": len(rows)}))
                items = [as_dict(item) for item in as_list(page.get("items"))]
                rows.extend(items)
                if not items or len(rows) >= int(page.get("total") or 0):
                    complete = True
                    break
        except DataPipelineError as exc:
            raise pipeline_failure(exc) from exc
        reservations = _reservations(rows, str(ctx.user_id))
        shown = [item for item in reservations if args.include_released or item["status"] == "open"][: args.limit]
        open_count = sum(1 for item in reservations if item["status"] == "open")
        scope = f" of {args.sku}" if args.sku else ""
        return ToolOutput(
            data={"reservations": shown, "open": open_count, "complete": complete},
            summary=f"{plural(open_count, 'open reservation')}{scope}"
            + ("" if complete else f" among the latest {len(rows)} holds (older ones aren't listed)"),
        )

    read = {"kind": ToolKind.READ, "scope": ToolScope.READ, "category": ToolCategory.KNOWLEDGE}
    return [
        ToolDefinition(
            name="search_catalog",
            description=(
                "Search the workspace's product and service catalog. Returns matching items with description, "
                "value proposition, use cases, SKUs with prices, and the allowed discount range."
            ),
            input_model=SearchCatalogArgs,
            handler=search_catalog,
            timeout_seconds=45,  # ranking a large catalog takes a while
            **read,
        ),
        ToolDefinition(
            name="check_inventory",
            description=(
                "Check stock of catalog SKUs: units available to sell in total, and on hand, reserved and available "
                "at each location that holds any, optionally against a needed quantity."
            ),
            input_model=CheckInventoryArgs,
            handler=check_inventory,
            timeout_seconds=30,
            **read,
        ),
        ToolDefinition(
            name="list_catalog_items",
            description=(
                "List catalog items newest first, filtered by status (default active and draft; RETIRED lists retired "
                "ones), category, type, keywords, industry, price and stock. Each item has its SKUs and prices."
            ),
            input_model=ListCatalogItemsArgs,
            handler=list_catalog_items,
            timeout_seconds=30,
            **read,
        ),
        ToolDefinition(
            name="get_catalog_item",
            description=(
                "Everything about one catalog item, by product_id or any of its SKUs: details, sales fields, discount "
                "limits, options, and each SKU with price, barcode, weight, status and stock per location."
            ),
            input_model=GetCatalogItemArgs,
            handler=get_catalog_item,
            timeout_seconds=30,
            **read,
        ),
        ToolDefinition(
            name="describe_catalog",
            description="The catalog's setup: its categories (keys and labels), stock locations, and the option names items use.",
            input_model=DescribeCatalogArgs,
            handler=describe_catalog,
            timeout_seconds=20,
            **read,
        ),
        ToolDefinition(
            name="list_stock_reservations",
            description=(
                "Stock reservations newest first: reservation_id, SKU, quantity per location, when and whether you made "
                "it. Open ones by default; filter by SKU or location."
            ),
            input_model=ListReservationsArgs,
            handler=list_stock_reservations,
            timeout_seconds=30,
            **read,
        ),
    ]


def _item(product: dict[str, Any], match: dict[str, Any], *, include_inactive: bool) -> dict[str, Any]:
    option_names = {str(option.get("id")): option.get("name") for option in map(as_dict, as_list(product.get("options")))}
    variants = [
        {
            "sku": variant.get("sku"),
            "price": variant.get("price"),
            "currency": variant.get("currency"),
            "status": variant.get("status"),
            "options": {
                str(option_names.get(str(value.get("option_id")), "option")): value.get("value")
                for value in map(as_dict, as_list(variant.get("option_values")))
            },
        }
        for variant in map(as_dict, as_list(product.get("variants")))
        if include_inactive or variant.get("status") != "RETIRED"
    ]
    return {
        "product_id": product.get("id"),
        "name": product.get("name"),
        "type": product.get("type"),
        "category": product.get("category"),
        "status": product.get("status"),
        "description": clip(product.get("description"), 500),
        "value_proposition": clip(product.get("value_proposition"), 300),
        "use_cases": as_list(product.get("use_cases"))[:5],
        "target_industries": as_list(product.get("target_industries"))[:5],
        "beats_competitors": as_list(product.get("competitors_beats"))[:5],
        "discount_pct": {"min": product.get("min_discount_pct"), "max": product.get("max_discount_pct")},
        "variants": variants[:10],
        "match": {"score": match.get("score"), "why": match.get("rationale")},
    }


def _listed_item(product: dict[str, Any], stock: dict[str, dict[str, Any]] | None) -> dict[str, Any]:
    variants = sorted(map(as_dict, as_list(product.get("variants"))), key=lambda v: str(v.get("sku")))
    skus = []
    for variant in variants[:10]:
        sku = {
            "sku": variant.get("sku"),
            "price": variant.get("price"),
            "currency": variant.get("currency"),
            "status": variant.get("status"),
            "options": " / ".join(str(value.get("value")) for value in map(as_dict, as_list(variant.get("option_values")))) or None,
        }
        if stock is not None:
            entry = as_dict(stock.get(str(variant.get("sku"))))
            levels = [as_dict(level) for level in as_list(entry.get("by_location"))]
            sku |= {
                "on_hand": sum(_int(level.get("qty_on_hand")) for level in levels),
                "reserved": sum(_int(level.get("qty_reserved")) for level in levels),
                "available": _int(entry.get("total_available")),
            }
        skus.append(sku)
    return {
        "product_id": product.get("id"),
        "name": product.get("name"),
        "type": product.get("type"),
        "status": product.get("status"),
        "category": product.get("category"),
        "subcategory": product.get("subcategory"),
        "discount_pct": {"min": product.get("min_discount_pct"), "max": product.get("max_discount_pct")},
        "sku_count": len(variants),
        "skus": skus,
        "updated_at": product.get("updated_at"),
    }


def _levels(entry: Any) -> dict[str, Any]:
    """A SKU's stock: totals and each location that holds any."""
    entry = as_dict(entry)
    levels = [as_dict(level) for level in as_list(entry.get("by_location"))]
    return {
        "on_hand": sum(_int(level.get("qty_on_hand")) for level in levels),
        "reserved": sum(_int(level.get("qty_reserved")) for level in levels),
        "available": _int(entry.get("total_available")),
        "locations": [
            {
                "location": level.get("location_name"),
                "on_hand": _int(level.get("qty_on_hand")),
                "reserved": _int(level.get("qty_reserved")),
                "available": _int(level.get("qty_available")),
                "sellable": level.get("sellable"),
            }
            for level in levels
            if _int(level.get("qty_on_hand")) or _int(level.get("qty_reserved"))
        ][:10],
    }


def _reservations(rows: list[dict[str, Any]], user_id: str) -> list[dict[str, Any]]:
    """Hold rows (RESERVE and RELEASE, newest first) grouped into reservations, newest first."""
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        reservation_id = str(row.get("ref_id"))
        entry = grouped.setdefault(
            reservation_id,
            {"reservation_id": reservation_id, "sku": row.get("sku"), "product": row.get("product_name"), "held": [], "released": []},
        )
        entry["held" if row.get("reason") == "RESERVE" else "released"].append(row)
    reservations = []
    for entry in grouped.values():
        held, released = entry.pop("held"), entry.pop("released")
        if not held:
            continue  # its holds are older than the rows read
        reservations.append(
            entry
            | {
                "quantity": sum(_int(row.get("delta")) for row in held),
                "locations": [{"location": row.get("location_name"), "quantity": _int(row.get("delta"))} for row in held],
                "reserved_at": min(str(row.get("at")) for row in held),
                "reserved_by_you": all(str(row.get("created_by")) == user_id for row in held),
                "status": "released" if released else "open",
                "released_at": max(str(row.get("at")) for row in released) if released else None,
            }
        )
    return sorted(reservations, key=lambda item: item["reserved_at"], reverse=True)


def _stock(sku: str, entry: Any, quantity: int | None) -> dict[str, Any]:
    if not isinstance(entry, dict):
        return {"sku": sku, "found": False}
    available = _int(entry.get("total_available"))
    return {
        "sku": sku,
        "found": True,
        "available": available,
        "can_fulfill": available >= quantity if quantity else None,
        "locations": _levels(entry)["locations"],
    }


def _stock_summary(items: list[dict[str, Any]], quantity: int | None) -> str:
    found = [item for item in items if item["found"]]
    parts = []
    if found and quantity:
        parts.append(f"{sum(1 for item in found if item['can_fulfill'])} of {len(found)} can supply {quantity}")
    elif found:
        parts.append(f"{len(found)} found")
    if len(found) < len(items):
        parts.append(f"{len(items) - len(found)} not found")
    return f"Stock for {plural(len(items), 'SKU')}: " + ", ".join(parts)


def _position(item: dict[str, Any]) -> int:
    return _int(item.get("position"))


def _int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0
