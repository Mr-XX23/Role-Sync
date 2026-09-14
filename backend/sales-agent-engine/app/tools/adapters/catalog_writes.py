"""Catalog and inventory writes over data-pipeline's catalog API (shared by the workspace).

As decided for this build, the agent may create items (with their options and SKUs), update
details, discount limits and each SKU's price, currency, barcode, weight and status, record
stock movements and reserve or release stock; it retires items and never hard-deletes them.
Every change records what it replaced, so undo restores exactly what was there. Viewers of a
workspace can't change its catalog.

Stock follows data-pipeline's typed movements: what happened (received, sold, shipped, damaged,
lost, returned) is recorded, and the history can't be edited. Only workspace owners and admins
may replace a count (a count correction, with a note); the agent checks that before asking the
rep to approve, so a member is never shown an approval that is bound to be refused.

data-pipeline's variant upsert overwrites every field of a variant (barcode, currency,
weight, status, option values), so a SKU change always sends the variant's full current
state with only the changed fields replaced.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Literal

from pydantic import Field, model_validator

from app.core.context import AgentContext
from app.platform.data_pipeline import DataPipelineClient, DataPipelineError
from app.platform.workspace_client import WorkspaceDirectory
from app.tools.adapters.catalog_lookup import (
    CatalogLookup,
    OptionChoiceArgs,
    ProductId,
    Sku,
    Tag,
    money,
    same_number,
    variant_payload,
)
from app.tools.adapters.common import (
    as_dict,
    as_list,
    clip,
    pipeline_failure,
    pipeline_write_failure,
    plural,
    workspace_writer_required,
)
from app.tools.registry import ToolDefinition
from app.tools.types import (
    ToolAccessDenied,
    ToolCategory,
    ToolFailed,
    ToolInput,
    ToolInputError,
    ToolInvocation,
    ToolKind,
    ToolOutput,
    ToolScope,
    UndoInvocation,
    UndoPlan,
)

_TEXT_FIELDS = ("name", "type", "category", "subcategory", "description", "value_proposition", "ideal_customer_profile", "status")
_LIST_FIELDS = ("keywords", "use_cases", "target_industries", "competitors_beats", "sales_tags")
_NUMBER_FIELDS = ("min_discount_pct", "max_discount_pct")
_SKU_FIELDS = ("price", "currency", "barcode", "weight", "status")

MovementType = Literal["RECEIVED", "SOLD", "SHIPPED", "DAMAGED", "LOST", "RETURNED"]
HistoryType = Literal["RECEIVED", "SOLD", "SHIPPED", "DAMAGED", "LOST", "RETURNED", "CORRECTION"]
_MOVEMENT_WORDS = {
    "RECEIVED": "received",
    "SOLD": "sold",
    "SHIPPED": "shipped",
    "DAMAGED": "written off as damaged",
    "LOST": "written off as lost",
    "RETURNED": "returned",
}
_TAKES_AVAILABLE = frozenset({"SOLD", "SHIPPED", "DAMAGED", "LOST"})  # these can't use reserved units
# How each kind of movement is stored in data-pipeline's ledger (for history filters).
_LEDGER_REASONS = {
    "RECEIVED": ("RESTOCK",),
    "SOLD": ("SALE",),
    "SHIPPED": ("TRANSFER_OUT", "TRANSFER_IN"),
    "DAMAGED": ("DAMAGE",),
    "LOST": ("LOST",),
    "RETURNED": ("RETURN",),
    "CORRECTION": ("ADJUST",),
}
_ADMIN_ROLES = frozenset({"OWNER", "ADMIN"})


class NewVariantArgs(ToolInput):
    sku: Sku
    price: float = Field(ge=0, le=1_000_000_000)
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    barcode: str | None = Field(default=None, max_length=100)
    weight: float | None = Field(default=None, ge=0, le=1_000_000)
    options: list[OptionChoiceArgs] = Field(
        default_factory=list,
        max_length=5,
        description="This SKU's option values, e.g. Size M and Color Black. Every SKU of an item names the same options",
    )

    @model_validator(mode="after")
    def _one_value_per_option(self) -> NewVariantArgs:
        names = [choice.name.lower() for choice in self.options]
        if len(set(names)) != len(names):
            raise ValueError(f"SKU {self.sku} names an option more than once")
        return self


def check_same_options(variants: list[NewVariantArgs]) -> None:
    """Every SKU names the same options, and no two SKUs have the same values (``ValueError``)."""
    if not variants:
        return
    first = sorted(choice.name.lower() for choice in variants[0].options)
    for item in variants[1:]:
        if sorted(choice.name.lower() for choice in item.options) != first:
            raise ValueError(
                f"every SKU must name the same options ({variants[0].sku}: {_names(variants[0])}; {item.sku}: {_names(item)})"
            )
    if first:
        combinations = [frozenset((c.name.lower(), c.value.lower()) for c in item.options) for item in variants]
        if len(set(combinations)) != len(combinations):
            raise ValueError("two SKUs have the same option values; each SKU needs its own combination")


def _names(item: NewVariantArgs) -> str:
    return ", ".join(choice.name for choice in item.options) or "no options"


class CreateCatalogItemArgs(ToolInput):
    name: str = Field(min_length=3, max_length=255)
    type: Literal["PRODUCT", "SERVICE"] = "PRODUCT"
    category: str = Field(min_length=1, max_length=100, description="An existing category key of the workspace catalog")
    subcategory: str | None = Field(default=None, max_length=100)
    status: Literal["DRAFT", "ACTIVE"] = "DRAFT"
    description: str | None = Field(default=None, max_length=10_000)
    value_proposition: str | None = Field(default=None, max_length=5000)
    ideal_customer_profile: str | None = Field(default=None, max_length=5000)
    keywords: list[Tag] = Field(default_factory=list, max_length=30)
    use_cases: list[Tag] = Field(default_factory=list, max_length=30)
    target_industries: list[Tag] = Field(default_factory=list, max_length=30)
    competitors_beats: list[Tag] = Field(default_factory=list, max_length=30)
    sales_tags: list[Tag] = Field(default_factory=list, max_length=30)
    min_discount_pct: float = Field(default=0, ge=0, le=100)
    max_discount_pct: float = Field(default=0, ge=0, le=100, description="The largest discount reps may give")
    variants: list[NewVariantArgs] = Field(default_factory=list, max_length=50, description="Sellable SKUs with prices")

    @model_validator(mode="after")
    def _discounts(self) -> CreateCatalogItemArgs:
        if self.min_discount_pct > self.max_discount_pct:
            raise ValueError("min_discount_pct can't be above max_discount_pct")
        if len({variant.sku for variant in self.variants}) != len(self.variants):
            raise ValueError("each SKU may appear only once")
        check_same_options(self.variants)
        return self


class SkuChangeArgs(ToolInput):
    sku: Sku
    price: float | None = Field(default=None, ge=0, le=1_000_000_000)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    barcode: str | None = Field(default=None, max_length=100, description="Empty text removes the barcode")
    weight: float | None = Field(default=None, ge=0, le=1_000_000)
    status: Literal["ACTIVE", "RETIRED"] | None = Field(
        default=None, description="RETIRED stops this one SKU being sold or quoted; ACTIVE sells it again"
    )

    @model_validator(mode="after")
    def _changes_something(self) -> SkuChangeArgs:
        if all(getattr(self, name) is None for name in _SKU_FIELDS):
            raise ValueError(f"say what to change about SKU {self.sku}")
        return self


class UpdateCatalogItemArgs(ToolInput):
    product_id: ProductId = Field(description="product_id from search_catalog or list_catalog_items")
    name: str | None = Field(default=None, min_length=3, max_length=255)
    type: Literal["PRODUCT", "SERVICE"] | None = None
    category: str | None = Field(default=None, min_length=1, max_length=100)
    subcategory: str | None = Field(default=None, max_length=100)
    status: Literal["DRAFT", "ACTIVE"] | None = None
    description: str | None = Field(default=None, max_length=10_000)
    value_proposition: str | None = Field(default=None, max_length=5000)
    ideal_customer_profile: str | None = Field(default=None, max_length=5000)
    keywords: list[Tag] | None = Field(default=None, max_length=30)
    use_cases: list[Tag] | None = Field(default=None, max_length=30)
    target_industries: list[Tag] | None = Field(default=None, max_length=30)
    competitors_beats: list[Tag] | None = Field(default=None, max_length=30)
    sales_tags: list[Tag] | None = Field(default=None, max_length=30)
    min_discount_pct: float | None = Field(default=None, ge=0, le=100)
    max_discount_pct: float | None = Field(default=None, ge=0, le=100)
    sku_changes: list[SkuChangeArgs] = Field(
        default_factory=list,
        max_length=50,
        description="Changes to this item's SKUs: price, currency, barcode, weight, or status",
    )

    @model_validator(mode="before")
    @classmethod
    def _prices_are_sku_changes(cls, data: Any) -> Any:
        # Approvals saved before sku_changes existed list new prices as ``prices``.
        if isinstance(data, dict) and "prices" in data:
            data = dict(data)
            data["sku_changes"] = [*(data.get("sku_changes") or []), *(data.pop("prices") or [])]
        return data

    @model_validator(mode="after")
    def _each_sku_once(self) -> UpdateCatalogItemArgs:
        skus = [change.sku for change in self.sku_changes]
        if len(set(skus)) != len(skus):
            raise ValueError("each SKU may appear only once in sku_changes")
        return self


class StockMovementArgs(ToolInput):
    sku: Sku
    type: MovementType = Field(
        description=(
            "What happened: RECEIVED (new stock arrived), SOLD (sold to a customer), SHIPPED (moved to another "
            "location), DAMAGED or LOST (written off), RETURNED (a customer sent it back)"
        )
    )
    quantity: int = Field(ge=1, le=1_000_000_000)
    location: str | None = Field(
        default=None,
        max_length=255,
        description="Where it happened (location name or id); for SHIPPED, where the stock leaves. Needed if there are several",
    )
    to_location: str | None = Field(default=None, max_length=255, description="SHIPPED only: where the stock arrives")
    resellable: bool = Field(default=True, description="RETURNED only: whether the returned units can be sold again")
    counterparty: str | None = Field(default=None, max_length=255, description="The customer or supplier")
    reference: str | None = Field(default=None, max_length=255, description="Order, invoice, PO or return number")
    note: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _fits_the_type(self) -> StockMovementArgs:
        if self.type == "SHIPPED" and not self.to_location:
            raise ValueError("SHIPPED needs to_location: where the stock arrives")
        if self.type != "SHIPPED" and self.to_location:
            raise ValueError("to_location is only for SHIPPED")
        if self.type != "RETURNED" and not self.resellable:
            raise ValueError("resellable is only for RETURNED")
        return self


class CorrectStockCountArgs(ToolInput):
    sku: Sku
    counted_quantity: int = Field(ge=0, le=1_000_000_000, description="How many units are actually there")
    expected_on_hand: int = Field(
        ge=0,
        description="The on-hand quantity check_inventory showed at this location just before; if stock has changed since, nothing is changed",
    )
    location: str | None = Field(default=None, max_length=255, description="Location name or id; needed if there are several")
    note: str = Field(min_length=3, max_length=1000, description="Why the count is being corrected")


class StockHistoryArgs(ToolInput):
    sku: Sku | None = Field(default=None, description="Only this SKU; leave out for the whole catalog")
    location: str | None = Field(default=None, max_length=255, description="Only this location (name or id)")
    types: list[HistoryType] = Field(default_factory=list, max_length=7, description="Only these kinds of movement")
    since: date | None = Field(default=None, description="From this day, inclusive")
    until: date | None = Field(default=None, description="Up to this day, inclusive")
    limit: int = Field(default=20, ge=1, le=100)


class ReserveStockArgs(ToolInput):
    sku: Sku
    quantity: int = Field(ge=1, le=1_000_000)
    location: str | None = Field(default=None, max_length=255, description="Reserve at this location; default: by priority")


class ReleaseStockArgs(ToolInput):
    reservation_id: ProductId = Field(description="reservation_id from reserve_stock, create_quote or list_stock_reservations")


class RetireCatalogItemArgs(ToolInput):
    product_id: ProductId


@dataclass
class _UpdatePlan:
    current: dict[str, Any]
    changes: dict[str, Any]  # product fields: new values
    previous: dict[str, Any]  # product fields: the values they replace
    payloads: list[dict[str, Any]]  # full variant states to upsert
    sku_changes: list[dict[str, Any]]  # {sku, field, before, after}, for the reviewer
    sku_undo: list[dict[str, Any]]  # {sku, fields: the values they replace}
    warnings: list[str] = field(default_factory=list)


def option_axes(variants: list[NewVariantArgs]) -> list[tuple[str, list[str]]]:
    """The options new SKUs name, in the order they first appear: ``[(name, [values])]``."""
    axes: dict[str, tuple[str, dict[str, str]]] = {}
    for item in variants:
        for choice in item.options:
            name, values = axes.setdefault(choice.name.lower(), (choice.name, {}))
            values.setdefault(choice.value.lower(), choice.value)
    return [(name, list(values.values())) for name, values in axes.values()]


def option_value_ids(options: list[Any]) -> dict[tuple[str, str], str]:
    """(option name, value), both lower-cased → option value id, from data-pipeline's options."""
    return {
        (str(option.get("name")).lower(), str(value.get("value")).lower()): str(value.get("id"))
        for option in map(as_dict, options)
        for value in map(as_dict, as_list(option.get("values")))
    }


