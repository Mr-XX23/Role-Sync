"""An in-memory data-pipeline (catalog, inventory, knowledge vault, connected apps) behind an httpx
MockTransport, answering like the real routes the engine's write tools use."""

from __future__ import annotations

import ipaddress
import json
import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

from app.platform.data_pipeline import DataPipelineClient

MAIN_WAREHOUSE = "11111111-1111-4111-8111-111111111111"
STORE = "22222222-2222-4222-8222-222222222222"
_BASE = "http://data-pipeline.test"
_VAULT = "/api/v1/knowledge-vault"
VAULT_CATEGORIES = frozenset(
    {"BATTLECARD", "PRICING_PACKAGING", "CASE_STUDY_ROI", "SECURITY_COMPLIANCE", "PRODUCT_SPEC", "CONTRACT_LEGAL", "GENERAL_RESOURCE"}
)


# What each connector's config route falls back to for a field it isn't sent (data-pipeline connector_routes.py).
CONNECTOR_DEFAULTS: dict[str, dict[str, Any]] = {
    source: {limit: amount, "categories": categories, "sync_window_days": 180, "auto_sync_interval_minutes": 0,
             "sync_frequency": "off", "auto_sync_enabled": False, "webhook_enabled": False, **extra}
    for source, limit, amount, categories, extra in (
        ("gmail", "max_emails_per_sync", 10, ["INBOX"], {}),
        ("gdrive", "max_files_per_sync", 10, ["MY_DRIVE"], {}),
        ("calendar", "max_events_per_sync", 10, ["PRIMARY"], {"future_window_days": 365}),
        ("slack", "max_messages_per_sync", 15, ["PUBLIC_CHANNELS", "DIRECT_MESSAGES", "GROUP_MESSAGES"], {}),
        ("notion", "max_records_per_sync", 15, ["PAGES", "DATABASES"], {}),
    )
}


def _json(status: int, body: Any) -> httpx.Response:
    return httpx.Response(status, json=body)


def _detail(status: int, message: str) -> httpx.Response:
    return httpx.Response(status, json={"detail": message})


