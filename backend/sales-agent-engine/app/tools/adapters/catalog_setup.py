"""Setting up the catalog: categories, stock locations, the SKUs of existing items, and bringing
retired items back. Only the coordinator has these tools (``CATALOG_SETUP``); sub-agents don't.

Nothing is removed that can't be put back. A category is removed only while no item names it and
no category sits under it, and a stock location only while it has never held stock (removing one
would erase its stock history), so undo simply adds them again. data-pipeline can't delete SKUs,
so undoing added SKUs retires them. Viewers of a workspace can't change its catalog.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal

from pydantic import Field, StringConstraints, model_validator

from app.core.context import AgentContext
from app.platform.data_pipeline import DataPipelineClient, DataPipelineError
from app.platform.workspace_client import WorkspaceDirectory
from app.tools.adapters.catalog_lookup import CatalogLookup, ProductId, Sku, find_location, money, variant_options, variant_payload
from app.tools.adapters.catalog_writes import (
    NewVariantArgs,
    check_same_options,
    new_variant_payload,
    option_value_ids,
)
from app.tools.adapters.common import as_dict, as_list, pipeline_failure, pipeline_write_failure, plural, workspace_writer_required
from app.tools.registry import ToolDefinition
from app.tools.types import (
    ToolCategory,
    ToolFailed,
    ToolInput,
    ToolInputError,
    ToolInvocation,
    ToolKind,
    ToolOutcomeUnknown,
    ToolOutput,
    ToolScope,
    UndoInvocation,
    UndoPlan,
)

CategoryKey = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
LocationType = Literal["WAREHOUSE", "STORE", "SUPPLIER", "IN_TRANSIT"]
_NEW_KEY = re.compile(r"[a-z0-9]+(?:[_-][a-z0-9]+)*")
_LOCATION_FIELDS = ("name", "type", "sellable", "priority")


class SaveCategoryArgs(ToolInput):
    key: CategoryKey = Field(description="An existing category's key to rename it, or a new short lowercase key such as office_chairs")
    label: str = Field(min_length=1, max_length=255, description="The name people see")
    parent_key: str | None = Field(
        default=None,
        max_length=100,
        description="The parent category's key. Leave out to keep an existing category's parent; empty text removes it",
    )


class DeleteCategoryArgs(ToolInput):
    key: CategoryKey


class CreateLocationArgs(ToolInput):
    name: str = Field(min_length=1, max_length=255)
    type: LocationType = "WAREHOUSE"
    sellable: bool = Field(default=True, description="Whether stock here can be sold and reserved")
    priority: int = Field(default=100, ge=1, le=10_000, description="Lower numbers are used first when stock is reserved")
    city: str | None = Field(default=None, max_length=100)
    country: str | None = Field(default=None, max_length=100)


class UpdateLocationArgs(ToolInput):
    location: str = Field(min_length=1, max_length=255, description="The location's current name or id")
    name: str | None = Field(default=None, min_length=1, max_length=255, description="A new name")
    type: LocationType | None = None
    sellable: bool | None = Field(default=None, description="Whether stock here can be sold and reserved")
    priority: int | None = Field(default=None, ge=1, le=10_000, description="Lower numbers are used first when stock is reserved")
    city: str | None = Field(default=None, max_length=100, description="Empty text removes it")
    country: str | None = Field(default=None, max_length=100, description="Empty text removes it")


class DeleteLocationArgs(ToolInput):
    location: str = Field(min_length=1, max_length=255, description="The location's name or id")


class AddSkusArgs(ToolInput):
    product_id: ProductId = Field(description="The item to add SKUs to (from search_catalog or list_catalog_items)")
    skus: list[NewVariantArgs] = Field(
        min_length=1,
        max_length=50,
        description="New SKUs. If the item has options (e.g. Size), each new SKU names a value for every one of them",
    )

    @model_validator(mode="after")
    def _distinct(self) -> AddSkusArgs:
        if len({item.sku for item in self.skus}) != len(self.skus):
            raise ValueError("each SKU may appear only once")
        check_same_options(self.skus)
        return self


class RestoreItemArgs(ToolInput):
    product_id: ProductId
    status: Literal["ACTIVE", "DRAFT"] = Field(default="ACTIVE", description="The status it comes back with")
    skus: list[Sku] = Field(default_factory=list, max_length=50, description="The SKUs to sell again; default all of them")


@dataclass
class _SkusPlan:
    product: dict[str, Any]
    axes: list[dict[str, Any]]  # the options as they are: [{name, values: [value]}]
    merged: list[dict[str, Any]]  # the options with the new values added
    new_values: list[dict[str, Any]]  # [{name, values}] the new SKUs add
    warnings: list[str] = field(default_factory=list)


def catalog_setup_tools(client: DataPipelineClient, directory: WorkspaceDirectory) -> list[ToolDefinition]:
    writer = workspace_writer_required(directory, "the catalog")
    lookup = CatalogLookup(client)

    # ------------------------------------------------------------------ categories
    async def plan_category(ctx: AgentContext, args: SaveCategoryArgs) -> tuple[dict[str, Any] | None, str | None]:
        """(the category as it is, or None if new; the parent it will have)."""
        categories = await lookup.categories(ctx)
        by_key = {str(item.get("key")): item for item in categories}
        existing = by_key.get(args.key)
        if existing is None and not _NEW_KEY.fullmatch(args.key):
            suggestion = re.sub(r"[^a-z0-9]+", "_", args.key.lower()).strip("_") or "new_category"
            raise ToolInputError(f"'{args.key}' can't be a new category key: use lowercase letters, digits, _ and -, e.g. '{suggestion}'")
        if args.parent_key is None:
            parent = existing.get("parent_key") if existing is not None else None
        else:
            parent = args.parent_key.strip() or None
        if parent is not None:
            if parent == args.key:
                raise ToolInputError("a category can't be its own parent")
            if parent not in by_key:
                raise ToolInputError(f"there is no category '{parent}' to put it under (categories: {', '.join(sorted(by_key)[:40]) or 'none'})")
            cursor, seen = parent, set()
            while cursor is not None and cursor not in seen:
                if cursor == args.key:
                    raise ToolInputError(f"'{parent}' is inside '{args.key}', so it can't be its parent")
                seen.add(cursor)
                cursor = as_dict(by_key.get(cursor)).get("parent_key")
        if existing is not None and existing.get("label") == args.label and existing.get("parent_key") == parent:
            raise ToolInputError(f"category '{args.key}' already has this label and parent")
        return existing, parent

    async def save_catalog_category(invocation: ToolInvocation) -> ToolOutput:
        args = invocation.args
        assert isinstance(args, SaveCategoryArgs)
        ctx = invocation.ctx
        existing, parent = await plan_category(ctx, args)
        try:
            await client.save_category(ctx.user_id, ctx.tenant_id, {"key": args.key, "label": args.label, "parent_key": parent})
        except DataPipelineError as exc:
            raise pipeline_write_failure(exc) from exc
        if existing is None:
            undo = UndoPlan(args={"key": args.key, "remove": True}, label=f"Remove the new category '{args.label}'")
            summary = f"Category '{args.label}' ({args.key}) added" + (f" under '{parent}'" if parent else "")
        else:
            undo = UndoPlan(
                args={"key": args.key, "label": existing.get("label"), "parent_key": existing.get("parent_key")},
                label=f"Put category '{args.key}' back as '{existing.get('label')}'",
            )
            summary = f"Category '{args.key}' is now '{args.label}'" + (f" under '{parent}'" if parent else "")
        return ToolOutput(
            data={"key": args.key, "label": args.label, "parent_key": parent, "created": existing is None},
            summary=summary,
            ref_id=args.key,
            undo=undo,
        )

    async def category_preview(ctx: AgentContext, args: ToolInput) -> dict[str, Any]:
        assert isinstance(args, SaveCategoryArgs)
        existing, parent = await plan_category(ctx, args)
        return {
            "kind": "catalog_category",
            "action": "create" if existing is None else "update",
            "key": args.key,
            "label": args.label,
            "parent_key": parent,
            "before": None if existing is None else {"label": existing.get("label"), "parent_key": existing.get("parent_key")},
        }

    async def undo_category(invocation: UndoInvocation) -> str:
        ctx = invocation.ctx
        key = str(invocation.args["key"])
        if invocation.args.get("remove"):
            return await remove_category(ctx, key)
        payload = {"key": key, "label": invocation.args.get("label"), "parent_key": invocation.args.get("parent_key")}
        try:
            await client.save_category(ctx.user_id, ctx.tenant_id, payload)
        except DataPipelineError as exc:
            raise pipeline_failure(exc) from exc
        return f"category '{key}' is '{payload['label']}' again"

    async def remove_category(ctx: AgentContext, key: str) -> str:
        try:
            removed = await client.delete_category(ctx.user_id, ctx.tenant_id, key)
        except DataPipelineError as exc:
            if exc.status == 400:
                raise ToolFailed(f"category '{key}' is in use now, so it was kept ({exc})") from exc
            raise pipeline_failure(exc) from exc
        return f"removed category '{key}'" if removed else f"category '{key}' was already gone"

    async def plan_delete_category(ctx: AgentContext, args: DeleteCategoryArgs) -> dict[str, Any]:
        categories = await lookup.categories(ctx)
        existing = next((item for item in categories if item.get("key") == args.key), None)
        if existing is None:
            known = ", ".join(sorted(str(item.get("key")) for item in categories)[:40]) or "none"
            raise ToolInputError(f"there is no category '{args.key}' (categories: {known})")
        children = sorted(str(item.get("key")) for item in categories if item.get("parent_key") == args.key)
        if children:
            raise ToolInputError(f"'{args.key}' is the parent of {', '.join(children)}; move or remove those first")
        try:
            users = await client.list_products(ctx.user_id, ctx.tenant_id, {"category": args.key, "limit": 3})
        except DataPipelineError as exc:
            raise pipeline_failure(exc) from exc
        if users:
            names = ", ".join(f"'{item.get('name')}'" for item in users[:3])
            raise ToolInputError(
                f"'{args.key}' is used by {names}{' and more' if len(users) >= 3 else ''} (retired items count too); "
                "move them to another category first"
            )
        return existing

    async def delete_catalog_category(invocation: ToolInvocation) -> ToolOutput:
        args = invocation.args
        assert isinstance(args, DeleteCategoryArgs)
        ctx = invocation.ctx
        existing = await plan_delete_category(ctx, args)
        try:
            removed = await client.delete_category(ctx.user_id, ctx.tenant_id, args.key)
        except DataPipelineError as exc:
            if exc.status == 400:
                raise ToolInputError(str(exc)) from exc
            raise pipeline_write_failure(exc) from exc
        if not removed:
            raise ToolInputError(f"category '{args.key}' no longer exists")
        return ToolOutput(
            data={"key": args.key, "label": existing.get("label")},
            summary=f"Category '{existing.get('label')}' ({args.key}) removed",
            ref_id=args.key,
            undo=UndoPlan(
                args={"key": args.key, "label": existing.get("label"), "parent_key": existing.get("parent_key")},
                label=f"Add the category '{existing.get('label')}' back",
            ),
        )

    async def delete_category_preview(ctx: AgentContext, args: ToolInput) -> dict[str, Any]:
        assert isinstance(args, DeleteCategoryArgs)
        existing = await plan_delete_category(ctx, args)
        return {
            "kind": "catalog_category",
            "action": "delete",
            "key": args.key,
            "label": existing.get("label"),
            "parent_key": existing.get("parent_key"),
            "before": None,
        }

    # ------------------------------------------------------------------ stock locations
    async def location_use(ctx: AgentContext, location_id: str) -> tuple[int, int, int]:
        """(units on hand, units reserved, stock movements ever recorded) at a location."""
        try:
            summary = as_dict(await client.stock_summary(ctx.user_id, ctx.tenant_id, {"location_id": location_id}))
            history = as_dict(
                await client.stock_movements(ctx.user_id, ctx.tenant_id, {"location_id": location_id, "include_holds": True, "limit": 1})
            )
        except DataPipelineError as exc:
            raise pipeline_failure(exc) from exc
        places = [as_dict(place) for place in as_list(summary.get("locations")) if str(as_dict(place).get("location_id")) == location_id]
        on_hand = sum(int(place.get("qty_on_hand") or 0) for place in places)
        reserved = sum(int(place.get("qty_reserved") or 0) for place in places)
        return on_hand, reserved, int(history.get("total") or 0)

    async def plan_new_location(ctx: AgentContext, args: CreateLocationArgs) -> dict[str, Any]:
        name = args.name.strip()
        if find_location(await lookup.locations(ctx), name) is not None:
            raise ToolInputError(f"there is already a stock location called '{name}'")
        address = {key: value.strip() for key, value in (("city", args.city), ("country", args.country)) if value and value.strip()}
        return {"name": name, "type": args.type, "sellable": args.sellable, "priority": args.priority, "address": address or None}

    async def create_stock_location(invocation: ToolInvocation) -> ToolOutput:
        args = invocation.args
        assert isinstance(args, CreateLocationArgs)
        ctx = invocation.ctx
        record = await plan_new_location(ctx, args)
        try:
            created = as_dict(await client.create_location(ctx.user_id, ctx.tenant_id, record))
        except DataPipelineError as exc:
            raise pipeline_write_failure(exc) from exc
        location_id = str(created.get("id"))
        selling = "sellable" if args.sellable else "not sellable"
        return ToolOutput(
            data={"location_id": location_id, **record},
            summary=f"Stock location '{record['name']}' added ({args.type.lower().replace('_', ' ')}, {selling}, priority {args.priority})",
            ref_id=location_id,
            undo=UndoPlan(args={"location_id": location_id, "name": record["name"]}, label=f"Remove the new stock location '{record['name']}'"),
        )

    async def create_location_preview(ctx: AgentContext, args: ToolInput) -> dict[str, Any]:
        assert isinstance(args, CreateLocationArgs)
        return {"kind": "stock_location", "action": "create", "location": await plan_new_location(ctx, args)}

    async def remove_new_location(invocation: UndoInvocation) -> str:
        ctx = invocation.ctx
        location_id, name = str(invocation.args["location_id"]), invocation.args.get("name")
        on_hand, reserved, movements = await location_use(ctx, location_id)
        if on_hand or reserved or movements:
            raise ToolFailed(f"'{name}' has held stock since it was added, so it was kept (removing it would erase that history)")
        try:
            await client.delete_location(ctx.user_id, ctx.tenant_id, location_id)
        except DataPipelineError as exc:
            if exc.status == 400 and "not found" in str(exc):
                return f"stock location '{name}' was already gone"
            raise pipeline_failure(exc) from exc
        return f"removed stock location '{name}'"

    async def plan_location_update(ctx: AgentContext, args: UpdateLocationArgs) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], list[str]]:
        """(the location as it is, its full new record, the changes, warnings)."""
        locations = await lookup.locations(ctx)
        current = await lookup.location(ctx, args.location)
        before = _record(current)
        after = {**before, "address": dict(as_dict(before["address"]))}
        if args.name is not None and args.name.strip() != before["name"]:
            other = find_location(locations, args.name)
            if other is not None and str(other.get("id")) != str(current.get("id")):
                raise ToolInputError(f"another stock location is already called '{other.get('name')}'")
            after["name"] = args.name.strip()
        for name in ("type", "sellable", "priority"):
            value = getattr(args, name)
            if value is not None:
                after[name] = value
        for name in ("city", "country"):
            value = getattr(args, name)
            if value is None:
                continue
            if value.strip():
                after["address"][name] = value.strip()
            else:
                after["address"].pop(name, None)
        after["address"] = after["address"] or None
        changes = [
            {"field": name, "before": before[name], "after": after[name]} for name in _LOCATION_FIELDS if before[name] != after[name]
        ] + [
            {"field": name, "before": as_dict(before["address"]).get(name), "after": as_dict(after["address"]).get(name)}
            for name in ("city", "country")
            if as_dict(before["address"]).get(name) != as_dict(after["address"]).get(name)
        ]
        if not changes:
            raise ToolInputError(f"nothing to change: '{before['name']}' already has these details")
        warnings = []
        if before["sellable"] and not after["sellable"]:
            on_hand, reserved, _ = await location_use(ctx, str(current.get("id")))
            if on_hand:
                warnings.append(f"Its {on_hand} units on hand will no longer count as available to sell or reserve")
            if reserved:
                warnings.append(f"The {reserved} units reserved there stay reserved")
        return current, after, changes, warnings

    async def update_stock_location(invocation: ToolInvocation) -> ToolOutput:
        args = invocation.args
        assert isinstance(args, UpdateLocationArgs)
        ctx = invocation.ctx
        current, after, changes, warnings = await plan_location_update(ctx, args)
        location_id = str(current.get("id"))
        try:
            await client.update_location(ctx.user_id, ctx.tenant_id, location_id, after)
        except DataPipelineError as exc:
            raise pipeline_write_failure(exc) from exc
        described = "; ".join(f"{change['field']} {change['before']} → {change['after']}" for change in changes)
        return ToolOutput(
            data={"location_id": location_id, "name": after["name"], "changes": changes, "warnings": warnings},
            summary=f"Stock location '{current.get('name')}' updated: {described}",
            ref_id=location_id,
            undo=UndoPlan(
                args={"location_id": location_id, "record": _record(current)},
                label=f"Put back the previous details of stock location '{current.get('name')}'",
            ),
        )

    async def update_location_preview(ctx: AgentContext, args: ToolInput) -> dict[str, Any]:
        assert isinstance(args, UpdateLocationArgs)
        current, _, changes, warnings = await plan_location_update(ctx, args)
        return {"kind": "stock_location", "action": "update", "name": current.get("name"), "changes": changes, "warnings": warnings}

    async def restore_location(invocation: UndoInvocation) -> str:
        ctx = invocation.ctx
        location_id, record = str(invocation.args["location_id"]), as_dict(invocation.args.get("record"))
        try:
            await client.update_location(ctx.user_id, ctx.tenant_id, location_id, record)
        except DataPipelineError as exc:
            if exc.status == 400 and "not found" in str(exc):
                raise ToolFailed(f"stock location '{record.get('name')}' was removed since, so there is nothing to put back") from exc
            raise pipeline_failure(exc) from exc
        return f"stock location '{record.get('name')}' has its previous details again"

    async def plan_location_delete(ctx: AgentContext, args: DeleteLocationArgs) -> dict[str, Any]:
        current = await lookup.location(ctx, args.location)
        name = current.get("name")
        on_hand, reserved, movements = await location_use(ctx, str(current.get("id")))
        if on_hand or reserved:
            held = f" ({reserved} reserved)" if reserved else ""
            raise ToolInputError(f"'{name}' holds {on_hand} units{held}; ship them elsewhere or write them off first")
        if movements:
            raise ToolInputError(
                f"'{name}' has stock history ({plural(movements, 'movement')}) and removing it would erase that history; "
                "rename it or make it not sellable instead (update_stock_location)"
            )
        return current

    async def delete_stock_location(invocation: ToolInvocation) -> ToolOutput:
        args = invocation.args
        assert isinstance(args, DeleteLocationArgs)
        ctx = invocation.ctx
        current = await plan_location_delete(ctx, args)
        try:
            await client.delete_location(ctx.user_id, ctx.tenant_id, str(current.get("id")))
        except DataPipelineError as exc:
            if exc.status == 400:
                raise ToolInputError(str(exc)) from exc
            raise pipeline_write_failure(exc) from exc
        return ToolOutput(
            data={"location_id": current.get("id"), "name": current.get("name")},
            summary=f"Stock location '{current.get('name')}' removed (it never held stock)",
            ref_id=str(current.get("id")),
            undo=UndoPlan(args={"record": _record(current)}, label=f"Add the stock location '{current.get('name')}' back"),
        )

    async def delete_location_preview(ctx: AgentContext, args: ToolInput) -> dict[str, Any]:
        assert isinstance(args, DeleteLocationArgs)
        current = await plan_location_delete(ctx, args)
        return {"kind": "stock_location", "action": "delete", "name": current.get("name"), "location": _record(current)}

    async def add_location_back(invocation: UndoInvocation) -> str:
        ctx = invocation.ctx
        record = as_dict(invocation.args.get("record"))
        if find_location(await lookup.locations(ctx), str(record.get("name"))) is not None:
            return f"stock location '{record.get('name')}' is already there"
        try:
            await client.create_location(ctx.user_id, ctx.tenant_id, record)
        except DataPipelineError as exc:
            raise pipeline_failure(exc) from exc
        return f"added stock location '{record.get('name')}' back"

    # ------------------------------------------------------------------ SKUs of an item
    async def plan_skus(ctx: AgentContext, args: AddSkusArgs) -> _SkusPlan:
        item = await lookup.product(ctx, args.product_id)
        name = item.get("name")
        if item.get("status") == "RETIRED":
            raise ToolInputError(f"'{name}' is retired; bring it back with restore_catalog_item first")
        taken = [new.sku for new in args.skus if await lookup.sku_in_use(ctx, new.sku)]
        if taken:
            raise ToolInputError(f"SKU already in use in this catalog: {', '.join(taken)}")
        options = sorted(map(as_dict, as_list(item.get("options"))), key=lambda option: int(option.get("position") or 0))
        axes = [
            {
                "name": str(option.get("name")),
                "values": [str(value.get("value")) for value in sorted(map(as_dict, as_list(option.get("values"))), key=lambda v: int(v.get("position") or 0))],
            }
            for option in options
        ]
        variants = [as_dict(v) for v in as_list(item.get("variants"))]
        named = [choice.name for choice in args.skus[0].options]
        axis_names = {axis["name"].lower(): axis for axis in axes}
        if axes:
            extra = [option for option in named if option.lower() not in axis_names]
            missing = [axis["name"] for axis in axes if axis["name"].lower() not in {option.lower() for option in named}]
            known = ", ".join(axis["name"] for axis in axes)
            if extra:
                raise ToolInputError(f"'{name}' has no option {', '.join(extra)} (its options: {known}); an item's SKUs share its options")
            if missing:
                raise ToolInputError(f"say each new SKU's {', '.join(missing)} ('{name}' has the options {known})")
        elif named and variants:
            raise ToolInputError(f"the SKUs of '{name}' have no options, so new SKUs can't have them either")

        merged = [{"name": axis["name"], "values": list(axis["values"])} for axis in axes]
        new_values: dict[str, list[str]] = {}
        for new in args.skus:
            for choice in new.options:
                axis = next((a for a in merged if a["name"].lower() == choice.name.lower()), None)
                if axis is None:  # an item without options gets its first ones
                    axis = {"name": choice.name, "values": []}
                    merged.append(axis)
                if choice.value.lower() not in {value.lower() for value in axis["values"]}:
                    axis["values"].append(choice.value)
                    new_values.setdefault(axis["name"], []).append(choice.value)

        plan = _SkusPlan(item, axes, merged, [{"name": key, "values": values} for key, values in new_values.items()])
        if axes:
            existing = {
                frozenset((key.lower(), value.lower()) for key, value in variant_options(item, v).items()): str(v.get("sku")) for v in variants
            }
            for new in args.skus:
                same = existing.get(frozenset((c.name.lower(), c.value.lower()) for c in new.options))
                if same:
                    described = ", ".join(f"{c.name} {c.value}" for c in new.options)
                    raise ToolInputError(f"SKU {same} already has {described}; a new SKU needs its own combination")
        currencies = sorted({str(v.get("currency")) for v in variants if v.get("status") == "ACTIVE"} | {new.currency for new in args.skus})
        if len(currencies) > 1:
            plan.warnings.append(f"'{name}' will have SKUs priced in {', '.join(currencies)}; a quote can't mix currencies")
        return plan

    async def add_catalog_skus(invocation: ToolInvocation) -> ToolOutput:
        args = invocation.args
        assert isinstance(args, AddSkusArgs)
        ctx = invocation.ctx
        plan = await plan_skus(ctx, args)
        name = str(plan.product.get("name"))
        ids = option_value_ids(as_list(plan.product.get("options")))
        if plan.new_values:
            try:
                ids = option_value_ids(await client.set_options(ctx.user_id, ctx.tenant_id, args.product_id, _options_payload(plan.merged)))
            except DataPipelineError as exc:
                raise pipeline_write_failure(exc) from exc
        try:
            payloads = [new_variant_payload(new, ids) for new in args.skus]
            await client.upsert_variants(ctx.user_id, ctx.tenant_id, args.product_id, payloads)
        except (DataPipelineError, KeyError) as exc:
            if isinstance(exc, DataPipelineError) and exc.maybe_applied:
                raise ToolOutcomeUnknown(str(exc)) from exc
            reason = f"option value {exc} is missing" if isinstance(exc, KeyError) else str(exc)
            if not plan.new_values:
                raise ToolFailed(f"the SKUs could not be added ({reason})") from exc
            try:  # no SKU uses the new option values, so taking them out again unlinks nothing
                await client.set_options(ctx.user_id, ctx.tenant_id, args.product_id, _options_payload(plan.axes))
                cleanup = "the new option values were taken out again"
            except DataPipelineError:
                cleanup = "taking the new option values out again also failed"
            raise ToolFailed(f"the SKUs could not be added ({reason}); {cleanup}") from exc
        skus = [new.sku for new in args.skus]
        return ToolOutput(
            data={"product_id": args.product_id, "name": name, "skus": skus, "new_option_values": plan.new_values, "warnings": plan.warnings},
            summary=f"Added {plural(len(skus), 'SKU')} to '{name}': {', '.join(skus)}",
            ref_id=args.product_id,
            undo=UndoPlan(
                args={"product_id": args.product_id, "name": name, "skus": skus},
                label=f"Retire the new SKUs {', '.join(skus)} of '{name}' (SKUs can't be deleted)",
            ),
        )

    async def add_skus_preview(ctx: AgentContext, args: ToolInput) -> dict[str, Any]:
        assert isinstance(args, AddSkusArgs)
        plan = await plan_skus(ctx, args)
        return {
            "kind": "catalog_skus",
            "product_id": args.product_id,
            "name": plan.product.get("name"),
            "skus": [new.model_dump(mode="json") | {"price": money(new.price)} for new in args.skus],
            "new_option_values": plan.new_values,
            "warnings": plan.warnings,
        }

    async def retire_added(invocation: UndoInvocation) -> str:
        ctx = invocation.ctx
        product_id, name = str(invocation.args["product_id"]), invocation.args.get("name")
        wanted = {str(sku) for sku in as_list(invocation.args.get("skus"))}
        item = await lookup.product(ctx, product_id)
        payloads = [
            variant_payload(as_dict(v), status="RETIRED")
            for v in as_list(item.get("variants"))
            if str(as_dict(v).get("sku")) in wanted and as_dict(v).get("status") != "RETIRED"
        ]
        if not payloads:
            return f"the new SKUs of '{name}' were already retired"
        try:
            await client.upsert_variants(ctx.user_id, ctx.tenant_id, product_id, payloads)
        except DataPipelineError as exc:
            raise pipeline_failure(exc) from exc
        return f"retired {plural(len(payloads), 'SKU')} of '{name}'"

    # ------------------------------------------------------------------ restore a retired item
    async def plan_restore(ctx: AgentContext, args: RestoreItemArgs) -> tuple[dict[str, Any], list[dict[str, Any]], list[str], list[str]]:
        """(the item, SKUs to sell again, SKUs that stay retired, warnings)."""
        item = await lookup.product(ctx, args.product_id)
        name = item.get("name")
        if item.get("status") != "RETIRED":
            raise ToolInputError(f"'{name}' isn't retired (it is {str(item.get('status')).lower()})")
        variants = {str(as_dict(v).get("sku")): as_dict(v) for v in as_list(item.get("variants"))}
        unknown = [sku for sku in args.skus if sku not in variants]
        if unknown:
            raise ToolInputError(f"'{name}' has no SKU {', '.join(unknown)} (SKUs: {', '.join(variants) or 'none'})")
        chosen = [variants[sku] for sku in args.skus] if args.skus else list(variants.values())
        reactivate = [v for v in chosen if v.get("status") != "ACTIVE"]
        staying = sorted(sku for sku, v in variants.items() if v.get("status") == "RETIRED" and v not in reactivate)
        warnings = []
        if not variants:
            warnings.append(f"'{name}' has no SKUs, so there is nothing to sell until one is added")
        elif args.status == "ACTIVE" and not reactivate and not any(v.get("status") == "ACTIVE" for v in variants.values()):
            warnings.append(f"no SKU of '{name}' will be active, so it can't be sold or quoted yet")
        return item, reactivate, staying, warnings

    async def restore_catalog_item(invocation: ToolInvocation) -> ToolOutput:
        args = invocation.args
        assert isinstance(args, RestoreItemArgs)
        ctx = invocation.ctx
        item, reactivate, _, warnings = await plan_restore(ctx, args)
        name = str(item.get("name"))
        try:
            await client.update_product(ctx.user_id, ctx.tenant_id, args.product_id, {"status": args.status})
        except DataPipelineError as exc:
            raise pipeline_write_failure(exc) from exc
        if reactivate:
            try:
                await client.upsert_variants(
                    ctx.user_id, ctx.tenant_id, args.product_id, [variant_payload(v, status="ACTIVE") for v in reactivate]
                )
            except DataPipelineError as exc:
                if exc.maybe_applied:
                    raise ToolOutcomeUnknown(str(exc)) from exc
                try:
                    await client.update_product(ctx.user_id, ctx.tenant_id, args.product_id, {"status": "RETIRED"})
                    cleanup = "the item was retired again"
                except DataPipelineError:
                    cleanup = "retiring the item again also failed"
                raise ToolFailed(f"its SKUs could not be reactivated ({exc}); {cleanup}") from exc
        skus = [str(v.get("sku")) for v in reactivate]
        return ToolOutput(
            data={"product_id": args.product_id, "name": name, "status": args.status, "skus": skus, "warnings": warnings},
            summary=f"Catalog item '{name}' restored as {args.status} with {plural(len(skus), 'SKU')} reactivated",
            ref_id=args.product_id,
            undo=UndoPlan(
                args={"product_id": args.product_id, "name": name, "skus": skus},
                label=f"Retire '{name}' again" + (f" with {', '.join(skus)}" if skus else ""),
            ),
        )

    async def restore_preview(ctx: AgentContext, args: ToolInput) -> dict[str, Any]:
        assert isinstance(args, RestoreItemArgs)
        item, reactivate, staying, warnings = await plan_restore(ctx, args)
        return {
            "kind": "catalog_restore",
            "product_id": args.product_id,
            "name": item.get("name"),
            "status": args.status,
            "skus": [str(v.get("sku")) for v in reactivate],
            "staying_retired": staying,
            "warnings": warnings,
        }

    async def retire_again(invocation: UndoInvocation) -> str:
        ctx = invocation.ctx
        product_id, name = str(invocation.args["product_id"]), invocation.args.get("name")
        wanted = {str(sku) for sku in as_list(invocation.args.get("skus"))}
        try:
            await client.update_product(ctx.user_id, ctx.tenant_id, product_id, {"status": "RETIRED"})
            item = await lookup.product(ctx, product_id)
            payloads = [
                variant_payload(as_dict(v), status="RETIRED")
                for v in as_list(item.get("variants"))
                if str(as_dict(v).get("sku")) in wanted and as_dict(v).get("status") != "RETIRED"
            ]
            if payloads:
                await client.upsert_variants(ctx.user_id, ctx.tenant_id, product_id, payloads)
        except DataPipelineError as exc:
            raise pipeline_failure(exc) from exc
        return f"retired '{name}' again with {plural(len(payloads), 'SKU')}"

    common = {
        "scope": ToolScope.CATALOG_SETUP,
        "category": ToolCategory.ACTION,
        "kind": ToolKind.WRITE,
        "acl": writer,
        "timeout_seconds": 60,
    }
    return [
        ToolDefinition(
            name="save_catalog_category",
            description=(
                "Add a catalog category, or rename an existing one (by its key). New keys are short and lowercase, "
                "e.g. office_chairs. describe_catalog lists the categories."
            ),
            input_model=SaveCategoryArgs,
            handler=save_catalog_category,
            preview=category_preview,
            undo_handler=undo_category,
            **common,
        ),
        ToolDefinition(
            name="delete_catalog_category",
            description="Remove a catalog category that no item uses (retired items count) and no other category sits under.",
            input_model=DeleteCategoryArgs,
            handler=delete_catalog_category,
            preview=delete_category_preview,
            undo_handler=undo_category,
            **common,
        ),
        ToolDefinition(
            name="create_stock_location",
            description=(
                "Add a stock location (warehouse, store, supplier or in transit): whether its stock can be sold, and "
                "its priority when stock is reserved (lower first)."
            ),
            input_model=CreateLocationArgs,
            handler=create_stock_location,
            preview=create_location_preview,
            undo_handler=remove_new_location,
            **common,
        ),
        ToolDefinition(
            name="update_stock_location",
            description="Rename a stock location or change its type, whether its stock can be sold, its priority, city or country.",
            input_model=UpdateLocationArgs,
            handler=update_stock_location,
            preview=update_location_preview,
            undo_handler=restore_location,
            **common,
        ),
        ToolDefinition(
            name="delete_stock_location",
            description=(
                "Remove a stock location that has never held stock. A location with stock or stock history can't be "
                "removed (that would erase the history): rename it or make it not sellable instead."
            ),
            input_model=DeleteLocationArgs,
            handler=delete_stock_location,
            preview=delete_location_preview,
            undo_handler=add_location_back,
            **common,
        ),
        ToolDefinition(
            name="add_catalog_skus",
            description=(
                "Add SKUs to an existing catalog item, with prices and, if the item has options (e.g. Size), a value for "
                "each option; a new value (e.g. Size XL) is added to the option. Undo retires the new SKUs."
            ),
            input_model=AddSkusArgs,
            handler=add_catalog_skus,
            preview=add_skus_preview,
            undo_handler=retire_added,
            **common,
        ),
        ToolDefinition(
            name="restore_catalog_item",
            description="Bring back a retired catalog item as ACTIVE or DRAFT, selling all its SKUs again or only the ones named.",
            input_model=RestoreItemArgs,
            handler=restore_catalog_item,
            preview=restore_preview,
            undo_handler=retire_again,
            **common,
        ),
    ]


def _record(location: dict[str, Any]) -> dict[str, Any]:
    """The fields data-pipeline writes when a location is saved (a save replaces all of them)."""
    return {
        "name": location.get("name"),
        "type": location.get("type") or "WAREHOUSE",
        "sellable": location.get("sellable") is not False,
        "priority": int(location.get("priority") or 100),
        "address": location.get("address") if isinstance(location.get("address"), dict) else None,
    }


def _options_payload(axes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"name": axis["name"], "position": index, "values": [{"value": value, "position": order} for order, value in enumerate(axis["values"])]}
        for index, axis in enumerate(axes)
    ]