def catalog_write_tools(client: DataPipelineClient, directory: WorkspaceDirectory) -> list[ToolDefinition]:
    writer = workspace_writer_required(directory, "the catalog")
    lookup = CatalogLookup(client)
    product, variant, check_category = lookup.product, lookup.variant, lookup.check_category
    location, stock_at = lookup.location, lookup.stock_at

    # ------------------------------------------------------------------ create
    async def validate_new_item(ctx: AgentContext, args: CreateCatalogItemArgs) -> None:
        await check_category(ctx, args.category)
        taken = [item.sku for item in args.variants if await lookup.sku_in_use(ctx, item.sku)]
        if taken:
            raise ToolInputError(f"SKU already in use in this catalog: {', '.join(taken)}")

    async def create_catalog_item(invocation: ToolInvocation) -> ToolOutput:
        args = invocation.args
        assert isinstance(args, CreateCatalogItemArgs)
        ctx = invocation.ctx
        await validate_new_item(ctx, args)
        payload = args.model_dump(mode="json", exclude={"variants"})
        payload |= {"min_discount_pct": money(args.min_discount_pct), "max_discount_pct": money(args.max_discount_pct)}
        axes = option_axes(args.variants)
        if axes:
            payload["options"] = [
                {"name": name, "position": index, "values": [{"value": value, "position": order} for order, value in enumerate(values)]}
                for index, (name, values) in enumerate(axes)
            ]
        try:
            created = await client.create_product(ctx.user_id, ctx.tenant_id, payload)
        except DataPipelineError as exc:
            raise pipeline_write_failure(exc) from exc
        product_id = str(created.get("id"))
        undo = UndoPlan(args={"product_id": product_id, "name": args.name}, label=f"Retire the new catalog item '{args.name}'")
        if args.variants:
            ids = option_value_ids(as_list(created.get("options")))
            try:
                variants = [new_variant_payload(item, ids) for item in args.variants]
                await client.upsert_variants(ctx.user_id, ctx.tenant_id, product_id, variants)
            except (DataPipelineError, KeyError) as exc:
                # Don't leave a half-made item behind: retire it, then report the failure.
                reason = f"option value {exc} is missing" if isinstance(exc, KeyError) else str(exc)
                try:
                    await client.retire_product(ctx.user_id, ctx.tenant_id, product_id)
                    cleanup = "the item was retired again"
                except DataPipelineError:
                    cleanup = f"retiring the item {product_id} also failed"
                raise ToolFailed(f"the item was created but its SKUs could not be added ({reason}); {cleanup}") from exc
        options = f" in {' × '.join(f'{len(values)} {name}' for name, values in axes)}" if axes else ""
        return ToolOutput(
            data={"product_id": product_id, "name": args.name, "status": args.status, "skus": [v.sku for v in args.variants]},
            summary=f"Catalog item '{args.name}' created as {args.status} with {plural(len(args.variants), 'SKU')}{options}",
            ref_id=product_id,
            undo=undo,
        )

    async def create_preview(ctx: AgentContext, args: ToolInput) -> dict[str, Any]:
        assert isinstance(args, CreateCatalogItemArgs)
        await validate_new_item(ctx, args)
        return {
            "kind": "catalog_item",
            "item": args.model_dump(mode="json", exclude={"variants"}),
            "options": [{"name": name, "values": values} for name, values in option_axes(args.variants)],
            "variants": [item.model_dump(mode="json") | {"price": money(item.price)} for item in args.variants],
        }

    async def retire_created(invocation: UndoInvocation) -> str:
        return await retire(invocation.ctx, str(invocation.args["product_id"]), str(invocation.args.get("name") or "item"))

    # ------------------------------------------------------------------ update
    async def plan_update(ctx: AgentContext, args: UpdateCatalogItemArgs) -> _UpdatePlan:
        current = await product(ctx, args.product_id)
        name = str(current.get("name"))
        retired = current.get("status") == "RETIRED"
        if retired and (args.status or any(change.status == "ACTIVE" for change in args.sku_changes)):
            raise ToolInputError(f"'{name}' is retired; bring it back with restore_catalog_item first")
        changes: dict[str, Any] = {}
        previous: dict[str, Any] = {}
        for field_name in (*_TEXT_FIELDS, *_LIST_FIELDS, *_NUMBER_FIELDS):
            value = getattr(args, field_name)
            if value is None:
                continue
            before = current.get(field_name)
            if field_name in _NUMBER_FIELDS:
                value = money(value)
                if same_number(before, value):
                    continue
            elif value == before:
                continue
            changes[field_name], previous[field_name] = value, before
        lowest = Decimal(str(changes.get("min_discount_pct", current.get("min_discount_pct") or 0)))
        highest = Decimal(str(changes.get("max_discount_pct", current.get("max_discount_pct") or 0)))
        if lowest > highest:
            raise ToolInputError(f"the minimum discount ({lowest}%) can't be above the maximum ({highest}%)")
        if "category" in changes:
            await check_category(ctx, changes["category"])

        variants_by_sku = {str(v.get("sku")): as_dict(v) for v in as_list(current.get("variants"))}
        plan = _UpdatePlan(current, changes, previous, [], [], [])
        for change in args.sku_changes:
            existing = variants_by_sku.get(change.sku)
            if existing is None:
                raise ToolInputError(f"'{name}' has no SKU '{change.sku}' (SKUs: {', '.join(variants_by_sku) or 'none'})")
            overrides, replaced = _sku_overrides(existing, change)
            if not overrides:
                continue
            plan.payloads.append(variant_payload(existing, **overrides))
            plan.sku_undo.append({"sku": change.sku, "fields": replaced})
            for field_name, after in overrides.items():
                row = {"sku": change.sku, "field": field_name, "before": replaced[field_name], "after": after}
                if field_name == "price":
                    row["currency"] = overrides.get("currency") or existing.get("currency")
                plan.sku_changes.append(row)
            existing.update(overrides)  # the item as it will be, for the warnings below
        if not changes and not plan.payloads:
            raise ToolInputError("nothing to change: the item already has these values")

        changed_fields = {row["field"] for row in plan.sku_changes}
        active = [v for v in variants_by_sku.values() if v.get("status") == "ACTIVE"]
        if "status" in changed_fields and not active and changes.get("status", current.get("status")) == "ACTIVE":
            plan.warnings.append(f"'{name}' will have no active SKU left, so it can't be sold or quoted until one is reactivated")
        currencies = sorted({str(v.get("currency")) for v in active})
        if changed_fields & {"currency", "status"} and len(currencies) > 1:
            plan.warnings.append(f"Its active SKUs will be priced in {', '.join(currencies)}; a quote can't mix currencies")
        return plan

    async def update_catalog_item(invocation: ToolInvocation) -> ToolOutput:
        args = invocation.args
        assert isinstance(args, UpdateCatalogItemArgs)
        ctx = invocation.ctx
        plan = await plan_update(ctx, args)
        name = str(plan.changes.get("name") or plan.current.get("name"))
        if plan.changes:
            try:
                await client.update_product(ctx.user_id, ctx.tenant_id, args.product_id, plan.changes)
            except DataPipelineError as exc:
                raise pipeline_write_failure(exc) from exc
        if plan.payloads:
            try:
                await client.upsert_variants(ctx.user_id, ctx.tenant_id, args.product_id, plan.payloads)
            except DataPipelineError as exc:
                if plan.changes:
                    try:
                        await client.update_product(ctx.user_id, ctx.tenant_id, args.product_id, plan.previous)
                        cleanup = "the other changes were reverted"
                    except DataPipelineError:
                        cleanup = "reverting the other changes also failed"
                    raise ToolFailed(f"the SKUs could not be changed ({exc}); {cleanup}") from exc
                raise pipeline_write_failure(exc) from exc
        described = [f"{field_name} changed" for field_name in plan.changes] + [
            f"{row['sku']} {row['field']} {row['before']} → {row['after']}" for row in plan.sku_changes
        ]
        changed_names = [*plan.changes, *(f"{item['sku']} {', '.join(item['fields'])}" for item in plan.sku_undo)]
        return ToolOutput(
            data={
                "product_id": args.product_id,
                "name": name,
                "changes": [{"field": f, "before": plan.previous[f], "after": value} for f, value in plan.changes.items()],
                "sku_changes": plan.sku_changes,
                "warnings": plan.warnings,
            },
            summary=f"Catalog item '{name}' updated: " + "; ".join(described),
            ref_id=args.product_id,
            undo=UndoPlan(
                args={"product_id": args.product_id, "fields": plan.previous, "skus": plan.sku_undo},
                label=f"Restore the previous values of '{name}' ({', '.join(changed_names)})",
            ),
        )

    async def update_preview(ctx: AgentContext, args: ToolInput) -> dict[str, Any]:
        assert isinstance(args, UpdateCatalogItemArgs)
        plan = await plan_update(ctx, args)
        return {
            "kind": "catalog_update",
            "product_id": args.product_id,
            "name": plan.current.get("name"),
            "changes": [{"field": f, "before": plan.previous[f], "after": value} for f, value in plan.changes.items()],
            "sku_changes": plan.sku_changes,
            "warnings": plan.warnings,
        }

    async def restore_values(invocation: UndoInvocation) -> str:
        ctx = invocation.ctx
        product_id = str(invocation.args["product_id"])
        fields = as_dict(invocation.args.get("fields"))
        skus = [as_dict(item) for item in as_list(invocation.args.get("skus"))]
        # Undo records written before per-SKU changes existed list old prices only.
        skus += [{"sku": item.get("sku"), "fields": {"price": item.get("price")}} for item in map(as_dict, as_list(invocation.args.get("prices")))]
        try:
            if fields:
                await client.update_product(ctx.user_id, ctx.tenant_id, product_id, fields)
            if skus:
                current = await product(ctx, product_id)
                variants_by_sku = {str(v.get("sku")): as_dict(v) for v in as_list(current.get("variants"))}
                payloads = [
                    variant_payload(variants_by_sku[str(item["sku"])], **as_dict(item.get("fields")))
                    for item in skus
                    if str(item.get("sku")) in variants_by_sku
                ]
                if payloads:
                    await client.upsert_variants(ctx.user_id, ctx.tenant_id, product_id, payloads)
        except DataPipelineError as exc:
            raise pipeline_failure(exc) from exc
        restored = len(fields) + sum(len(as_dict(item.get("fields"))) for item in skus)
        return f"restored {plural(restored, 'previous value')} of catalog item {product_id}"

    # ------------------------------------------------------------------ stock
    async def owner_or_admin(ctx: AgentContext, args: ToolInput) -> None:
        role = await directory.role_in(ctx.user_id, ctx.tenant_id)
        if role is None:
            raise ToolAccessDenied("you are no longer a member of this workspace")
        if role not in _ADMIN_ROLES:
            raise ToolAccessDenied(
                "only workspace owners and admins can correct a stock count; record what happened instead "
                "(received, sold, shipped, damaged, lost or returned)"
            )

    async def plan_movement(ctx: AgentContext, args: StockMovementArgs) -> dict[str, Any]:
        found = await variant(ctx, args.sku)
        source = await location(ctx, args.location)
        target = await location(ctx, args.to_location) if args.type == "SHIPPED" else None
        if target is not None and str(target.get("id")) == str(source.get("id")):
            raise ToolInputError("stock can't be shipped to the location it is already at")
        if args.type == "SOLD" and source.get("sellable") is False:
            raise ToolInputError(
                f"{source.get('name')} isn't a sellable location, so nothing can be sold from it; ship the stock to a sellable location first"
            )
        on_hand, reserved = await stock_at(ctx, args.sku, str(source.get("id")))
        available = max(0, on_hand - reserved)
        if args.type in _TAKES_AVAILABLE and args.quantity > available:
            held = f", {reserved} reserved" if reserved else ""
            raise ToolInputError(
                f"only {available} × {args.sku} available at {source.get('name')} ({on_hand} on hand{held}); "
                f"can't record {args.quantity} as {args.type.lower()}"
            )
        change = {"RECEIVED": args.quantity, "RETURNED": args.quantity if args.resellable else 0}.get(args.type, -args.quantity)
        levels = [{"location": source.get("name"), "before": on_hand, "after": on_hand + change}]
        if target is not None:
            arriving, _ = await stock_at(ctx, args.sku, str(target.get("id")))
            levels.append({"location": target.get("name"), "before": arriving, "after": arriving + args.quantity})
        return {"variant": found, "source": source, "target": target, "levels": levels}

    async def record_stock_movement(invocation: ToolInvocation) -> ToolOutput:
        args = invocation.args
        assert isinstance(args, StockMovementArgs)
        ctx = invocation.ctx
        plan = await plan_movement(ctx, args)
        source, target = plan["source"], plan["target"]
        payload: dict[str, Any] = {
            "type": args.type,
            "variant_id": str(plan["variant"].get("id")),
            "location_id": str(source.get("id")),
            "qty": args.quantity,
            "note": args.note or "Recorded by the sales agent",
        }
        if target is not None:
            payload["to_location_id"] = str(target.get("id"))
        if args.type == "RETURNED":
            payload["resellable"] = args.resellable
        if args.counterparty:
            payload["counterparty"] = args.counterparty
        if args.reference:
            payload["reference"] = args.reference
        try:
            recorded = as_dict(await client.record_stock_movement(ctx.user_id, ctx.tenant_id, payload))
        except DataPipelineError as exc:
            raise pipeline_write_failure(exc) from exc
        levels = [
            {"location": level.get("location_name"), "before": level.get("qty_on_hand_before"), "after": level.get("qty_on_hand")}
            for level in map(as_dict, as_list(recorded.get("levels")))
        ] or plan["levels"]
        moved = ", ".join(f"{level['location']} {level['before']} → {level['after']}" for level in levels)
        where = f" from {source.get('name')} to {target.get('name')}" if target is not None else f" at {source.get('name')}"
        written_off = " and written off" if args.type == "RETURNED" and not args.resellable else ""
        ref_id = recorded.get("ref_id")
        undo = None
        if target is not None:
            undo = UndoPlan(
                args={
                    "variant_id": payload["variant_id"],
                    "sku": args.sku,
                    "quantity": args.quantity,
                    "from_location_id": payload["to_location_id"],
                    "from_name": target.get("name"),
                    "to_location_id": payload["location_id"],
                    "to_name": source.get("name"),
                    "reference": f"Undo of shipment {ref_id}"[:255],
                },
                label=f"Ship the {args.quantity} × {args.sku} back from {target.get('name')} to {source.get('name')}",
            )
        return ToolOutput(
            data={"type": args.type, "sku": args.sku, "quantity": args.quantity, "levels": levels, "ref_id": ref_id},
            summary=f"Recorded {args.quantity} × {args.sku} {_MOVEMENT_WORDS[args.type]}{written_off}{where} (on hand: {moved})",
            ref_id=str(ref_id) if ref_id else None,
            undo=undo,
        )

    async def movement_preview(ctx: AgentContext, args: ToolInput) -> dict[str, Any]:
        assert isinstance(args, StockMovementArgs)
        plan = await plan_movement(ctx, args)
        return {
            "kind": "stock_movement",
            "type": args.type,
            "sku": args.sku,
            "quantity": args.quantity,
            "levels": plan["levels"],
            "resellable": args.resellable if args.type == "RETURNED" else None,
            "counterparty": args.counterparty,
            "reference": args.reference,
            "note": args.note,
            "undoable": args.type == "SHIPPED",
        }

    async def ship_back(invocation: UndoInvocation) -> str:
        ctx = invocation.ctx
        undo = invocation.args
        reference = str(undo["reference"])
        # Undo steps are retried when no answer comes back, so check the return wasn't recorded already.
        try:
            recent = await client.stock_movements(
                ctx.user_id,
                ctx.tenant_id,
                {"variant_id": str(undo["variant_id"]), "location_id": str(undo["from_location_id"]), "reason": ["TRANSFER_OUT"], "limit": 50},
            )
        except DataPipelineError as exc:
            raise pipeline_failure(exc) from exc
        if any(as_dict(item).get("reference") == reference for item in as_list(as_dict(recent).get("items"))):
            return f"the {undo['quantity']} × {undo.get('sku')} were already shipped back to {undo.get('to_name')}"
        payload = {
            "type": "SHIPPED",
            "variant_id": str(undo["variant_id"]),
            "location_id": str(undo["from_location_id"]),
            "to_location_id": str(undo["to_location_id"]),
            "qty": int(undo["quantity"]),
            "reference": reference,
            "note": "Undo of a shipment recorded by the sales agent",
        }
        try:
            await client.record_stock_movement(ctx.user_id, ctx.tenant_id, payload)
        except DataPipelineError as exc:
            raise pipeline_failure(exc) from exc
        return f"shipped {undo['quantity']} × {undo.get('sku')} back from {undo.get('from_name')} to {undo.get('to_name')}"

    async def plan_correction(ctx: AgentContext, args: CorrectStockCountArgs) -> tuple[dict[str, Any], dict[str, Any], int, int]:
        found = await variant(ctx, args.sku)
        place = await location(ctx, args.location)
        on_hand, reserved = await stock_at(ctx, args.sku, str(place.get("id")))
        if args.expected_on_hand != on_hand:
            raise ToolInputError(
                f"{args.sku} now has {on_hand} on hand at {place.get('name')}, not {args.expected_on_hand}; check the stock again before correcting it"
            )
        if args.counted_quantity < reserved:
            raise ToolInputError(f"{reserved} units of {args.sku} are reserved at {place.get('name')}; the count can't go below that")
        if args.counted_quantity == on_hand:
            raise ToolInputError(f"{args.sku} already has {on_hand} on hand at {place.get('name')}")
        return found, place, on_hand, reserved

    async def correct_stock_count(invocation: ToolInvocation) -> ToolOutput:
        args = invocation.args
        assert isinstance(args, CorrectStockCountArgs)
        ctx = invocation.ctx
        found, place, before, _ = await plan_correction(ctx, args)
        payload = {
            "type": "COUNT_CORRECTION",
            "variant_id": str(found.get("id")),
            "location_id": str(place.get("id")),
            "qty": args.counted_quantity,
            "expected_on_hand": args.expected_on_hand,
            "note": args.note,
        }
        try:
            await client.record_stock_movement(ctx.user_id, ctx.tenant_id, payload)
        except DataPipelineError as exc:
            if exc.status == 409:
                raise ToolFailed(f"the stock changed before the correction was saved, so nothing was changed ({exc})") from exc
            raise pipeline_write_failure(exc) from exc
        where = str(place.get("name"))
        return ToolOutput(
            data={"sku": args.sku, "location": where, "before": before, "after": args.counted_quantity},
            summary=f"Count of {args.sku} at {where} corrected from {before} to {args.counted_quantity}",
            undo=UndoPlan(
                args={
                    "variant_id": payload["variant_id"],
                    "location_id": payload["location_id"],
                    "location": where,
                    "sku": args.sku,
                    "quantity": before,
                    "applied": args.counted_quantity,
                },
                label=f"Set the count of {args.sku} at {where} back to {before}",
            ),
        )

    async def correction_preview(ctx: AgentContext, args: ToolInput) -> dict[str, Any]:
        assert isinstance(args, CorrectStockCountArgs)
        _, place, before, reserved = await plan_correction(ctx, args)
        return {
            "kind": "stock_change",
            "sku": args.sku,
            "location": place.get("name"),
            "before": before,
            "after": args.counted_quantity,
            "reserved": reserved,
            "reason": "COUNT CORRECTION",
            "note": args.note,
        }

    async def restore_count(invocation: UndoInvocation) -> str:
        ctx = invocation.ctx
        undo = invocation.args
        sku, quantity = str(undo.get("sku")), int(undo["quantity"])
        payload = {
            "type": "COUNT_CORRECTION",
            "variant_id": str(undo["variant_id"]),
            "location_id": str(undo["location_id"]),
            "qty": quantity,
            "expected_on_hand": int(undo["applied"]),
            "note": "Undo of a count correction made by the sales agent",
        }
        try:
            await client.record_stock_movement(ctx.user_id, ctx.tenant_id, payload)
        except DataPipelineError as exc:
            if exc.status != 409:
                raise pipeline_failure(exc) from exc
            on_hand, _ = await stock_at(ctx, sku, str(undo["location_id"]))
            if on_hand == quantity:
                return f"the count of {sku} at {undo.get('location')} was already back at {quantity}"
            raise ToolFailed(f"the stock of {sku} has changed since the correction (now {on_hand}), so it was left as it is") from exc
        return f"count of {sku} at {undo.get('location')} set back to {quantity}"

    async def stock_history(invocation: ToolInvocation) -> ToolOutput:
        args = invocation.args
        assert isinstance(args, StockHistoryArgs)
        ctx = invocation.ctx
        filters: dict[str, Any] = {}
        if args.sku:
            filters["variant_id"] = str((await variant(ctx, args.sku)).get("id"))
        if args.location:
            filters["location_id"] = str((await location(ctx, args.location)).get("id"))
        if args.since:
            filters["date_from"] = datetime.combine(args.since, time.min, tzinfo=UTC).isoformat()
        if args.until:
            filters["date_to"] = datetime.combine(args.until + timedelta(days=1), time.min, tzinfo=UTC).isoformat()
        wanted = {"limit": args.limit, **filters}
        if args.types:
            wanted["reason"] = sorted({reason for kind in args.types for reason in _LEDGER_REASONS[kind]})
        try:
            history, summary = await asyncio.gather(
                client.stock_movements(ctx.user_id, ctx.tenant_id, wanted), client.stock_summary(ctx.user_id, ctx.tenant_id, filters)
            )
        except DataPipelineError as exc:
            raise pipeline_failure(exc) from exc
        movements = [
            {
                "at": item.get("at"),
                "type": item.get("type"),
                "sku": item.get("sku"),
                "product": item.get("product_name"),
                "change": item.get("delta"),
                "on_hand_after": item.get("on_hand_after"),
                "location": item.get("location_name"),
                "other_location": item.get("other_location_name"),
                "counterparty": item.get("counterparty"),
                "reference": item.get("reference"),
                "note": clip(item.get("note"), 200) or None,
            }
            for item in map(as_dict, as_list(as_dict(history).get("items")))
        ]
        locations = [
            {
                "location": place.get("location_name"),
                "on_hand": place.get("qty_on_hand"),
                "reserved": place.get("qty_reserved"),
                "available": place.get("qty_available"),
                **{key: place.get(key) for key in ("received", "sold", "shipped_out", "shipped_in", "damaged", "lost", "returned") if place.get(key)},
            }
            for place in map(as_dict, as_list(as_dict(summary).get("locations")))
        ]
        scope = f" for {args.sku}" if args.sku else ""
        return ToolOutput(
            data={
                "movements": movements,
                "total": as_dict(history).get("total"),
                "totals": as_dict(summary).get("totals"),
                "locations": locations,
            },
            summary=f"{plural(len(movements), 'stock movement')}{scope}" + (f" of {as_dict(history).get('total')}" if as_dict(history).get("total") else ""),
        )

    async def reserve_stock(invocation: ToolInvocation) -> ToolOutput:
        args = invocation.args
        assert isinstance(args, ReserveStockArgs)
        ctx = invocation.ctx
        place = await location(ctx, args.location) if args.location else None
        try:
            held = await client.reserve_stock(
                ctx.user_id, ctx.tenant_id, sku=args.sku, quantity=args.quantity, location_id=str(place["id"]) if place else None
            )
        except DataPipelineError as exc:
            raise pipeline_write_failure(exc) from exc
        reservation_id = str(held.get("reservation_id"))
        allocations = [
            {"location": as_dict(item).get("location_name"), "quantity": as_dict(item).get("qty")} for item in as_list(held.get("allocations"))
        ]
        spread = ", ".join(f"{item['quantity']} at {item['location']}" for item in allocations)
        return ToolOutput(
            data={"reservation_id": reservation_id, "sku": args.sku, "quantity": args.quantity, "allocations": allocations},
            summary=f"Reserved {args.quantity} × {args.sku}" + (f" ({spread})" if spread else ""),
            ref_id=reservation_id,
            undo=UndoPlan(
                args={"reservation_id": reservation_id, "sku": args.sku, "quantity": args.quantity},
                label=f"Release the reservation of {args.quantity} × {args.sku}",
            ),
        )

    async def reserve_preview(ctx: AgentContext, args: ToolInput) -> dict[str, Any]:
        assert isinstance(args, ReserveStockArgs)
        await variant(ctx, args.sku)
        place = await location(ctx, args.location) if args.location else None
        try:
            availability = as_dict(await client.availability(ctx.user_id, ctx.tenant_id, args.sku))
        except DataPipelineError as exc:
            raise pipeline_failure(exc) from exc
        if place is not None:
            levels = [as_dict(level) for level in as_list(availability.get("by_location"))]
            available = sum(int(level.get("qty_available") or 0) for level in levels if str(level.get("location_id")) == str(place["id"]))
        else:
            available = int(availability.get("total_available") or 0)
        if available < args.quantity:
            where = f" at {place.get('name')}" if place else ""
            raise ToolInputError(f"only {available} × {args.sku} available{where}; can't reserve {args.quantity}")
        return {"kind": "stock_reservation", "sku": args.sku, "quantity": args.quantity, "location": place.get("name") if place else None, "available": available}

    async def release_reservation(invocation: UndoInvocation) -> str:
        reservation_id = str(invocation.args["reservation_id"])
        try:
            await client.release_stock(invocation.ctx.user_id, invocation.ctx.tenant_id, reservation_id)
        except DataPipelineError as exc:
            if "already been released" in str(exc):
                return f"reservation {reservation_id} was already released"
            raise pipeline_failure(exc) from exc
        return f"released the reservation of {invocation.args.get('quantity')} × {invocation.args.get('sku')}"

    async def release_stock(invocation: ToolInvocation) -> ToolOutput:
        args = invocation.args
        assert isinstance(args, ReleaseStockArgs)
        ctx = invocation.ctx
        try:
            released = await client.release_stock(ctx.user_id, ctx.tenant_id, args.reservation_id)
        except DataPipelineError as exc:
            if exc.status == 400:
                raise ToolInputError(str(exc)) from exc
            raise pipeline_write_failure(exc) from exc
        quantity = released.get("released_qty")
        return ToolOutput(
            data={"reservation_id": args.reservation_id, "released": quantity},
            summary=f"Released reservation {args.reservation_id} ({quantity} units)",
            ref_id=args.reservation_id,
        )

    async def release_preview(ctx: AgentContext, args: ToolInput) -> dict[str, Any]:
        assert isinstance(args, ReleaseStockArgs)
        try:
            rows = await client.stock_movements(
                ctx.user_id, ctx.tenant_id, {"ref_id": args.reservation_id, "reason": ["RESERVE", "RELEASE"], "limit": 200}
            )
        except DataPipelineError as exc:
            if exc.status in (400, 422):
                raise ToolInputError(f"'{args.reservation_id}' is not a reservation id") from exc
            raise pipeline_failure(exc) from exc
        entries = [as_dict(row) for row in as_list(as_dict(rows).get("items"))]
        held = [row for row in entries if row.get("reason") == "RESERVE"]
        if not held:
            raise ToolInputError(f"there is no reservation {args.reservation_id} in this workspace; list_stock_reservations shows the open ones")
        if any(row.get("reason") == "RELEASE" for row in entries):
            raise ToolInputError(f"reservation {args.reservation_id} was already released")
        return {
            "kind": "stock_release",
            "reservation_id": args.reservation_id,
            "sku": held[0].get("sku"),
            "product": held[0].get("product_name"),
            "quantity": sum(int(row.get("delta") or 0) for row in held),
            "locations": [{"location": row.get("location_name"), "quantity": row.get("delta")} for row in held],
            "reserved_at": min(str(row.get("at")) for row in held),
            "reserved_by_you": all(str(row.get("created_by")) == str(ctx.user_id) for row in held),
        }

    # ------------------------------------------------------------------ retire
    async def retire(ctx: AgentContext, product_id: str, name: str) -> str:
        try:
            retired = await client.retire_product(ctx.user_id, ctx.tenant_id, product_id)
        except DataPipelineError as exc:
            raise pipeline_failure(exc) from exc
        return f"retired '{name}'" if retired is not None else f"'{name}' was already gone"

    async def plan_retire(ctx: AgentContext, args: RetireCatalogItemArgs) -> dict[str, Any]:
        current = await product(ctx, args.product_id)
        if current.get("status") == "RETIRED":
            raise ToolInputError(f"'{current.get('name')}' is already retired")
        return current

    async def retire_catalog_item(invocation: ToolInvocation) -> ToolOutput:
        args = invocation.args
        assert isinstance(args, RetireCatalogItemArgs)
        ctx = invocation.ctx
        current = await plan_retire(ctx, args)
        name = str(current.get("name"))
        try:
            await client.retire_product(ctx.user_id, ctx.tenant_id, args.product_id)
        except DataPipelineError as exc:
            raise pipeline_write_failure(exc) from exc
        variants = [
            {"sku": str(v.get("sku")), "status": str(v.get("status"))} for v in map(as_dict, as_list(current.get("variants")))
        ]
        return ToolOutput(
            data={"product_id": args.product_id, "name": name, "previous_status": current.get("status"), "skus": len(variants)},
            summary=f"Catalog item '{name}' retired with its {plural(len(variants), 'SKU')}",
            ref_id=args.product_id,
            undo=UndoPlan(
                args={"product_id": args.product_id, "status": current.get("status"), "variants": variants},
                label=f"Restore '{name}' to {str(current.get('status')).lower()} with its SKUs",
            ),
        )

    async def retire_preview(ctx: AgentContext, args: ToolInput) -> dict[str, Any]:
        assert isinstance(args, RetireCatalogItemArgs)
        current = await plan_retire(ctx, args)
        return {
            "kind": "catalog_retire",
            "product_id": args.product_id,
            "name": current.get("name"),
            "status": current.get("status"),
            "skus": [str(as_dict(v).get("sku")) for v in as_list(current.get("variants"))],
        }

    async def unretire(invocation: UndoInvocation) -> str:
        ctx = invocation.ctx
        product_id = str(invocation.args["product_id"])
        status = str(invocation.args.get("status") or "DRAFT")
        wanted = {str(as_dict(v).get("sku")): str(as_dict(v).get("status")) for v in as_list(invocation.args.get("variants"))}
        try:
            await client.update_product(ctx.user_id, ctx.tenant_id, product_id, {"status": status})
            current = await product(ctx, product_id)
            payloads = [
                variant_payload(as_dict(v), status=wanted[str(as_dict(v).get("sku"))])
                for v in as_list(current.get("variants"))
                if wanted.get(str(as_dict(v).get("sku"))) not in (None, as_dict(v).get("status"))
            ]
            if payloads:
                await client.upsert_variants(ctx.user_id, ctx.tenant_id, product_id, payloads)
        except DataPipelineError as exc:
            raise pipeline_failure(exc) from exc
        return f"restored catalog item {product_id} to {status.lower()} with {plural(len(payloads), 'SKU')} reactivated"

    common = {"scope": ToolScope.CATALOG, "category": ToolCategory.ACTION, "kind": ToolKind.WRITE, "acl": writer, "timeout_seconds": 60}
    return [
        ToolDefinition(
            name="create_catalog_item",
            description=(
                "Add a product or service to the workspace catalog, optionally with sellable SKUs and prices. SKUs "
                "may have options (e.g. Size and Color); every SKU names the same options. New items start as DRAFT "
                "unless status ACTIVE is given. The category must be an existing catalog category."
            ),
            input_model=CreateCatalogItemArgs,
            handler=create_catalog_item,
            preview=create_preview,
            undo_handler=retire_created,
            **common,
        ),
        ToolDefinition(
            name="update_catalog_item",
            description=(
                "Change a catalog item's details, type, status (DRAFT/ACTIVE), discount limits, or its SKUs' price, "
                "currency, barcode, weight or status (retire or reactivate one SKU). Only the fields you pass change. "
                "To remove a whole item use retire_catalog_item; to add SKUs use add_catalog_skus."
            ),
            input_model=UpdateCatalogItemArgs,
            handler=update_catalog_item,
            preview=update_preview,
            undo_handler=restore_values,
            **common,
        ),
        ToolDefinition(
            name="record_stock_movement",
            description=(
                "Record something that happened to a SKU's stock: RECEIVED, SOLD, SHIPPED to another location, DAMAGED, "
                "LOST or RETURNED. Stock history can't be edited: only a shipment can be undone (by shipping it back); "
                "other mistakes are fixed with correct_stock_count."
            ),
            input_model=StockMovementArgs,
            handler=record_stock_movement,
            preview=movement_preview,
            undo_handler=ship_back,
            **common,
        ),
        ToolDefinition(
            name="correct_stock_count",
            description=(
                "Replace a SKU's on-hand count at a location with a physical count, with a note saying why. Only workspace "
                "owners and admins may; call check_inventory first and pass the on-hand figure it shows for that location."
            ),
            input_model=CorrectStockCountArgs,
            handler=correct_stock_count,
            preview=correction_preview,
            undo_handler=restore_count,
            **(common | {"acl": owner_or_admin}),
        ),
        ToolDefinition(
            name="reserve_stock",
            description="Hold units of a SKU for a customer so they can't be sold to anyone else. Returns a reservation_id.",
            input_model=ReserveStockArgs,
            handler=reserve_stock,
            preview=reserve_preview,
            undo_handler=release_reservation,
            **common,
        ),
        ToolDefinition(
            name="release_stock",
            description="Release a stock reservation (by reservation_id) so the units can be sold again.",
            input_model=ReleaseStockArgs,
            handler=release_stock,
            preview=release_preview,
            **common,
        ),
        ToolDefinition(
            name="retire_catalog_item",
            description="Retire a catalog item and all its SKUs so they can no longer be sold or quoted. Items are never deleted.",
            input_model=RetireCatalogItemArgs,
            handler=retire_catalog_item,
            preview=retire_preview,
            undo_handler=unretire,
            **common,
        ),
        ToolDefinition(
            name="stock_history",
            description=(
                "Stock movements newest first (what was received, sold, shipped, damaged, lost, returned or corrected), "
                "with totals per location. Filter by SKU, location, kind of movement and dates."
            ),
            kind=ToolKind.READ,
            scope=ToolScope.READ,
            category=ToolCategory.KNOWLEDGE,
            input_model=StockHistoryArgs,
            handler=stock_history,
            timeout_seconds=30,
        ),
    ]