@dataclass
class FakeDataPipeline:
    categories: set[str] = field(default_factory=lambda: {"software", "apparel"})
    category_details: dict[str, dict[str, Any]] = field(default_factory=dict)  # key → {label, parent_key}, when not the defaults
    locations: list[dict[str, Any]] = field(
        default_factory=lambda: [{"id": MAIN_WAREHOUSE, "name": "Main warehouse", "sellable": True, "priority": 1}]
    )
    products: dict[str, dict[str, Any]] = field(default_factory=dict)
    stock: dict[tuple[str, str], dict[str, int]] = field(default_factory=dict)  # (variant id, location id)
    reservations: dict[str, dict[str, Any]] = field(default_factory=dict)
    documents: dict[str, dict[str, Any]] = field(default_factory=dict)
    connections: dict[str, dict[str, Any]] = field(default_factory=dict)  # source → its status, as /connectors/status shows it
    connector_history: dict[str, list[dict[str, Any]]] = field(default_factory=dict)  # source → activities, newest first
    syncs_started: list[str] = field(default_factory=list)
    requests: list[tuple[str, str, Any]] = field(default_factory=list)
    failures: dict[tuple[str, str], int] = field(default_factory=dict)  # (METHOD, path) → status, once
    forbid_writes: bool = False
    corrections_allowed: bool = True  # data-pipeline lets only workspace OWNER/ADMIN correct a count
    movements: list[dict[str, Any]] = field(default_factory=list)  # the stock ledger, oldest first
    unreachable_pages: set[str] = field(default_factory=set)  # addresses ingest-url can't fetch (502)
    # What the classifier decides when a document is classified again.
    classifier_answer: dict[str, Any] = field(
        default_factory=lambda: {
            "category": "PRICING_PACKAGING", "target_competitor": "Globex", "target_industry": "SaaS",
            "sales_summary": "Globex price points", "sales_tags": ["pricing", "globex"],
        }
    )

    def add_document(self, *, name: str, user_id: Any, **fields: Any) -> dict[str, Any]:
        """A vault document as data-pipeline lists it (indexed, uploaded, unclassified by hand)."""
        document = {
            "doc_id": f"doc_{uuid4().hex[:12]}", "name": name, "type": "PDF", "status": "Indexed", "chunks": 4,
            "category": "GENERAL_RESOURCE", "target_competitor": None, "target_industry": None, "sales_summary": "",
            "sales_tags": [], "classifier_used": "openrouter", "user_id": str(user_id), "source": "USER_UPLOAD",
            "created_at": "2026-09-01T10:00:00+00:00", "last_updated": "2026-09-01T10:05:00+00:00", "metadata": {},
        } | fields
        self.documents[document["doc_id"]] = document
        return document

    # ------------------------------------------------------------------ setup
    def add_product(
        self,
        *,
        name: str,
        sku: str,
        price: str,
        type: str = "PRODUCT",
        status: str = "ACTIVE",
        max_discount_pct: str = "20.00",
        currency: str = "USD",
        on_hand: int = 0,
        location: str = MAIN_WAREHOUSE,
    ) -> dict[str, Any]:
        product_id = str(uuid4())
        variant_id = str(uuid4())
        option_value = {"id": str(uuid4()), "value": "Standard"}
        product = {
            "id": product_id,
            "name": name,
            "type": type,
            "category": "software",
            "status": status,
            "description": f"{name} description",
            "min_discount_pct": "0.00",
            "max_discount_pct": max_discount_pct,
            "keywords": [],
            "options": [],
            "created_at": self._now(),
            "variants": [
                {
                    "id": variant_id,
                    "product_id": product_id,
                    "sku": sku,
                    "barcode": f"BAR-{sku}",
                    "price": price,
                    "currency": currency,
                    "weight": "1.50",
                    "status": status if status == "RETIRED" else "ACTIVE",
                    "option_values": [option_value],
                }
            ],
        }
        self.products[product_id] = product
        if on_hand:
            self.stock[(variant_id, location)] = {"on_hand": on_hand, "reserved": 0}
        return product

    def add_item(
        self,
        *,
        name: str,
        options: dict[str, list[str]],
        skus: list[tuple[str, str, dict[str, str]]],
        status: str = "ACTIVE",
        category: str = "apparel",
    ) -> dict[str, Any]:
        """An item with option axes and SKUs linked to their values: ``skus`` is ``[(sku, price, {option: value})]``."""
        product_id = str(uuid4())
        axes = [
            {"id": str(uuid4()), "name": axis, "position": index, "values": []}
            for index, axis in enumerate(options)
        ]
        for axis in axes:
            axis["values"] = [
                {"id": str(uuid4()), "option_id": axis["id"], "value": value, "position": order}
                for order, value in enumerate(options[axis["name"]])
            ]
        by_choice = {(axis["name"], value["value"]): value for axis in axes for value in axis["values"]}
        product = {
            "id": product_id, "name": name, "type": "PRODUCT", "category": category, "status": status,
            "description": f"{name} description", "min_discount_pct": "0.00", "max_discount_pct": "10.00", "keywords": [],
            "options": axes, "created_at": self._now(),
            "variants": [
                {
                    "id": str(uuid4()), "product_id": product_id, "sku": sku, "barcode": None, "price": price, "currency": "USD",
                    "weight": None, "status": "RETIRED" if status == "RETIRED" else "ACTIVE",
                    "option_values": [dict(by_choice[(axis, value)]) for axis, value in choice.items()],
                }
                for sku, price, choice in skus
            ],
        }
        self.products[product_id] = product
        return product

    def add_connection(self, source: str, *, status: str = "Up to Date", locked: bool = False, synced: int = 0,
                       progress: str = "", **config: Any) -> dict[str, Any]:
        """A connection of the caller in this workspace, with config fields replaced as given."""
        connection = self._connection(source)
        connection.update(status=status, current_progress=progress, lock={"is_locked": locked},
                          backfill_state={"total_synced_so_far": synced})
        connection["config"].update(config)
        return connection

    def _connection(self, source: str) -> dict[str, Any]:
        return self.connections.setdefault(source, {
            "connection_id": f"conn_{source}", "status": "Available", "config": dict(CONNECTOR_DEFAULTS[source]),
            "backfill_state": {"total_synced_so_far": 0}, "lock": {"is_locked": False}, "current_progress": "",
            "last_successful_sync_at": "2026-09-15T08:00:00+00:00",
        })

    def _now(self) -> str:
        self._ticks = getattr(self, "_ticks", 0) + 1
        return f"2026-09-01T10:{self._ticks // 60:02d}:{self._ticks % 60:02d}+00:00"

    def client(self) -> DataPipelineClient:
        return DataPipelineClient(base_url=_BASE, http=httpx.AsyncClient(transport=self.transport()))

    def variant_by_sku(self, sku: str) -> dict[str, Any] | None:
        for product in self.products.values():
            for variant in product["variants"]:
                if variant["sku"] == sku:
                    return variant
        return None

    def _record_movement(self, body: dict[str, Any]) -> httpx.Response:
        return _movement(self, body)

    def paths(self, method: str | None = None) -> list[str]:
        return [path for verb, path, _ in self.requests if method is None or verb == method]

    def _category(self, key: str) -> dict[str, Any]:
        details = self.category_details.get(key, {})
        return {"key": key, "label": details.get("label", key.title()), "parent_key": details.get("parent_key")}

    @staticmethod
    def _location_fields(body: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": body["name"], "type": body.get("type", "WAREHOUSE"), "sellable": body.get("sellable", True),
            "priority": body.get("priority", 100), "address": body.get("address"),
        }

    def _availability(self, variant: dict[str, Any]) -> dict[str, Any]:
        levels = [
            {
                "location_id": location["id"],
                "location_name": location["name"],
                "sellable": location["sellable"],
                "qty_on_hand": level["on_hand"],
                "qty_reserved": level["reserved"],
                # Like data-pipeline: stock at a location that isn't sellable is never available.
                "qty_available": max(0, level["on_hand"] - level["reserved"]) if location["sellable"] else 0,
            }
            for location in self.locations
            if (level := self.stock.get((variant["id"], location["id"])))
        ]
        return {"variant_id": variant["id"], "sku": variant["sku"], "total_available": sum(l["qty_available"] for l in levels), "by_location": levels}

    def _list_products(self, params: httpx.QueryParams) -> list[dict[str, Any]]:
        """GET /catalog/products: the filters, newest first; one SKU must match the price and stock filters."""
        in_stock = params.get("in_stock") == "true"

        def sku_matches(variant: dict[str, Any]) -> bool:
            price = Decimal(str(variant["price"]))
            if params.get("min_price") and price < Decimal(params["min_price"]):
                return False
            if params.get("max_price") and price > Decimal(params["max_price"]):
                return False
            if in_stock:
                return any(
                    location["sellable"] and (level := self.stock.get((variant["id"], location["id"]))) and level["on_hand"] > level["reserved"]
                    for location in self.locations
                    if not params.get("location_id") or location["id"] == params["location_id"]
                )
            return True

        keywords = (params.get("keywords") or "").lower()
        rows = [
            product
            for product in self.products.values()
            if all(not params.get(key) or product.get(key) == params[key] for key in ("status", "category", "type"))
            and (not keywords or keywords in f"{product.get('name')} {product.get('description')}".lower())
            and (not any(params.get(key) for key in ("min_price", "max_price", "in_stock")) or any(map(sku_matches, product["variants"])))
        ]
        rows.sort(key=lambda product: str(product.get("created_at")), reverse=True)
        limit, offset = int(params.get("limit") or 60), int(params.get("offset") or 0)
        return [{key: value for key, value in product.items() if key != "options"} for product in rows[offset : offset + limit]]

    def _hold(self, variant: dict[str, Any], location: dict[str, Any], qty: int, reason: str, ref_id: str, request: httpx.Request) -> None:
        """A reservation's ledger row (RESERVE or RELEASE), which data-pipeline writes per location."""
        self.movements.append(
            {
                "id": str(uuid4()), "variant_id": variant["id"], "sku": variant["sku"],
                "product_name": self.products[variant["product_id"]]["name"], "location_id": location["id"],
                "location_name": location["name"], "reason": reason, "delta": qty,
                "type": "RESERVED" if reason == "RESERVE" else "RELEASED", "ref_id": ref_id,
                "created_by": request.headers["X-User-Id"], "at": self._now(), "reference": None, "counterparty": None, "note": None,
            }
        )

    # ------------------------------------------------------------------ transport
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        method, path = request.method, request.url.path
        body: Any = None
        if request.headers.get("content-type", "").startswith("application/json"):
            body = json.loads(request.content or b"null")
        self.requests.append((method, path, body))
        if not request.headers.get("X-User-Id") or not request.headers.get("X-Tenant-Id"):
            return _detail(401, "missing identity")
        if (method, path) in self.failures:
            return _detail(self.failures.pop((method, path)), "injected failure")
        if self.forbid_writes and method != "GET":
            return _detail(403, "Viewers can't change this workspace's data.")
        try:
            return self._route(method, path, body, request)
        except KeyError as exc:
            return _detail(404, f"{exc} not found")

    def _route(self, method: str, path: str, body: Any, request: httpx.Request) -> httpx.Response:
        if path.startswith("/api/v1/connectors/"):
            return self._connectors(method, path.removeprefix("/api/v1/connectors/"), body, request)
        catalog = "/api/v1/catalog"
        if path == f"{catalog}/categories" and method == "GET":
            return _json(200, [self._category(key) for key in sorted(self.categories)])
        if path == f"{catalog}/categories" and method == "POST":
            self.categories.add(body["key"])
            self.category_details[body["key"]] = {"label": body["label"], "parent_key": body.get("parent_key")}
            return _json(201, self._category(body["key"]))
        if (match := re.fullmatch(rf"{catalog}/categories/([^/]+)", path)) and method == "DELETE":
            key = match.group(1)
            if key not in self.categories:
                return _detail(404, f"Category '{key}' not found")
            used = sum(1 for product in self.products.values() if product.get("category") == key)
            if used:
                return _detail(400, f"Category '{key}' is used by {used} product(s); move them to another category first")
            if any(details.get("parent_key") == key for details in self.category_details.values()):
                return _detail(400, f"Category '{key}' is the parent of another category")
            self.categories.discard(key)
            self.category_details.pop(key, None)
            return httpx.Response(204)
        if path == f"{catalog}/describe" and method == "GET":
            names = sorted({str(option["name"]) for product in self.products.values() for option in product.get("options") or []})
            return _json(200, {"categories": [self._category(key) for key in sorted(self.categories)], "option_types": names, "filterable_fields": []})
        if path == f"{catalog}/locations" and method == "GET":
            return _json(200, self.locations)
        if path == f"{catalog}/locations" and method == "POST":
            location = {"id": str(uuid4()), **self._location_fields(body)}
            self.locations.append(location)
            return _json(201, location)
        if match := re.fullmatch(rf"{catalog}/locations/([^/]+)", path):
            location = next((item for item in self.locations if item["id"] == match.group(1)), None)
            if location is None:
                return _detail(400, f"Location '{match.group(1)}' not found")
            if method == "PUT":
                location.update(self._location_fields(body))  # every field is written, like data-pipeline
                return _json(200, location)
            if method == "DELETE":
                levels = [key for key, level in self.stock.items() if key[1] == location["id"]]
                if any(self.stock[key]["on_hand"] > 0 or self.stock[key]["reserved"] > 0 for key in levels):
                    return _detail(400, f"Cannot delete location '{location['name']}' because it contains active inventory")
                for key in levels:
                    del self.stock[key]
                self.movements = [entry for entry in self.movements if entry["location_id"] != location["id"]]
                self.locations.remove(location)
                return httpx.Response(204)
        if path == f"{catalog}/products" and method == "GET":
            return _json(200, self._list_products(request.url.params))
        if path == f"{catalog}/products" and method == "POST":
            if body["category"] not in self.categories:
                return _detail(400, f"Category '{body['category']}' does not exist in tenant vocabulary")
            product = {**body, "id": str(uuid4()), "variants": [], "options": [], "created_at": self._now()}
            product["options"] = _set_options(product, body.get("options") or [])
            self.products[product["id"]] = product
            return _json(201, product)
        if match := re.fullmatch(rf"{catalog}/products/([^/]+)", path):
            product = self.products[match.group(1)]
            if method == "GET":
                return _json(200, product)
            if method == "PUT":
                product.update(body)
                return _json(200, product)
            if method == "DELETE":
                product["status"] = "RETIRED"
                for variant in product["variants"]:
                    variant["status"] = "RETIRED"
                return _json(200, product)
        if (match := re.fullmatch(rf"{catalog}/products/([^/]+)/options", path)) and method == "PUT":
            product = self.products[match.group(1)]
            names = [option["name"] for option in body["options"]]
            if len(set(names)) != len(names):
                return _detail(400, "Each option name may appear only once")
            product["options"] = _set_options(product, body["options"])
            return _json(200, product["options"])
        if (match := re.fullmatch(rf"{catalog}/products/([^/]+)/variants", path)) and method == "POST":
            product = self.products[match.group(1)]
            known = {value["id"]: value for option in product.get("options") or [] for value in option["values"]}
            for incoming in body["variants"]:
                existing = self.variant_by_sku(incoming["sku"])
                if existing is not None and existing["product_id"] != product["id"]:
                    return _detail(400, f"SKU '{incoming['sku']}' already exists for a different product in this tenant")
                kept = {value["id"]: value for value in (existing or {}).get("option_values") or []}
                values = []
                for value_id in incoming.get("option_value_ids") or []:
                    if value_id not in known and value_id not in kept:
                        return _detail(400, "One or more option_value_ids do not belong to this product or tenant")
                    values.append(dict(known.get(value_id) or kept[value_id]))
                fields = {key: incoming.get(key) for key in ("barcode", "price", "currency", "weight", "status")}
                if existing is None:
                    product["variants"].append(
                        {"id": str(uuid4()), "product_id": product["id"], "sku": incoming["sku"], **fields, "option_values": values}
                    )
                else:
                    existing.update(fields, option_values=values)
            return _json(200, product["variants"])
        if match := re.fullmatch(rf"{catalog}/variants/([^/]+)", path):
            variant = self.variant_by_sku(match.group(1))
            return _json(200, variant) if variant else _detail(404, "Variant not found")
        if match := re.fullmatch(rf"{catalog}/variants/([^/]+)/availability", path):
            variant = self.variant_by_sku(match.group(1))
            if variant is None:
                return _detail(404, "Variant not found")
            return _json(200, self._availability(variant))
        if path == f"{catalog}/inventory/availability" and method == "GET":
            wanted = request.url.params.get_list("skus")
            found = [variant for sku in wanted if (variant := self.variant_by_sku(sku))]
            return _json(200, {variant["sku"]: self._availability(variant) for variant in found})
        if path == f"{catalog}/inventory/movements" and method == "POST":
            return self._record_movement(body)
        if path == f"{catalog}/inventory/movements" and method == "GET":
            params = request.url.params
            reasons = params.get_list("reason")
            holds = params.get("include_holds") == "true"
            items = [
                entry
                for entry in reversed(self.movements)
                if (not params.get("variant_id") or entry["variant_id"] == params["variant_id"])
                and (not params.get("location_id") or entry["location_id"] == params["location_id"])
                and (not params.get("ref_id") or entry.get("ref_id") == params["ref_id"])
                and (entry["reason"] in reasons if reasons else holds or entry["reason"] not in ("RESERVE", "RELEASE"))
            ]
            limit, offset = int(params.get("limit") or 50), int(params.get("offset") or 0)
            return _json(200, {"items": items[offset : offset + limit], "total": len(items), "limit": limit, "offset": offset})
        if path == f"{catalog}/inventory/movements/summary" and method == "GET":
            wanted = request.url.params.get("location_id")
            places = [
                {
                    "location_id": location["id"], "location_name": location["name"], "location_type": location.get("type", "WAREHOUSE"),
                    "sellable": location["sellable"],
                    "qty_on_hand": sum(level["on_hand"] for (_, place), level in self.stock.items() if place == location["id"]),
                    "qty_reserved": sum(level["reserved"] for (_, place), level in self.stock.items() if place == location["id"]),
                    "received": sum(e["delta"] for e in self.movements if e["reason"] == "RESTOCK" and e["location_id"] == location["id"]),
                    "sold": -sum(e["delta"] for e in self.movements if e["reason"] == "SALE" and e["location_id"] == location["id"]),
                }
                for location in self.locations
                if not wanted or location["id"] == wanted
            ]
            return _json(200, {"locations": places, "totals": {"movements": len(self.movements)}})
        if path == f"{catalog}/inventory/reserve" and method == "POST":
            variant = self.variant_by_sku(body["sku"])
            if variant is None:
                return _detail(400, "Variant not found")
            wanted, allocations = body["qty"], []
            for location in self.locations:
                if body.get("location_id") and location["id"] != body["location_id"]:
                    continue
                level = self.stock.get((variant["id"], location["id"]))
                if not level:
                    continue
                take = min(wanted, level["on_hand"] - level["reserved"])
                if take > 0:
                    allocations.append((level, location, take))
                    wanted -= take
            if wanted > 0:
                return _detail(400, f"Insufficient stock: requested {body['qty']}")
            reservation_id = str(uuid4())
            for level, location, take in allocations:
                level["reserved"] += take
                self._hold(variant, location, take, "RESERVE", reservation_id, request)
            self.reservations[reservation_id] = {"allocations": allocations, "released": False, "sku": body["sku"], "variant": variant}
            return _json(
                200,
                {
                    "reservation_id": reservation_id,
                    "sku": body["sku"],
                    "requested_qty": body["qty"],
                    "allocated_qty": body["qty"],
                    "allocations": [{"location_id": loc["id"], "location_name": loc["name"], "qty": take} for _, loc, take in allocations],
                },
            )
        if (match := re.fullmatch(rf"{catalog}/inventory/release/([^/]+)", path)) and method == "POST":
            reservation = self.reservations.get(match.group(1))
            if reservation is None:
                return _detail(400, f"No active reservation found with ID '{match.group(1)}'")
            if reservation["released"]:
                return _detail(400, f"Reservation '{match.group(1)}' has already been released")
            for level, location, take in reservation["allocations"]:
                level["reserved"] -= take
                self._hold(reservation["variant"], location, take, "RELEASE", match.group(1), request)
            reservation["released"] = True
            released = sum(take for _, _, take in reservation["allocations"])
            return _json(200, {"reservation_id": match.group(1), "released_qty": released, "movements_count": 1})
        if path.startswith(_VAULT):
            return self._vault(method, path.removeprefix(_VAULT), body, request)
        return _detail(404, f"no route {method} {path}")

    def _connectors(self, method: str, rest: str, body: Any, request: httpx.Request) -> httpx.Response:
        """The connector routes the engine uses (data-pipeline composio_connector/connector_routes.py)."""
        if rest == "status" and method == "GET":
            return _json(200, {"status": "success", "connections": {source: self._connection(source) for source in CONNECTOR_DEFAULTS}})
        source, _, action = rest.partition("/")
        if source not in CONNECTOR_DEFAULTS:
            return _detail(400, f"Unsupported source: {source}")
        connection = self._connection(source)
        if action == "activities" and method == "GET":
            limit = int(request.url.params.get("limit", "20"))
            return _json(200, {"status": "success", "source": source, "activities": self.connector_history.get(source, [])[:limit]})
        if action == "sync-now" and method == "POST":
            if connection["lock"]["is_locked"]:
                return _detail(409, "A sync job is currently running. Please wait.")
            self.syncs_started.append(source)
            return _json(200, {"status": "started", "connection_id": connection["connection_id"]})
        if action == "config" and method == "POST":
            connection["config"] = {**CONNECTOR_DEFAULTS[source], **(body or {})}  # the whole config: unsent fields reset
            self.syncs_started.append(source)  # saving starts a sync
            return _json(200, {"status": "success", "message": "Configuration saved", "connection": connection})
        if action == "auto-sync" and method == "POST":
            connection["config"].update(
                sync_frequency=body["sync_frequency"], auto_sync_interval_minutes=body.get("interval_minutes") or 0,
                auto_sync_enabled=bool(body.get("auto_sync_enabled")), webhook_enabled=bool(body.get("webhook_enabled")),
            )
            return _json(200, {"status": "success", "connection": connection})
        if action == "disconnect" and method == "POST":
            connection["status"] = "Disconnected"
            return _json(200, {"status": "success", "message": f"{source} disconnected. Synced memories preserved."})
        return _detail(404, "Not Found")

    def _vault(self, method: str, path: str, body: Any, request: httpx.Request) -> httpx.Response:
        """The knowledge vault routes (data-pipeline knowledge_vault_routes.py)."""
        user_id = request.headers["X-User-Id"]
        if path == "/upload" and method == "POST":
            name = re.search(rb'filename="([^"]+)"', request.content)
            document = self.add_document(name=name.group(1).decode() if name else "file", user_id=user_id, status="Parsing", chunks=0)
            document["size_bytes"] = len(request.content)
            return _json(200, {"status": "success", "document": document})
        if path == "/documents" and method == "GET":
            params = request.url.params
            listed = [
                doc
                for doc in reversed(self.documents.values())
                if (params.get("status", "all").lower() in ("all", str(doc.get("status")).lower()))
                and (params.get("category", "all").lower() in ("all", str(doc.get("category")).lower()))
                and (not params.get("search") or params["search"].lower() in str(doc.get("name")).lower())
                and (params.get("mine") != "true" or doc.get("user_id") == user_id)
            ]
            return _json(200, {"status": "success", "count": len(listed), "documents": listed})
        if path == "/ingest-url" and method == "POST":
            url = body["url"].strip()
            host = urlsplit(url).hostname or ""
            try:
                internal = not ipaddress.ip_address(host).is_global
            except ValueError:
                internal = "." not in host
            if internal:
                return _detail(400, "Only pages on the public internet can be added to the knowledge vault.")
            if url in self.unreachable_pages:
                return _detail(502, "We could not fetch that page. Check the address and try again.")
            existing = next((doc for doc in self.documents.values() if doc.get("metadata", {}).get("target_url") == url), None)
            if existing is not None:
                # Like data-pipeline: the page is named after its address unless a title is given, and the
                # classifier decides again unless the request overrides it.
                existing.update(
                    name=(body.get("title") or url).strip(), status="Parsing", chunks=0,
                    category=body.get("category") or "GENERAL_RESOURCE", target_competitor=body.get("target_competitor"),
                )
                return _json(200, {"status": "success", "document": existing})
            document = self.add_document(
                name=(body.get("title") or url).strip(), user_id=user_id, doc_id=f"url_{uuid4().hex[:12]}", type="URL",
                status="Parsing", chunks=0, source="URL_INGEST", metadata={"target_url": url},
                category=body.get("category") or "GENERAL_RESOURCE", target_competitor=body.get("target_competitor"),
            )
            return _json(200, {"status": "success", "document": document})
        match = re.fullmatch(r"/documents/([^/]+)(/[a-z-]+)?", path)
        if match is None:
            return _detail(404, f"no route {method} {path}")
        document = self.documents.get(match.group(1))
        if document is None:
            return _detail(404, "Document not found.")
        action = match.group(2)
        if action is None and method == "DELETE":
            del self.documents[document["doc_id"]]
            return _json(200, {"status": "success", "doc_id": document["doc_id"]})
        if action == "/sales-classification" and method == "PATCH":
            if body.get("category") and body["category"].upper() in VAULT_CATEGORIES:
                document["category"] = body["category"].upper()
            for key in ("target_competitor", "target_industry"):
                if body.get(key) is not None:
                    document[key] = body[key].strip() or None
            if body.get("sales_summary") is not None:
                document["sales_summary"] = body["sales_summary"].strip()
            if body.get("sales_tags") is not None:
                document["sales_tags"] = [tag.strip() for tag in body["sales_tags"] if tag.strip()][:8]
            document["classifier_used"] = "manual_user_override"
            return _json(200, {"status": "success", "document": document})
        if action == "/reclassify" and method == "POST":
            document.update(self.classifier_answer, classifier_used="openrouter")
            return _json(200, {"status": "success", "document": document})
        if action == "/reindex" and method == "POST":
            document.update(status="Parsing", chunks=0)
            return _json(200, {"status": "success", "document": document})
        return _detail(404, f"no route {method} {path}")


