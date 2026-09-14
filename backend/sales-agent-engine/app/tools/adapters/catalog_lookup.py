"""Lookups and payload helpers shared by the catalog tools (data-pipeline's catalog API).

Lookups raise tool errors a model can act on: an unknown product, SKU, category or location is
a ``ToolInputError`` naming what exists; data-pipeline failures go through ``pipeline_failure``.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Annotated, Any

from pydantic import Field, StringConstraints

from app.core.context import AgentContext
from app.platform.data_pipeline import DataPipelineClient, DataPipelineError
from app.tools.adapters.common import as_dict, as_list, pipeline_failure
from app.tools.types import ToolInput, ToolInputError

Tag = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
ProductId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=36, max_length=36)]
Sku = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
OptionName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
OptionValue = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]


class OptionChoiceArgs(ToolInput):
    name: OptionName = Field(description="The option, e.g. Size or Color")
    value: OptionValue = Field(description="This SKU's value of it, e.g. M or Black")


class CatalogLookup:
    def __init__(self, client: DataPipelineClient) -> None:
        self._client = client

    async def product(self, ctx: AgentContext, product_id: str) -> dict[str, Any]:
        """A product with its options and variants."""
        try:
            found = await self._client.product(ctx.user_id, ctx.tenant_id, product_id)
        except DataPipelineError as exc:
            if exc.status in (400, 422):
                raise ToolInputError(f"'{product_id}' is not a catalog product id") from exc
            raise pipeline_failure(exc) from exc
        if not isinstance(found, dict):
            raise ToolInputError(f"no catalog item {product_id} in this workspace")
        return found

    async def variant(self, ctx: AgentContext, sku: str) -> dict[str, Any]:
        try:
            found = await self._client.variant(ctx.user_id, ctx.tenant_id, sku)
        except DataPipelineError as exc:
            raise pipeline_failure(exc) from exc
        if not isinstance(found, dict):
            raise ToolInputError(f"no SKU '{sku}' in this workspace's catalog")
        return found

    async def sku_in_use(self, ctx: AgentContext, sku: str) -> bool:
        try:
            return await self._client.variant(ctx.user_id, ctx.tenant_id, sku) is not None
        except DataPipelineError as exc:
            raise pipeline_failure(exc) from exc

    async def categories(self, ctx: AgentContext) -> list[dict[str, Any]]:
        try:
            return await self._client.categories(ctx.user_id, ctx.tenant_id)
        except DataPipelineError as exc:
            raise pipeline_failure(exc) from exc

    async def check_category(self, ctx: AgentContext, category: str) -> None:
        keys = [str(item.get("key")) for item in await self.categories(ctx)]
        if category not in keys:
            known = ", ".join(sorted(keys)[:40]) or "none yet"
            raise ToolInputError(f"'{category}' is not a catalog category of this workspace (categories: {known})")

    async def locations(self, ctx: AgentContext) -> list[dict[str, Any]]:
        try:
            return await self._client.locations(ctx.user_id, ctx.tenant_id)
        except DataPipelineError as exc:
            raise pipeline_failure(exc) from exc

    async def location(self, ctx: AgentContext, wanted: str | None) -> dict[str, Any]:
        """The stock location named (by name, any case, or id); the only one when none is named."""
        locations = await self.locations(ctx)
        names = ", ".join(str(item.get("name")) for item in locations) or "none"
        if not locations:
            raise ToolInputError("this workspace has no stock locations yet; add one first")
        if wanted:
            found = find_location(locations, wanted)
            if found is None:
                raise ToolInputError(f"no stock location '{wanted}' (locations: {names})")
            return found
        if len(locations) == 1:
            return locations[0]
        raise ToolInputError(f"say which stock location to use (locations: {names})")

    async def stock_at(self, ctx: AgentContext, sku: str, location_id: str) -> tuple[int, int]:
        """(on hand, reserved) of a SKU at a location."""
        try:
            availability = await self._client.availability(ctx.user_id, ctx.tenant_id, sku)
        except DataPipelineError as exc:
            raise pipeline_failure(exc) from exc
        for level in as_list(as_dict(availability).get("by_location")):
            if str(as_dict(level).get("location_id")) == location_id:
                return int(level.get("qty_on_hand") or 0), int(level.get("qty_reserved") or 0)
        return 0, 0


def find_location(locations: list[dict[str, Any]], wanted: str) -> dict[str, Any] | None:
    key = wanted.strip().lower()
    for item in locations:
        if key in (str(item.get("id")).lower(), str(item.get("name") or "").strip().lower()):
            return item
    return None


def variant_payload(variant: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    """A variant's full current state for the upsert, with ``overrides`` applied.

    data-pipeline's variant upsert overwrites every field of a variant (barcode, currency, weight,
    status, option values), so a change always sends the variant's full current state."""
    payload = {
        "sku": variant.get("sku"),
        "barcode": variant.get("barcode"),
        "price": str(variant.get("price")),
        "currency": variant.get("currency") or "USD",
        "weight": variant.get("weight"),
        "status": variant.get("status") or "ACTIVE",
        "option_value_ids": [str(value.get("id")) for value in map(as_dict, as_list(variant.get("option_values"))) if value.get("id")],
    }
    return payload | overrides


def option_names(product: dict[str, Any]) -> dict[str, str]:
    """Option id → option name, from a product's detail."""
    return {str(option.get("id")): str(option.get("name")) for option in map(as_dict, as_list(product.get("options")))}


def variant_options(product: dict[str, Any], variant: dict[str, Any]) -> dict[str, str]:
    """A variant's option values by option name, e.g. ``{"Size": "M"}``."""
    names = option_names(product)
    return {
        names.get(str(value.get("option_id")), "Option"): str(value.get("value"))
        for value in map(as_dict, as_list(variant.get("option_values")))
    }


def money(value: Any) -> str:
    return str(Decimal(str(value)).quantize(Decimal("0.01")))


def same_number(left: Any, right: Any) -> bool:
    try:
        return Decimal(str(left)) == Decimal(str(right))
    except (InvalidOperation, ValueError):
        return False