def new_variant_payload(item: NewVariantArgs, ids: dict[tuple[str, str], str]) -> dict[str, Any]:
    """A new SKU for the upsert; ``KeyError`` when one of its option values has no id."""
    return {
        "sku": item.sku,
        "price": money(item.price),
        "currency": item.currency,
        "barcode": (item.barcode or "").strip() or None,
        "weight": money(item.weight) if item.weight is not None else None,
        "status": "ACTIVE",
        "option_value_ids": [ids[(choice.name.lower(), choice.value.lower())] for choice in item.options],
    }


def _sku_overrides(existing: dict[str, Any], change: SkuChangeArgs) -> tuple[dict[str, Any], dict[str, Any]]:
    """(the SKU fields this change sets, the values they replace), leaving out fields that wouldn't change."""
    overrides: dict[str, Any] = {}
    replaced: dict[str, Any] = {}
    if change.price is not None and not same_number(existing.get("price"), change.price):
        overrides["price"], replaced["price"] = money(change.price), str(existing.get("price"))
    if change.currency is not None and change.currency != existing.get("currency"):
        overrides["currency"], replaced["currency"] = change.currency, existing.get("currency")
    if change.barcode is not None and (change.barcode.strip() or None) != existing.get("barcode"):
        overrides["barcode"], replaced["barcode"] = change.barcode.strip() or None, existing.get("barcode")
    if change.weight is not None and not same_number(existing.get("weight"), change.weight):
        overrides["weight"], replaced["weight"] = money(change.weight), existing.get("weight")
    if change.status is not None and change.status != existing.get("status"):
        overrides["status"], replaced["status"] = change.status, existing.get("status")
    return overrides, replaced