def _location_named(pipeline: FakeDataPipeline, location_id: str) -> dict[str, Any]:
    return next(location for location in pipeline.locations if location["id"] == location_id)


def _set_options(product: dict[str, Any], options: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """PUT /products/{id}/options: axes and values matched by name keep their ids; SKUs lose only removed values."""
    current = {option["name"]: option for option in product.get("options") or []}
    result = []
    for index, incoming in enumerate(options):
        option = current.get(incoming["name"]) or {"id": str(uuid4()), "name": incoming["name"], "values": []}
        existing = {value["value"]: value for value in option["values"]}
        result.append(
            {
                **option,
                "position": incoming.get("position") or index,
                "values": [
                    {**(existing.get(value["value"]) or {"id": str(uuid4()), "option_id": option["id"], "value": value["value"]}),
                     "position": value.get("position") or order}
                    for order, value in enumerate(incoming.get("values") or [])
                ],
            }
        )
    kept = {value["id"] for option in result for value in option["values"]}
    for variant in product.get("variants") or []:
        variant["option_values"] = [v for v in variant.get("option_values") or [] if v["id"] in kept or not v.get("option_id")]
    return result


def _write(pipeline: FakeDataPipeline, variant: dict[str, Any], location_id: str, delta: int, reason: str, body: dict[str, Any]) -> dict[str, Any]:
    level = pipeline.stock.setdefault((variant["id"], location_id), {"on_hand": 0, "reserved": 0})
    level["on_hand"] += delta
    entry = {
        "id": str(uuid4()), "variant_id": variant["id"], "sku": variant["sku"], "location_id": location_id,
        "location_name": _location_named(pipeline, location_id)["name"], "reason": reason, "delta": delta,
        "type": {"RESTOCK": "RECEIVED", "SALE": "SOLD", "TRANSFER_OUT": "SHIPPED_OUT", "TRANSFER_IN": "SHIPPED_IN",
                 "DAMAGE": "DAMAGED", "LOST": "LOST", "RETURN": "RETURNED"}.get(reason, "CORRECTION"),
        "on_hand_after": level["on_hand"], "reference": body.get("reference"), "counterparty": body.get("counterparty"),
        "note": body.get("note"), "at": pipeline._now(), "product_name": pipeline.products[variant["product_id"]]["name"],
    }
    pipeline.movements.append(entry)
    return entry


def _movement(pipeline: FakeDataPipeline, body: dict[str, Any]) -> httpx.Response:
    """The rules of POST /catalog/inventory/movements (data-pipeline catalog/service.py record_movement)."""
    variant = next((v for p in pipeline.products.values() for v in p["variants"] if v["id"] == body["variant_id"]), None)
    if variant is None:
        return _detail(404, "Variant not found")
    kind, qty, location_id = body["type"], body["qty"], body["location_id"]
    location = _location_named(pipeline, location_id)
    level = pipeline.stock.setdefault((variant["id"], location_id), {"on_hand": 0, "reserved": 0})
    before = {location_id: level["on_hand"]}
    if kind == "COUNT_CORRECTION":
        if not pipeline.corrections_allowed:
            return _detail(403, "Only workspace owners and admins can correct a stock count")
        if not (body.get("note") or "").strip():
            return _detail(400, "Say why the count is being corrected")
        if body.get("expected_on_hand") is not None and body["expected_on_hand"] != level["on_hand"]:
            return _detail(409, f"The stock changed: {level['on_hand']} on hand, not {body['expected_on_hand']}")
        if qty < level["reserved"]:
            return _detail(400, "The count can't go below reserved units")
        if qty != level["on_hand"]:
            _write(pipeline, variant, location_id, qty - level["on_hand"], "ADJUST", body)
    elif qty < 1:
        return _detail(400, "Enter a quantity of at least 1")
    elif kind == "SOLD" and not location["sellable"]:
        return _detail(400, f"{location['name']} is not a sellable location")
    elif kind in ("SOLD", "SHIPPED", "DAMAGED", "LOST") and qty > level["on_hand"] - level["reserved"]:
        return _detail(400, f"Only {level['on_hand'] - level['reserved']} available")
    elif kind == "RECEIVED":
        _write(pipeline, variant, location_id, qty, "RESTOCK", body)
    elif kind in ("SOLD", "DAMAGED", "LOST"):
        _write(pipeline, variant, location_id, -qty, {"SOLD": "SALE", "DAMAGED": "DAMAGE", "LOST": "LOST"}[kind], body)
    elif kind == "SHIPPED":
        target = body["to_location_id"]
        before[target] = pipeline.stock.get((variant["id"], target), {"on_hand": 0})["on_hand"]
        _write(pipeline, variant, location_id, -qty, "TRANSFER_OUT", body)
        _write(pipeline, variant, target, qty, "TRANSFER_IN", body)
    elif kind == "RETURNED":
        _write(pipeline, variant, location_id, qty, "RETURN", body)
        if body.get("resellable") is False:
            _write(pipeline, variant, location_id, -qty, "DAMAGE", body)
    levels = [
        {
            "location_id": place, "location_name": _location_named(pipeline, place)["name"], "qty_on_hand_before": was,
            "qty_on_hand": pipeline.stock[(variant["id"], place)]["on_hand"],
            "qty_reserved": pipeline.stock[(variant["id"], place)]["reserved"], "qty_available": 0,
        }
        for place, was in before.items()
    ]
    return _json(200, {"type": kind, "ref_id": str(uuid4()), "changed": True, "levels": levels, "movements": []})


def stock_of(pipeline: FakeDataPipeline, sku: str, location: str = MAIN_WAREHOUSE) -> dict[str, int]:
    variant = pipeline.variant_by_sku(sku)
    assert variant is not None
    return pipeline.stock.get((variant["id"], location), {"on_hand": 0, "reserved": 0})


def price_of(pipeline: FakeDataPipeline, sku: str) -> Decimal:
    variant = pipeline.variant_by_sku(sku)
    assert variant is not None
    return Decimal(str(variant["price"]))
