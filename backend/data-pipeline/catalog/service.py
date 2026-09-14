import itertools
import json
import logging
import os
import re
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from sqlalchemy import case, or_, func, select, text
from sqlalchemy.orm import Session, joinedload, selectinload

from catalog.search_ranking import SearchableProduct, rank_products

from catalog.models import (
    Category,
    Product,
    ProductOption,
    OptionValue,
    Variant,
    VariantOptionValue,
    Location,
    InventoryLevel,
    StockMovement,
    STOCK_MOVEMENT_REASONS,
)
from catalog.stock_movements import (
    HOLD_REASONS,
    MAX_ON_HAND,
    StockConflictError,
    StockPermissionError,
    add_to_totals,
    clean_text,
    empty_totals,
    movement_type,
)
from catalog.schemas import (
    CategoryCreate,
    CategoryResponse,
    ProductCreate,
    ProductUpdate,
    ProductOptionCreate,
    CandidateVariant,
    CandidateGridResponse,
    VariantCreate,
    LocationCreate,
    ReservationAllocation,
    ReservationResponse,
    ReleaseStockResponse,
    TransferStockResponse,
    RecordMovementRequest,
    RecordMovementResponse,
    StockLevelChange,
    StockMovementEntry,
    StockMovementHistoryResponse,
    StockMovementTotals,
    LocationStockSummary,
    StockMovementSummaryResponse,
    LocationAvailability,
    VariantAvailabilityResponse,
    CheckAvailabilityResponse,
    DescribeCatalogResponse,
    RowValidationItem,
    ValidationReport,
    GenerateFindabilityResponse,
    SemanticSearchResponse,
    SemanticMatchItem,
)

logger = logging.getLogger("catalog.service")


class ProductService:
    """Single write authority for products, options, variants, locations, and inventory."""

    def __init__(self, db: Session):
        self.db = db

    # -----------------------------------------------------------------------
    # Categories
    # -----------------------------------------------------------------------

    def upsert_category(self, tenant_id: UUID, data: CategoryCreate) -> Category:
        category = (
            self.db.query(Category)
            .filter(Category.tenant_id == tenant_id, Category.key == data.key)
            .first()
        )
        if category:
            category.label = data.label
            category.parent_key = data.parent_key
        else:
            category = Category(
                tenant_id=tenant_id,
                key=data.key,
                label=data.label,
                parent_key=data.parent_key,
            )
            self.db.add(category)
        self.db.commit()
        self.db.refresh(category)
        return category

    def list_categories(self, tenant_id: UUID) -> List[Category]:
        return (
            self.db.query(Category)
            .filter(Category.tenant_id == tenant_id)
            .order_by(Category.key.asc())
            .all()
        )

    def delete_category(self, tenant_id: UUID, key: str) -> bool:
        """Remove a category nothing uses; ``False`` if the workspace has no such category.

        Products name their category by key, so a category in use (by a product in any status,
        retired ones included) or the parent of another category is kept."""
        category = (
            self.db.query(Category)
            .filter(Category.tenant_id == tenant_id, Category.key == key)
            .first()
        )
        if not category:
            return False
        products = (
            self.db.query(func.count(Product.id))
            .filter(Product.tenant_id == tenant_id, Product.category == key)
            .scalar()
        )
        if products:
            raise ValueError(
                f"Category '{key}' is used by {products} product{'s' if products != 1 else ''}; "
                "move them to another category first"
            )
        children = (
            self.db.query(func.count(Category.id))
            .filter(Category.tenant_id == tenant_id, Category.parent_key == key)
            .scalar()
        )
        if children:
            raise ValueError(
                f"Category '{key}' is the parent of {children} other categor{'ies' if children != 1 else 'y'}"
            )
        self.db.delete(category)
        self.db.commit()
        return True

    # -----------------------------------------------------------------------
    # Products
    # -----------------------------------------------------------------------

    def upsert_product(
        self,
        tenant_id: UUID,
        data: ProductCreate | ProductUpdate,
        user_id: str,
        product_id: Optional[UUID] = None,
    ) -> Product:
        # Validate category if provided
        if getattr(data, "category", None) is not None:
            cat_exists = (
                self.db.query(Category)
                .filter(
                    Category.tenant_id == tenant_id,
                    Category.key == data.category,
                )
                .first()
            )
            if not cat_exists:
                raise ValueError(
                    f"Category '{data.category}' does not exist in tenant vocabulary"
                )

        if product_id:
            product = (
                self.db.query(Product)
                .filter(Product.tenant_id == tenant_id, Product.id == product_id)
                .first()
            )
            if not product:
                raise ValueError(f"Product with id '{product_id}' not found")

            update_data = data.model_dump(exclude_unset=True, exclude={"options"})
            for field, val in update_data.items():
                if hasattr(product, field):
                    setattr(product, field, val)

            options_data = getattr(data, "options", None)
            if options_data is not None:
                self.set_options(tenant_id, product.id, options_data)

            product.version += 1
        else:
            product_dict = data.model_dump(exclude={"options"})
            options_data = getattr(data, "options", None)
            product = Product(
                tenant_id=tenant_id,
                acl=[f"tenant:{tenant_id}", f"user:{user_id}"],
                **product_dict,
            )
            self.db.add(product)
            self.db.flush()

            if options_data:
                self.set_options(tenant_id, product.id, options_data)

        self.db.commit()
        return self.get_product(tenant_id, product.id)

    def get_product(self, tenant_id: UUID, product_id: UUID) -> Product:
        product = (
            self.db.query(Product)
            .options(
                selectinload(Product.options).selectinload(ProductOption.values),
                selectinload(Product.variants).selectinload(Variant.option_values),
            )
            .filter(Product.tenant_id == tenant_id, Product.id == product_id)
            .first()
        )
        if not product:
            raise ValueError(f"Product '{product_id}' not found")
        return product

    def list_products(
        self,
        tenant_id: UUID,
        status: Optional[str] = None,
        category: Optional[str] = None,
        subcategory: Optional[str] = None,
        type: Optional[str] = None,
        min_price: Optional[Decimal] = None,
        max_price: Optional[Decimal] = None,
        keywords: Optional[str] = None,
        target_industry: Optional[str] = None,
        in_stock: Optional[bool] = None,
        location_id: Optional[UUID] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[Product]:
        query = (
            self.db.query(Product)
            .options(
                selectinload(Product.options).selectinload(ProductOption.values),
                selectinload(Product.variants).selectinload(Variant.option_values),
            )
            .filter(Product.tenant_id == tenant_id)
        )

        if status:
            query = query.filter(Product.status == status)

        if category:
            query = query.filter(Product.category == category)

        if subcategory:
            query = query.filter(Product.subcategory == subcategory)

        if type:
            query = query.filter(Product.type == type)

        if target_industry:
            query = query.filter(
                func.array_to_string(Product.target_industries, " ").ilike(
                    f"%{target_industry.strip()}%"
                )
            )

        if keywords:
            raw_kw = keywords.strip()
            kw_pattern = f"%{raw_kw}%"
            full_phrase_conds = [
                Product.name.ilike(kw_pattern),
                Product.description.ilike(kw_pattern),
                Product.ideal_customer_profile.ilike(kw_pattern),
                Product.value_proposition.ilike(kw_pattern),
                func.array_to_string(Product.keywords, " ").ilike(kw_pattern),
                func.array_to_string(Product.use_cases, " ").ilike(kw_pattern),
                func.array_to_string(Product.target_industries, " ").ilike(kw_pattern),
            ]
            stop_words = {
                "a", "an", "the", "for", "in", "on", "at", "to", "of", "and",
                "or", "is", "it", "my", "your", "with", "something", "some",
                "any", "want", "need", "looking", "about", "from", "by",
            }
            tokens = [
                w for w in re.findall(r"\w+", raw_kw.lower())
                if w not in stop_words and len(w) > 1
            ]
            token_conds = []
            for token in tokens:
                tp = f"%{token}%"
                token_conds.append(
                    or_(
                        Product.name.ilike(tp),
                        Product.description.ilike(tp),
                        Product.ideal_customer_profile.ilike(tp),
                        Product.value_proposition.ilike(tp),
                        func.array_to_string(Product.keywords, " ").ilike(tp),
                        func.array_to_string(Product.use_cases, " ").ilike(tp),
                        func.array_to_string(Product.target_industries, " ").ilike(tp),
                    )
                )

            if token_conds:
                query = query.filter(or_(*full_phrase_conds, *token_conds))
            else:
                query = query.filter(or_(*full_phrase_conds))

        # Price and stock filters look at variants. One variant must pass all of them (an item with a
        # SKU under the price that is also in stock), checked in a subquery: joining variants once per
        # filter put the variant table in the query twice, which Postgres refused.
        variant_conditions = []
        if min_price is not None:
            variant_conditions.append(Variant.price >= min_price)
        if max_price is not None:
            variant_conditions.append(Variant.price <= max_price)
        if in_stock is True:
            stocked = (
                select(InventoryLevel.variant_id)
                .join(Location, Location.id == InventoryLevel.location_id)
                .where(
                    InventoryLevel.tenant_id == tenant_id,
                    Location.sellable == True,
                    (InventoryLevel.qty_on_hand - InventoryLevel.qty_reserved) > 0,
                )
            )
            if location_id:
                stocked = stocked.where(Location.id == location_id)
            variant_conditions.append(Variant.id.in_(stocked))
        if variant_conditions:
            matching = select(Variant.product_id).where(Variant.tenant_id == tenant_id, *variant_conditions)
            query = query.filter(Product.id.in_(matching))

        return query.order_by(Product.created_at.desc()).offset(offset).limit(limit).all()

    def delete_product(self, tenant_id: UUID, product_id: UUID) -> Product:
        """Soft delete product by setting status to RETIRED and retire variants strictly within tenant."""
        product = (
            self.db.query(Product)
            .filter(Product.tenant_id == tenant_id, Product.id == product_id)
            .first()
        )
        if not product:
            raise ValueError(f"Product '{product_id}' not found")
        product.status = "RETIRED"
        # Cascade RETIRED status to all variants of this product
        self.db.query(Variant).filter(
            Variant.tenant_id == tenant_id,
            Variant.product_id == product.id,
        ).update({"status": "RETIRED"}, synchronize_session=False)
        self.db.commit()
        self.db.refresh(product)
        return product

    def hard_delete_product(self, tenant_id: UUID, product_id: UUID) -> bool:
        """Permanently hard-delete product and all cascaded child records strictly within tenant."""
        product = (
            self.db.query(Product)
            .filter(Product.tenant_id == tenant_id, Product.id == product_id)
            .first()
        )
        if not product:
            raise ValueError(f"Product '{product_id}' not found")
        self.db.delete(product)
        self.db.commit()
        return True

    # -----------------------------------------------------------------------
    # Options & Candidate Grid Generation
    # -----------------------------------------------------------------------

    def set_options(
        self,
        tenant_id: UUID,
        product_id: UUID,
        options: List[ProductOptionCreate],
    ) -> List[ProductOption]:
        """Make a product's option axes and values exactly ``options``.

        Axes and values are matched by name: one that stays keeps its id, so variants linked to it
        keep their option values (adding "XL" to Size doesn't unlink the existing S, M and L SKUs).
        Only removed axes and values are deleted, which unlinks the variants that used them."""
        product = (
            self.db.query(Product)
            .filter(Product.tenant_id == tenant_id, Product.id == product_id)
            .first()
        )
        if not product:
            raise ValueError(f"Product '{product_id}' not found")

        names = [opt_in.name for opt_in in options]
        if len(set(names)) != len(names):
            raise ValueError("Each option name may appear only once")
        for opt_in in options:
            values = [val_in.value for val_in in opt_in.values]
            if len(set(values)) != len(values):
                raise ValueError(f"Each value of option '{opt_in.name}' may appear only once")

        existing = {
            opt.name: opt
            for opt in self.db.query(ProductOption)
            .options(selectinload(ProductOption.values))
            .filter(ProductOption.tenant_id == tenant_id, ProductOption.product_id == product_id)
        }

        kept_options = set()
        for pos, opt_in in enumerate(options):
            opt = existing.get(opt_in.name)
            if opt is None:
                opt = ProductOption(product_id=product_id, tenant_id=tenant_id, name=opt_in.name)
                self.db.add(opt)
                self.db.flush()
            opt.position = opt_in.position if opt_in.position else pos
            kept_options.add(opt.id)

            current_values = {val.value: val for val in opt.values}
            kept_values = set()
            for val_pos, val_in in enumerate(opt_in.values):
                val = current_values.get(val_in.value)
                if val is None:
                    val = OptionValue(option_id=opt.id, tenant_id=tenant_id, value=val_in.value)
                    self.db.add(val)
                    self.db.flush()
                val.position = val_in.position if val_in.position else val_pos
                kept_values.add(val.id)
            removed_values = [val.id for val in current_values.values() if val.id not in kept_values]
            if removed_values:
                # The database cascades these to the variant links that used them.
                self.db.query(OptionValue).filter(
                    OptionValue.tenant_id == tenant_id, OptionValue.id.in_(removed_values)
                ).delete(synchronize_session=False)

        removed_options = [opt.id for opt in existing.values() if opt.id not in kept_options]
        if removed_options:
            # Cascades to their values and the variant links that used them.
            self.db.query(ProductOption).filter(
                ProductOption.tenant_id == tenant_id, ProductOption.id.in_(removed_options)
            ).delete(synchronize_session=False)

        self.db.commit()
        self.db.expire_all()
        return (
            self.db.query(ProductOption)
            .options(joinedload(ProductOption.values))
            .filter(
                ProductOption.tenant_id == tenant_id,
                ProductOption.product_id == product_id,
            )
            .order_by(ProductOption.position.asc())
            .all()
        )

    def generate_variant_grid(
        self, tenant_id: UUID, product_id: UUID
    ) -> CandidateGridResponse:
        """Compute Cartesian product of options as unpersisted candidates."""
        product = self.get_product(tenant_id, product_id)
        if not product.options:
            return CandidateGridResponse(product_id=product_id, candidates=[])

        # Extract values for each option axis in order
        options_values = [
            [(opt.name, val) for val in sorted(opt.values, key=lambda v: v.position)]
            for opt in sorted(product.options, key=lambda o: o.position)
            if opt.values
        ]

        if not options_values:
            return CandidateGridResponse(product_id=product_id, candidates=[])

        candidates = []
        base_sku_prefix = product.name.upper().replace(" ", "-")[:10]

        for combination in itertools.product(*options_values):
            option_value_ids = [val.id for _, val in combination]
            option_summary = {opt_name: val.value for opt_name, val in combination}
            sku_suffix = "-".join(val.value.upper().replace(" ", "") for _, val in combination)
            suggested_sku = f"{base_sku_prefix}-{sku_suffix}"

            candidates.append(
                CandidateVariant(
                    option_value_ids=option_value_ids,
                    option_summary=option_summary,
                    suggested_sku=suggested_sku,
                )
            )

        return CandidateGridResponse(product_id=product_id, candidates=candidates)

    def upsert_variants(
        self,
        tenant_id: UUID,
        product_id: UUID,
        variants: List[VariantCreate],
    ) -> List[Variant]:
        """Persists only enabled combinations; validates SKU uniqueness per tenant, price >= 0."""
        product = (
            self.db.query(Product)
            .filter(Product.tenant_id == tenant_id, Product.id == product_id)
            .first()
        )
        if not product:
            raise ValueError(f"Product '{product_id}' not found")

        batch_skus = set()
        persisted_variants = []
        for v_in in variants:
            if v_in.price < 0:
                raise ValueError(f"Variant price must be non-negative (got {v_in.price})")

            if v_in.sku in batch_skus:
                raise ValueError(f"Duplicate SKU '{v_in.sku}' in batch")
            batch_skus.add(v_in.sku)

            # Check SKU uniqueness per tenant
            existing = (
                self.db.query(Variant)
                .filter(Variant.tenant_id == tenant_id, Variant.sku == v_in.sku)
                .first()
            )
            if existing and existing.product_id != product_id:
                raise ValueError(
                    f"SKU '{v_in.sku}' already exists for a different product in this tenant"
                )

            # Validate that option_value_ids belong to this product and tenant
            if v_in.option_value_ids:
                valid_count = (
                    self.db.query(OptionValue)
                    .join(ProductOption, ProductOption.id == OptionValue.option_id)
                    .filter(
                        ProductOption.tenant_id == tenant_id,
                        ProductOption.product_id == product_id,
                        OptionValue.id.in_(v_in.option_value_ids),
                    )
                    .count()
                )
                if valid_count != len(v_in.option_value_ids):
                    raise ValueError(
                        "One or more option_value_ids do not belong to this product or tenant"
                    )

            if existing:
                variant = existing
                variant.price = v_in.price
                variant.barcode = v_in.barcode
                variant.weight = v_in.weight
                variant.currency = v_in.currency
                variant.status = v_in.status
            else:
                variant = Variant(
                    product_id=product_id,
                    tenant_id=tenant_id,
                    sku=v_in.sku,
                    barcode=v_in.barcode,
                    price=v_in.price,
                    currency=v_in.currency,
                    weight=v_in.weight,
                    status=v_in.status,
                )
                self.db.add(variant)
                self.db.flush()

            # Associate option values
            self.db.query(VariantOptionValue).filter(
                VariantOptionValue.tenant_id == tenant_id,
                VariantOptionValue.variant_id == variant.id,
            ).delete(synchronize_session=False)

            for opt_val_id in v_in.option_value_ids:
                vov = VariantOptionValue(
                    variant_id=variant.id,
                    option_value_id=opt_val_id,
                    tenant_id=tenant_id,
                )
                self.db.add(vov)

            persisted_variants.append(variant)

        self.db.commit()
        return (
            self.db.query(Variant)
            .options(joinedload(Variant.option_values))
            .filter(
                Variant.tenant_id == tenant_id,
                Variant.product_id == product_id,
            )
            .all()
        )

    def get_variant(self, tenant_id: UUID, sku: str) -> Variant:
        variant = (
            self.db.query(Variant)
            .options(
                joinedload(Variant.product),
                joinedload(Variant.option_values),
            )
            .filter(Variant.tenant_id == tenant_id, Variant.sku == sku)
            .first()
        )
        if not variant:
            raise ValueError(f"Variant with SKU '{sku}' not found")
        return variant

    # -----------------------------------------------------------------------
    # Locations
    # -----------------------------------------------------------------------

    def upsert_location(
        self,
        tenant_id: UUID,
        data: LocationCreate,
        location_id: Optional[UUID] = None,
    ) -> Location:
        if location_id:
            loc = (
                self.db.query(Location)
                .filter(Location.tenant_id == tenant_id, Location.id == location_id)
                .first()
            )
            if not loc:
                raise ValueError(f"Location '{location_id}' not found")
            for k, v in data.model_dump().items():
                setattr(loc, k, v)
        else:
            loc = Location(tenant_id=tenant_id, **data.model_dump())
            self.db.add(loc)

        self.db.commit()
        self.db.refresh(loc)
        return loc

    def list_locations(self, tenant_id: UUID) -> List[Location]:
        return (
            self.db.query(Location)
            .filter(Location.tenant_id == tenant_id)
            .order_by(Location.priority.asc(), Location.name.asc())
            .all()
        )

    def delete_location(self, tenant_id: UUID, location_id: UUID) -> bool:
        loc = (
            self.db.query(Location)
            .filter(Location.tenant_id == tenant_id, Location.id == location_id)
            .first()
        )
        if not loc:
            raise ValueError(f"Location '{location_id}' not found")

        active_inv = (
            self.db.query(InventoryLevel)
            .filter(
                InventoryLevel.tenant_id == tenant_id,
                InventoryLevel.location_id == location_id,
                (InventoryLevel.qty_on_hand > 0) | (InventoryLevel.qty_reserved > 0),
            )
            .first()
        )
        if active_inv:
            raise ValueError(
                f"Cannot delete location '{loc.name}' because it contains active inventory (on-hand or reserved). "
                "Please adjust or transfer the stock to 0 before deleting."
            )

        self.db.query(InventoryLevel).filter(
            InventoryLevel.tenant_id == tenant_id,
            InventoryLevel.location_id == location_id,
        ).delete(synchronize_session=False)

        self.db.delete(loc)
        self.db.commit()
        return True

    # -----------------------------------------------------------------------
    # Inventory Ledger & Operations
    # -----------------------------------------------------------------------

    def _get_or_create_inventory_level(
        self,
        tenant_id: UUID,
        variant_id: UUID,
        location_id: UUID,
        for_update: bool = False,
    ) -> InventoryLevel:
        query = self.db.query(InventoryLevel).filter(
            InventoryLevel.tenant_id == tenant_id,
            InventoryLevel.variant_id == variant_id,
            InventoryLevel.location_id == location_id,
        )
        if for_update:
            query = query.with_for_update()

        inv = query.first()
        if not inv:
            try:
                with self.db.begin_nested():
                    inv = InventoryLevel(
                        variant_id=variant_id,
                        location_id=location_id,
                        tenant_id=tenant_id,
                        qty_on_hand=0,
                        qty_reserved=0,
                    )
                    self.db.add(inv)
                    self.db.flush()
            except Exception:
                # Concurrent insert collision handled gracefully
                pass

            query = self.db.query(InventoryLevel).filter(
                InventoryLevel.tenant_id == tenant_id,
                InventoryLevel.variant_id == variant_id,
                InventoryLevel.location_id == location_id,
            )
            if for_update:
                query = query.with_for_update()
            inv = query.one()
        return inv

    # The rules for changing a count live in catalog.stock_movements.

    def _tenant_variant(self, tenant_id: UUID, variant_id: UUID) -> Variant:
        variant = (
            self.db.query(Variant)
            .filter(Variant.tenant_id == tenant_id, Variant.id == variant_id)
            .first()
        )
        if not variant:
            raise ValueError(f"Variant '{variant_id}' not found")
        return variant

    def _tenant_location(self, tenant_id: UUID, location_id: UUID, label: str = "Location") -> Location:
        location = (
            self.db.query(Location)
            .filter(Location.tenant_id == tenant_id, Location.id == location_id)
            .first()
        )
        if not location:
            raise ValueError(f"{label} '{location_id}' not found")
        return location

    def _lock_levels(
        self, tenant_id: UUID, variant_id: UUID, location_ids: List[UUID]
    ) -> Dict[UUID, InventoryLevel]:
        """Row-lock a variant's stock at each location, always in the same order so that two
        changes touching the same pair of locations can't deadlock."""
        return {
            location_id: self._get_or_create_inventory_level(
                tenant_id, variant_id, location_id, for_update=True
            )
            for location_id in sorted(set(location_ids))
        }

    def _write_movement(
        self,
        inv: InventoryLevel,
        delta: int,
        reason: str,
        *,
        tenant_id: UUID,
        created_by: Optional[str] = None,
        ref_id: Optional[UUID] = None,
        note: Optional[str] = None,
        reference: Optional[str] = None,
        counterparty: Optional[str] = None,
    ) -> StockMovement:
        """Apply ``delta`` to a locked stock level and record it in the ledger."""
        new_qty = inv.qty_on_hand + delta
        if new_qty > MAX_ON_HAND:
            raise ValueError(f"A location can't hold more than {MAX_ON_HAND} units of one item")
        inv.qty_on_hand = new_qty
        movement = StockMovement(
            inv_level_id=inv.id,
            tenant_id=tenant_id,
            delta=delta,
            reason=reason,
            ref_id=ref_id,
            note=note,
            reference=reference,
            counterparty=counterparty,
            on_hand_after=new_qty,
            # Wall-clock time, not the transaction's start: rows written together (a return
            # and its write-off) then list in the order they happened.
            at=func.clock_timestamp(),
            created_by=created_by,
        )
        self.db.add(movement)
        return movement

    @staticmethod
    def _require_available(inv: InventoryLevel, location: Location, qty: int, doing: str) -> None:
        available = inv.qty_on_hand - inv.qty_reserved
        if qty > available:
            raise ValueError(
                f"Insufficient available stock at {location.name}: {max(available, 0)} available "
                f"({inv.qty_on_hand} on hand, {inv.qty_reserved} reserved), so {qty} can't be {doing}"
            )

    @staticmethod
    def _require_correction_rights(can_correct: bool, note: Optional[str]) -> None:
        if not can_correct:
            raise StockPermissionError(
                "Only workspace owners and admins can correct a stock count. Record what happened "
                "instead: stock received, sold, shipped, damaged, lost or returned."
            )
        if not clean_text(note):
            raise ValueError("A count correction needs a note saying why the count is changing")

    def _set_count(
        self,
        inv: InventoryLevel,
        qty: int,
        reason: str,
        *,
        tenant_id: UUID,
        ref_id: Optional[UUID],
        note: Optional[str],
        created_by: Optional[str],
        can_correct: bool,
    ) -> None:
        delta = qty - inv.qty_on_hand
        if delta == 0:
            return
        opening = reason == "RESTOCK" and inv.qty_on_hand == 0
        if not opening:
            self._require_correction_rights(can_correct, note)
        if qty < inv.qty_reserved:
            raise ValueError(
                f"Cannot set qty_on_hand ({qty}) less than reserved ({inv.qty_reserved})"
            )
        self._write_movement(
            inv,
            delta,
            "RESTOCK" if opening else "ADJUST",
            tenant_id=tenant_id,
            created_by=created_by,
            ref_id=ref_id,
            note=clean_text(note) or f"Stock set to {qty} (delta {delta:+d})",
        )

    def set_stock(
        self,
        tenant_id: UUID,
        variant_id: UUID,
        location_id: UUID,
        qty: int,
        reason: str = "RESTOCK",
        ref_id: Optional[UUID] = None,
        note: Optional[str] = None,
        created_by: Optional[str] = None,
        *,
        can_correct: bool = False,
    ) -> InventoryLevel:
        """Set the on-hand count of a variant at a location.

        Where there is no stock yet this is opening stock, recorded as received (RESTOCK).
        Replacing an existing count, or any ``reason="ADJUST"``, is a count correction:
        ``can_correct`` (owners and admins) and a note are required.
        """
        if qty < 0:
            raise ValueError(f"qty cannot be negative (got {qty})")
        self._tenant_variant(tenant_id, variant_id)
        self._tenant_location(tenant_id, location_id)

        try:
            inv = self._get_or_create_inventory_level(
                tenant_id, variant_id, location_id, for_update=True
            )
            self._set_count(
                inv,
                qty,
                reason,
                tenant_id=tenant_id,
                ref_id=ref_id,
                note=note,
                created_by=created_by,
                can_correct=can_correct,
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        self.db.refresh(inv)
        return inv

    def batch_set_stock(
        self,
        tenant_id: UUID,
        items: List[Any],
        created_by: Optional[str] = None,
        *,
        can_correct: bool = False,
    ) -> List[InventoryLevel]:
        """``set_stock`` for many (variant, location) pairs in one transaction: all or nothing."""
        if not items:
            return []

        # Extract IDs
        variant_ids = {getattr(it, "variant_id", None) or it["variant_id"] for it in items}
        location_ids = {getattr(it, "location_id", None) or it["location_id"] for it in items}

        # Validate variant_ids belong to tenant
        db_variants = set(
            v[0]
            for v in self.db.query(Variant.id)
            .filter(Variant.tenant_id == tenant_id, Variant.id.in_(variant_ids))
            .all()
        )
        missing_variants = variant_ids - db_variants
        if missing_variants:
            raise ValueError(f"One or more variants not found in tenant: {missing_variants}")

        # Validate location_ids belong to tenant
        db_locations = set(
            l[0]
            for l in self.db.query(Location.id)
            .filter(Location.tenant_id == tenant_id, Location.id.in_(location_ids))
            .all()
        )
        missing_locations = location_ids - db_locations
        if missing_locations:
            raise ValueError(f"One or more locations not found in tenant: {missing_locations}")

        updated_levels = []
        try:
            for item in items:
                v_id = getattr(item, "variant_id", None) or item["variant_id"]
                l_id = getattr(item, "location_id", None) or item["location_id"]
                qty = getattr(item, "qty", None) if hasattr(item, "qty") else item["qty"]
                reason = getattr(item, "reason", "RESTOCK") if hasattr(item, "reason") else item.get("reason", "RESTOCK")
                ref_id = getattr(item, "ref_id", None) if hasattr(item, "ref_id") else item.get("ref_id")
                note = getattr(item, "note", None) if hasattr(item, "note") else item.get("note")

                if qty < 0:
                    raise ValueError(f"qty cannot be negative (got {qty})")

                inv = self._get_or_create_inventory_level(
                    tenant_id, v_id, l_id, for_update=True
                )
                self._set_count(
                    inv,
                    qty,
                    reason,
                    tenant_id=tenant_id,
                    ref_id=ref_id,
                    note=note,
                    created_by=created_by,
                    can_correct=can_correct,
                )
                updated_levels.append(inv)

            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        for inv in updated_levels:
            self.db.refresh(inv)
        return updated_levels

    def adjust_stock(
        self,
        tenant_id: UUID,
        variant_id: UUID,
        location_id: UUID,
        delta: int,
        reason: str = "ADJUST",
        ref_id: Optional[UUID] = None,
        note: Optional[str] = None,
        created_by: Optional[str] = None,
        *,
        can_correct: bool = False,
    ) -> InventoryLevel:
        """Change the on-hand count of a variant at a location by ``delta``.

        RESTOCK adds; SALE and DAMAGE remove available units (a sale only at a sellable
        location). ADJUST is a count correction: ``can_correct`` and a note are required.
        """
        self._tenant_variant(tenant_id, variant_id)
        location = self._tenant_location(tenant_id, location_id)

        if delta == 0:
            raise ValueError("delta must not be zero")
        if reason == "ADJUST":
            self._require_correction_rights(can_correct, note)
        elif reason == "RESTOCK" and delta < 0:
            raise ValueError("RESTOCK adds stock; lowering a count is a count correction (ADJUST)")
        elif reason in ("SALE", "DAMAGE") and delta > 0:
            raise ValueError(f"{reason} removes stock; raising a count is RESTOCK or a count correction (ADJUST)")
        if reason == "SALE" and not location.sellable:
            raise ValueError(f"{location.name} is not a sellable location, so nothing can be sold from it")

        try:
            inv = self._get_or_create_inventory_level(
                tenant_id, variant_id, location_id, for_update=True
            )
            new_qty = inv.qty_on_hand + delta
            if new_qty < 0:
                raise ValueError(
                    f"Adjustment delta {delta:+d} would result in negative qty_on_hand ({new_qty})"
                )
            if new_qty < inv.qty_reserved:
                raise ValueError(
                    f"Adjustment delta {delta:+d} would result in qty_on_hand ({new_qty}) less than reserved ({inv.qty_reserved})"
                )
            self._write_movement(
                inv,
                delta,
                reason,
                tenant_id=tenant_id,
                created_by=created_by,
                ref_id=ref_id,
                note=clean_text(note) or f"Stock adjusted by {delta:+d} to {new_qty}",
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        self.db.refresh(inv)
        return inv

    def allocate(
        self,
        tenant_id: UUID,
        variant_id: UUID,
        qty: int,
    ) -> List[ReservationAllocation]:
        """Strategy function for multi-location inventory allocation (Section 5).

        Picks the sellable location(s) with qty_available >= qty, ordered by priority ASC.
        If none can fully cover, splits across sellable locations in priority order.
        Raises ValueError if insufficient sellable stock.
        """
        if qty <= 0:
            raise ValueError("Allocation quantity must be strictly greater than 0")

        loc_levels = (
            self.db.query(Location, InventoryLevel)
            .outerjoin(
                InventoryLevel,
                (InventoryLevel.location_id == Location.id)
                & (InventoryLevel.variant_id == variant_id)
                & (InventoryLevel.tenant_id == tenant_id),
            )
            .filter(Location.tenant_id == tenant_id, Location.sellable == True)
            .order_by(Location.priority.asc(), Location.id.asc())
            .all()
        )

        if not loc_levels:
            raise ValueError("No sellable locations configured for this tenant")

        # Check if any single location can fully cover
        for loc, inv in loc_levels:
            avail = max(0, (inv.qty_on_hand - inv.qty_reserved)) if inv else 0
            if avail >= qty:
                return [
                    ReservationAllocation(
                        location_id=loc.id,
                        location_name=loc.name,
                        qty=qty,
                    )
                ]

        # Split across locations in priority order
        total_available = sum(
            max(0, (inv.qty_on_hand - inv.qty_reserved)) if inv else 0
            for _, inv in loc_levels
        )
        if total_available < qty:
            raise ValueError(
                f"Insufficient sellable stock: total available {total_available}, requested {qty}"
            )

        allocations: List[ReservationAllocation] = []
        remaining = qty
        for loc, inv in loc_levels:
            if remaining <= 0:
                break
            avail = max(0, (inv.qty_on_hand - inv.qty_reserved)) if inv else 0
            if avail <= 0:
                continue
            take_qty = min(avail, remaining)
            allocations.append(
                ReservationAllocation(
                    location_id=loc.id,
                    location_name=loc.name,
                    qty=take_qty,
                )
            )
            remaining -= take_qty

        return allocations

    def reserve(
        self,
        tenant_id: UUID,
        sku: str,
        qty: int,
        location_id: Optional[UUID] = None,
        created_by: Optional[str] = None,
    ) -> ReservationResponse:
        """Reserve stock using priority allocation & row-level locking to prevent overselling."""
        if qty <= 0:
            raise ValueError("Reservation quantity must be strictly greater than 0")

        variant = self.get_variant(tenant_id, sku)
        reservation_id = uuid4()

        if location_id is not None:
            # Single explicit location reservation
            loc = (
                self.db.query(Location)
                .filter(Location.tenant_id == tenant_id, Location.id == location_id)
                .first()
            )
            if not loc:
                raise ValueError(f"Location '{location_id}' not found")
            if not loc.sellable:
                raise ValueError(f"Location '{loc.name}' is marked as not sellable")

            inv = self._get_or_create_inventory_level(
                tenant_id, variant.id, location_id, for_update=True
            )
            available = inv.qty_on_hand - inv.qty_reserved
            if available < qty:
                raise ValueError(
                    f"Insufficient stock at location '{loc.name}': available {available}, requested {qty}"
                )

            inv.qty_reserved += qty
            movement = StockMovement(
                inv_level_id=inv.id,
                tenant_id=tenant_id,
                delta=qty,
                reason="RESERVE",
                ref_id=reservation_id,
                note=f"Reserved {qty} units for SKU {sku}",
                on_hand_after=inv.qty_on_hand,
                created_by=created_by,
            )
            self.db.add(movement)
            self.db.commit()
            return ReservationResponse(
                reservation_id=reservation_id,
                sku=sku,
                requested_qty=qty,
                allocated_qty=qty,
                allocations=[
                    ReservationAllocation(
                        location_id=loc.id,
                        location_name=loc.name,
                        qty=qty,
                    )
                ],
            )
        else:
            # Row-lock existing inventory levels for sellable locations in priority order
            sellable_invs = (
                self.db.query(InventoryLevel)
                .join(Location, Location.id == InventoryLevel.location_id)
                .filter(
                    InventoryLevel.tenant_id == tenant_id,
                    InventoryLevel.variant_id == variant.id,
                    Location.sellable == True,
                )
                .order_by(Location.priority.asc(), Location.id.asc())
                .with_for_update()
                .all()
            )

            allocations = self.allocate(tenant_id, variant.id, qty)

            inv_by_loc = {inv.location_id: inv for inv in sellable_invs}
            for alloc in allocations:
                inv = inv_by_loc.get(alloc.location_id)
                if not inv:
                    inv = self._get_or_create_inventory_level(
                        tenant_id, variant.id, alloc.location_id, for_update=True
                    )
                avail = inv.qty_on_hand - inv.qty_reserved
                if avail < alloc.qty:
                    self.db.rollback()
                    raise ValueError(
                        f"Stock changed concurrently at location '{alloc.location_name}': available {avail}, needed {alloc.qty}"
                    )
                inv.qty_reserved += alloc.qty
                movement = StockMovement(
                    inv_level_id=inv.id,
                    tenant_id=tenant_id,
                    delta=alloc.qty,
                    reason="RESERVE",
                    ref_id=reservation_id,
                    note=f"Reserved {alloc.qty} units for SKU {sku}",
                    on_hand_after=inv.qty_on_hand,
                    created_by=created_by,
                )
                self.db.add(movement)

            self.db.commit()
            return ReservationResponse(
                reservation_id=reservation_id,
                sku=sku,
                requested_qty=qty,
                allocated_qty=qty,
                allocations=allocations,
            )

    def release(
        self,
        tenant_id: UUID,
        reservation_id: UUID,
        created_by: Optional[str] = None,
    ) -> ReleaseStockResponse:
        """Release a previously made reservation and decrement qty_reserved."""
        # Prevent double-release
        already_released = (
            self.db.query(StockMovement)
            .filter(
                StockMovement.tenant_id == tenant_id,
                StockMovement.ref_id == reservation_id,
                StockMovement.reason == "RELEASE",
            )
            .first()
        )
        if already_released:
            raise ValueError(
                f"Reservation '{reservation_id}' has already been released"
            )

        movements = (
            self.db.query(StockMovement)
            .filter(
                StockMovement.tenant_id == tenant_id,
                StockMovement.ref_id == reservation_id,
                StockMovement.reason == "RESERVE",
            )
            .all()
        )
        if not movements:
            raise ValueError(
                f"No active reservation found with ID '{reservation_id}'"
            )

        total_released = 0
        for m in movements:
            inv = (
                self.db.query(InventoryLevel)
                .filter(
                    InventoryLevel.id == m.inv_level_id,
                    InventoryLevel.tenant_id == tenant_id,
                )
                .with_for_update()
                .one()
            )
            release_qty = min(m.delta, inv.qty_reserved)
            inv.qty_reserved -= release_qty
            total_released += release_qty

            rel_movement = StockMovement(
                inv_level_id=inv.id,
                tenant_id=tenant_id,
                delta=release_qty,
                reason="RELEASE",
                ref_id=reservation_id,
                note=f"Released {release_qty} units from reservation {reservation_id}",
                on_hand_after=inv.qty_on_hand,
                created_by=created_by,
            )
            self.db.add(rel_movement)

        self.db.commit()
        return ReleaseStockResponse(
            reservation_id=reservation_id,
            released_qty=total_released,
            movements_count=len(movements),
        )

    def _ship(
        self,
        source: InventoryLevel,
        destination: InventoryLevel,
        from_location: Location,
        qty: int,
        *,
        tenant_id: UUID,
        **movement: Any,
    ) -> List[StockMovement]:
        """Move available units between two locked stock levels: a TRANSFER_OUT and a
        TRANSFER_IN row sharing one ref_id."""
        self._require_available(source, from_location, qty, "shipped")
        return [
            self._write_movement(source, -qty, "TRANSFER_OUT", tenant_id=tenant_id, **movement),
            self._write_movement(destination, qty, "TRANSFER_IN", tenant_id=tenant_id, **movement),
        ]

    def transfer(
        self,
        tenant_id: UUID,
        sku: str,
        from_location_id: UUID,
        to_location_id: UUID,
        qty: int,
        note: Optional[str] = None,
        created_by: Optional[str] = None,
        reference: Optional[str] = None,
    ) -> TransferStockResponse:
        """Inter-location inventory transfer with row locking and paired ledger movements."""
        if qty <= 0:
            raise ValueError("Transfer quantity must be greater than 0")
        if from_location_id == to_location_id:
            raise ValueError("Source and destination locations must be distinct")

        variant = self.get_variant(tenant_id, sku)
        from_loc = self._tenant_location(tenant_id, from_location_id, "Source location")
        self._tenant_location(tenant_id, to_location_id, "Destination location")

        transfer_ref = uuid4()
        try:
            levels = self._lock_levels(tenant_id, variant.id, [from_location_id, to_location_id])
            self._ship(
                levels[from_location_id],
                levels[to_location_id],
                from_loc,
                qty,
                tenant_id=tenant_id,
                created_by=created_by,
                ref_id=transfer_ref,
                note=clean_text(note),
                reference=clean_text(reference),
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return TransferStockResponse(
            ref_id=transfer_ref,
            sku=sku,
            from_location_id=from_location_id,
            to_location_id=to_location_id,
            qty=qty,
        )

    # -----------------------------------------------------------------------
    # Stock Movements: record what happened, read the history and totals
    # -----------------------------------------------------------------------

    def record_movement(
        self,
        tenant_id: UUID,
        data: RecordMovementRequest,
        *,
        created_by: Optional[str] = None,
        can_correct: bool = False,
    ) -> RecordMovementResponse:
        """Record one thing that happened to stock at a location (rules: catalog.stock_movements)."""
        kind = data.type
        note = clean_text(data.note)
        movement: Dict[str, Any] = {
            "created_by": created_by,
            "ref_id": uuid4(),
            "note": note,
            "reference": clean_text(data.reference),
            "counterparty": clean_text(data.counterparty),
        }

        variant = self._tenant_variant(tenant_id, data.variant_id)
        location = self._tenant_location(tenant_id, data.location_id)
        places = [location]
        if kind == "COUNT_CORRECTION":
            self._require_correction_rights(can_correct, note)
        elif data.qty < 1:
            raise ValueError("Enter a quantity of at least 1")
        if kind == "SHIPPED":
            if data.to_location_id is None:
                raise ValueError("Choose the location the stock is shipped to")
            if data.to_location_id == data.location_id:
                raise ValueError("Stock can't be shipped to the location it is already at")
            places.append(self._tenant_location(tenant_id, data.to_location_id, "Destination location"))
        if kind == "SOLD" and not location.sellable:
            raise ValueError(
                f"{location.name} is not a sellable location, so nothing can be sold from it. "
                "Ship the stock to a sellable location first."
            )

        try:
            levels = self._lock_levels(tenant_id, variant.id, [place.id for place in places])
            inv = levels[location.id]
            before = {location_id: level.qty_on_hand for location_id, level in levels.items()}
            rows: List[StockMovement] = []

            if kind == "RECEIVED":
                rows.append(self._write_movement(inv, data.qty, "RESTOCK", tenant_id=tenant_id, **movement))
            elif kind in ("SOLD", "DAMAGED", "LOST"):
                reason, doing = {
                    "SOLD": ("SALE", "sold"),
                    "DAMAGED": ("DAMAGE", "written off as damaged"),
                    "LOST": ("LOST", "written off as lost"),
                }[kind]
                self._require_available(inv, location, data.qty, doing)
                rows.append(self._write_movement(inv, -data.qty, reason, tenant_id=tenant_id, **movement))
            elif kind == "SHIPPED":
                rows.extend(
                    self._ship(inv, levels[places[1].id], location, data.qty, tenant_id=tenant_id, **movement)
                )
            elif kind == "RETURNED":
                rows.append(self._write_movement(inv, data.qty, "RETURN", tenant_id=tenant_id, **movement))
                if not data.resellable:
                    # Counted as returned, then written off: back in the building, not sellable.
                    write_off = {**movement, "note": note or "Returned by a customer and can't be sold again"}
                    rows.append(self._write_movement(inv, -data.qty, "DAMAGE", tenant_id=tenant_id, **write_off))
            else:  # COUNT_CORRECTION
                if data.expected_on_hand is not None and data.expected_on_hand != inv.qty_on_hand:
                    raise StockConflictError(
                        f"The stock at {location.name} changed while you were counting: it is now "
                        f"{inv.qty_on_hand}, not {data.expected_on_hand}. Check your count against the "
                        "new figure and save again."
                    )
                if data.qty < inv.qty_reserved:
                    raise ValueError(
                        f"{inv.qty_reserved} units at {location.name} are reserved for customers, so the "
                        f"count can't go below {inv.qty_reserved}. Release those reservations first if "
                        "the units are gone."
                    )
                if data.qty != inv.qty_on_hand:
                    rows.append(
                        self._write_movement(
                            inv, data.qty - inv.qty_on_hand, "ADJUST", tenant_id=tenant_id, **movement
                        )
                    )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        written = [row.id for row in rows]
        found = (
            self._movement_rows(tenant_id)
            .filter(StockMovement.id.in_(written))
            .order_by(StockMovement.at.asc())
            .all()
            if written
            else []
        )
        entries = self._movement_entries(tenant_id, found)
        return RecordMovementResponse(
            type=kind,
            ref_id=movement["ref_id"],
            changed=bool(rows),
            levels=[
                StockLevelChange(
                    location_id=place.id,
                    location_name=place.name,
                    qty_on_hand_before=before[place.id],
                    qty_on_hand=levels[place.id].qty_on_hand,
                    qty_reserved=levels[place.id].qty_reserved,
                    qty_available=max(0, levels[place.id].qty_on_hand - levels[place.id].qty_reserved),
                )
                for place in places
            ],
            movements=entries,
        )

    def _movement_rows(self, tenant_id: UUID):
        """Ledger rows of a tenant with the names a person needs to read them."""
        return (
            self.db.query(
                StockMovement,
                Variant.id.label("variant_id"),
                Variant.sku.label("sku"),
                Product.id.label("product_id"),
                Product.name.label("product_name"),
                Location.id.label("location_id"),
                Location.name.label("location_name"),
            )
            .join(InventoryLevel, InventoryLevel.id == StockMovement.inv_level_id)
            .join(Variant, Variant.id == InventoryLevel.variant_id)
            .join(Product, Product.id == Variant.product_id)
            .join(Location, Location.id == InventoryLevel.location_id)
            .filter(StockMovement.tenant_id == tenant_id, InventoryLevel.tenant_id == tenant_id)
        )

    def _movement_entries(self, tenant_id: UUID, rows: List[Any]) -> List[StockMovementEntry]:
        if not rows:
            return []

        labels: Dict[UUID, List[str]] = {}
        for variant_id, value in (
            self.db.query(VariantOptionValue.variant_id, OptionValue.value)
            .join(OptionValue, OptionValue.id == VariantOptionValue.option_value_id)
            .join(ProductOption, ProductOption.id == OptionValue.option_id)
            .filter(
                VariantOptionValue.tenant_id == tenant_id,
                VariantOptionValue.variant_id.in_({row.variant_id for row in rows}),
            )
            .order_by(ProductOption.position.asc(), OptionValue.position.asc())
        ):
            labels.setdefault(variant_id, []).append(value)

        # The other end of each shipment, which a location filter may have left out.
        shipments = {row[0].ref_id for row in rows if row[0].reason in ("TRANSFER_OUT", "TRANSFER_IN") and row[0].ref_id}
        ends: Dict[tuple, tuple] = {}
        if shipments:
            for ref_id, reason, end_id, end_name in (
                self.db.query(StockMovement.ref_id, StockMovement.reason, Location.id, Location.name)
                .join(InventoryLevel, InventoryLevel.id == StockMovement.inv_level_id)
                .join(Location, Location.id == InventoryLevel.location_id)
                .filter(
                    StockMovement.tenant_id == tenant_id,
                    StockMovement.ref_id.in_(shipments),
                    StockMovement.reason.in_(("TRANSFER_OUT", "TRANSFER_IN")),
                )
            ):
                ends[(ref_id, reason)] = (end_id, end_name)

        entries = []
        for row in rows:
            m = row[0]
            other = None
            if m.reason == "TRANSFER_OUT":
                other = ends.get((m.ref_id, "TRANSFER_IN"))
            elif m.reason == "TRANSFER_IN":
                other = ends.get((m.ref_id, "TRANSFER_OUT"))
            entries.append(
                StockMovementEntry(
                    id=m.id,
                    at=m.at,
                    type=movement_type(m.reason, m.delta),
                    reason=m.reason,
                    delta=m.delta,
                    on_hand_after=m.on_hand_after,
                    variant_id=row.variant_id,
                    sku=row.sku,
                    product_id=row.product_id,
                    product_name=row.product_name,
                    variant_label=" / ".join(labels.get(row.variant_id, [])) or None,
                    location_id=row.location_id,
                    location_name=row.location_name,
                    other_location_id=other[0] if other else None,
                    other_location_name=other[1] if other else None,
                    counterparty=m.counterparty,
                    reference=m.reference,
                    note=m.note,
                    ref_id=m.ref_id,
                    created_by=m.created_by,
                )
            )
        return entries

    def list_movements(
        self,
        tenant_id: UUID,
        *,
        variant_id: Optional[UUID] = None,
        location_id: Optional[UUID] = None,
        reasons: Optional[List[str]] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        include_holds: bool = False,
        ref_id: Optional[UUID] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> StockMovementHistoryResponse:
        """Stock ledger rows, newest first. Reservation holds are left out unless asked for.
        ``ref_id`` keeps only the rows one action wrote (a shipment's two rows, a reservation)."""
        unknown = set(reasons or ()) - set(STOCK_MOVEMENT_REASONS)
        if unknown:
            raise ValueError(f"Unknown movement reason: {', '.join(sorted(unknown))}")

        query = self._movement_rows(tenant_id)
        if variant_id is not None:
            query = query.filter(InventoryLevel.variant_id == variant_id)
        if location_id is not None:
            query = query.filter(InventoryLevel.location_id == location_id)
        if ref_id is not None:
            query = query.filter(StockMovement.ref_id == ref_id)
        if reasons:
            query = query.filter(StockMovement.reason.in_(reasons))
        elif not include_holds:
            query = query.filter(StockMovement.reason.notin_(HOLD_REASONS))
        if date_from is not None:
            query = query.filter(StockMovement.at >= date_from)
        if date_to is not None:
            query = query.filter(StockMovement.at < date_to)

        total = query.count()
        rows = (
            query.order_by(StockMovement.at.desc(), StockMovement.id.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return StockMovementHistoryResponse(
            items=self._movement_entries(tenant_id, rows),
            total=total,
            limit=limit,
            offset=offset,
        )

    def movement_summary(
        self,
        tenant_id: UUID,
        *,
        variant_id: Optional[UUID] = None,
        location_id: Optional[UUID] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> StockMovementSummaryResponse:
        """Per-location totals of what happened to stock in a period, next to current stock."""
        units_in = func.coalesce(func.sum(case((StockMovement.delta > 0, StockMovement.delta), else_=0)), 0)
        units_out = func.coalesce(func.sum(case((StockMovement.delta < 0, -StockMovement.delta), else_=0)), 0)
        moved = (
            self.db.query(
                InventoryLevel.location_id,
                StockMovement.reason,
                units_in,
                units_out,
                func.count(StockMovement.id),
            )
            .join(InventoryLevel, InventoryLevel.id == StockMovement.inv_level_id)
            .filter(
                StockMovement.tenant_id == tenant_id,
                InventoryLevel.tenant_id == tenant_id,
                StockMovement.reason.notin_(HOLD_REASONS),
            )
        )
        stock = self.db.query(
            InventoryLevel.location_id,
            func.coalesce(func.sum(InventoryLevel.qty_on_hand), 0),
            func.coalesce(func.sum(InventoryLevel.qty_reserved), 0),
            func.coalesce(func.sum(func.greatest(0, InventoryLevel.qty_on_hand - InventoryLevel.qty_reserved)), 0),
        ).filter(InventoryLevel.tenant_id == tenant_id)
        places = self.db.query(Location).filter(Location.tenant_id == tenant_id)

        if variant_id is not None:
            moved = moved.filter(InventoryLevel.variant_id == variant_id)
            stock = stock.filter(InventoryLevel.variant_id == variant_id)
        if location_id is not None:
            moved = moved.filter(InventoryLevel.location_id == location_id)
            stock = stock.filter(InventoryLevel.location_id == location_id)
            places = places.filter(Location.id == location_id)
        if date_from is not None:
            moved = moved.filter(StockMovement.at >= date_from)
        if date_to is not None:
            moved = moved.filter(StockMovement.at < date_to)

        totals_by_location: Dict[UUID, Dict[str, int]] = {}
        for place_id, reason, qty_in, qty_out, count in moved.group_by(
            InventoryLevel.location_id, StockMovement.reason
        ):
            add_to_totals(
                totals_by_location.setdefault(place_id, empty_totals()), reason, int(qty_in), int(qty_out), int(count)
            )
        stock_by_location = {
            place_id: (int(on_hand), int(reserved), int(free))
            for place_id, on_hand, reserved, free in stock.group_by(InventoryLevel.location_id)
        }

        overall = empty_totals()
        summaries = []
        for place in places.order_by(Location.priority.asc(), Location.name.asc()):
            totals = totals_by_location.get(place.id, empty_totals())
            on_hand, reserved, free = stock_by_location.get(place.id, (0, 0, 0))
            summaries.append(
                LocationStockSummary(
                    location_id=place.id,
                    location_name=place.name,
                    location_type=place.type,
                    sellable=place.sellable,
                    qty_on_hand=on_hand,
                    qty_reserved=reserved,
                    qty_available=free if place.sellable else 0,
                    **totals,
                )
            )
            for field, value in totals.items():
                overall[field] += value

        return StockMovementSummaryResponse(
            variant_id=variant_id,
            date_from=date_from,
            date_to=date_to,
            locations=summaries,
            totals=StockMovementTotals(**overall),
        )

    # -----------------------------------------------------------------------
    # Availability & AI Access Tools
    # -----------------------------------------------------------------------

    def availability(
        self, tenant_id: UUID, sku: str
    ) -> VariantAvailabilityResponse:
        """Query v_variant_availability view and provide per-location availability breakdown."""
        variant = self.get_variant(tenant_id, sku)

        # Total available from view
        row = self.db.execute(
            text(
                "SELECT qty_available FROM catalog.v_variant_availability "
                "WHERE tenant_id = :tenant_id AND variant_id = :variant_id"
            ),
            {"tenant_id": tenant_id, "variant_id": variant.id},
        ).fetchone()

        total_available = int(row[0]) if row and row[0] is not None else 0

        # Per-location breakdown
        levels = (
            self.db.query(InventoryLevel, Location)
            .join(Location, Location.id == InventoryLevel.location_id)
            .filter(
                InventoryLevel.tenant_id == tenant_id,
                InventoryLevel.variant_id == variant.id,
            )
            .order_by(Location.priority.asc(), Location.name.asc())
            .all()
        )

        by_location: List[LocationAvailability] = []
        for inv, loc in levels:
            by_location.append(
                LocationAvailability(
                    location_id=loc.id,
                    location_name=loc.name,
                    sellable=loc.sellable,
                    priority=loc.priority,
                    qty_on_hand=inv.qty_on_hand,
                    qty_reserved=inv.qty_reserved,
                    qty_available=max(0, inv.qty_on_hand - inv.qty_reserved)
                    if loc.sellable
                    else 0,
                )
            )

        return VariantAvailabilityResponse(
            variant_id=variant.id,
            sku=sku,
            total_available=total_available,
            by_location=by_location,
        )

    def batch_availability(
        self,
        tenant_id: UUID,
        skus: Optional[List[str]] = None,
    ) -> Dict[str, VariantAvailabilityResponse]:
        """Fetch total sellable availability and per-location breakdown for multiple or all SKUs in 1-2 queries."""
        var_query = self.db.query(Variant.id, Variant.sku).filter(Variant.tenant_id == tenant_id)
        if skus:
            clean_skus = [s.strip() for s in skus if s and s.strip()]
            if not clean_skus:
                return {}
            var_query = var_query.filter(Variant.sku.in_(clean_skus))

        variants = var_query.all()
        if not variants:
            return {}

        variant_map = {v[0]: v[1] for v in variants}
        variant_ids = list(variant_map.keys())

        # Query all inventory levels joined with location for these variants
        levels = (
            self.db.query(InventoryLevel, Location)
            .join(Location, Location.id == InventoryLevel.location_id)
            .filter(
                InventoryLevel.tenant_id == tenant_id,
                InventoryLevel.variant_id.in_(variant_ids),
            )
            .order_by(Location.priority.asc(), Location.name.asc())
            .all()
        )

        # Group levels by variant_id
        inv_by_variant: Dict[UUID, List[Tuple[InventoryLevel, Location]]] = {
            v_id: [] for v_id in variant_ids
        }
        for inv, loc in levels:
            if inv.variant_id in inv_by_variant:
                inv_by_variant[inv.variant_id].append((inv, loc))

        result: Dict[str, VariantAvailabilityResponse] = {}
        for v_id, sku in variant_map.items():
            loc_list = inv_by_variant.get(v_id, [])
            by_loc: List[LocationAvailability] = []
            total_avail = 0

            for inv, loc in loc_list:
                loc_avail = (
                    max(0, inv.qty_on_hand - inv.qty_reserved) if loc.sellable else 0
                )
                if loc.sellable:
                    total_avail += loc_avail

                by_loc.append(
                    LocationAvailability(
                        location_id=loc.id,
                        location_name=loc.name,
                        sellable=loc.sellable,
                        priority=loc.priority,
                        qty_on_hand=inv.qty_on_hand,
                        qty_reserved=inv.qty_reserved,
                        qty_available=loc_avail,
                    )
                )

            result[sku] = VariantAvailabilityResponse(
                variant_id=v_id,
                sku=sku,
                total_available=total_avail,
                by_location=by_loc,
            )

        return result

    def check_availability(
        self,
        tenant_id: UUID,
        sku: str,
        qty: int = 1,
        location_id: Optional[UUID] = None,
    ) -> CheckAvailabilityResponse:
        """Check if requested quantity can be fulfilled (total or specific location)."""
        avail_resp = self.availability(tenant_id, sku)
        if location_id is not None:
            loc_match = next(
                (l for l in avail_resp.by_location if l.location_id == location_id),
                None,
            )
            can_fulfill = (
                loc_match is not None
                and loc_match.sellable
                and loc_match.qty_available >= qty
            )
        else:
            can_fulfill = avail_resp.total_available >= qty

        return CheckAvailabilityResponse(
            can_fulfill=can_fulfill,
            sku=sku,
            requested_qty=qty,
            total_available=avail_resp.total_available,
            location_id=location_id,
            by_location=avail_resp.by_location,
        )

    def describe_catalog(self, tenant_id: UUID) -> DescribeCatalogResponse:
        """Describe tenant catalog vocabulary, filterable fields, and option types for AI tools."""
        categories = self.list_categories(tenant_id)
        cat_responses = [CategoryResponse.model_validate(c) for c in categories]
        filterable_fields = [
            "category",
            "subcategory",
            "type",
            "status",
            "min_price",
            "max_price",
            "keywords",
            "target_industry",
            "in_stock",
            "location",
        ]
        option_names = [
            row[0]
            for row in self.db.query(ProductOption.name)
            .filter(ProductOption.tenant_id == tenant_id)
            .distinct()
            .all()
        ]
        return DescribeCatalogResponse(
            categories=cat_responses,
            filterable_fields=filterable_fields,
            option_types=sorted(option_names),
        )

    # -----------------------------------------------------------------------
    # CSV Dry-Run Validation
    # -----------------------------------------------------------------------

    def validate_rows(
        self,
        tenant_id: UUID,
        rows: List[Dict[str, Any]],
        auto_create_categories: bool = False,
    ) -> ValidationReport:
        """Validate flat CSV rows dry-run: checks types, categories, prices, SKUs, writes nothing."""
        categories = {c.key for c in self.list_categories(tenant_id)}
        results: List[RowValidationItem] = []

        # Pre-fetch existing database state for batch
        all_skus = {str(r.get("sku")).strip() for r in rows if r.get("sku")}
        all_locations = {
            str(r.get("location")).strip()
            for r in rows
            if r.get("location") and str(r.get("location")).strip()
        }

        # Query existing variants and their product names
        db_sku_to_prod_name: Dict[str, str] = {}
        if all_skus:
            db_vars = (
                self.db.query(Variant.sku, Product.name)
                .join(Product, Product.id == Variant.product_id)
                .filter(
                    Variant.tenant_id == tenant_id,
                    Variant.sku.in_(all_skus),
                )
                .all()
            )
            db_sku_to_prod_name = {row[0]: row[1] for row in db_vars}

        # Query existing inventory reserved quantities
        db_sku_loc_reserved: Dict[Tuple[str, str], int] = {}
        if all_skus and all_locations:
            db_invs = (
                self.db.query(Variant.sku, Location.name, InventoryLevel.qty_reserved)
                .join(Variant, Variant.id == InventoryLevel.variant_id)
                .join(Location, Location.id == InventoryLevel.location_id)
                .filter(
                    InventoryLevel.tenant_id == tenant_id,
                    Variant.sku.in_(all_skus),
                    Location.name.in_(all_locations),
                )
                .all()
            )
            db_sku_loc_reserved = {(row[0], row[1]): row[2] for row in db_invs}

        seen_skus: Dict[str, str] = {}
        seen_sku_prices: Dict[str, Decimal] = {}
        seen_sku_currencies: Dict[str, str] = {}
        seen_sku_options: Dict[str, Dict[str, str]] = {}
        seen_sku_locations: Set[Tuple[str, str]] = set()
        seen_prod_types: Dict[str, str] = {}
        seen_prod_categories: Dict[str, str] = {}

        valid_count = 0
        error_count = 0

        for idx, row in enumerate(rows):
            errors = []
            warnings = []

            p_name = row.get("product_name") or row.get("name")
            p_type = (row.get("type") or "PRODUCT").upper()
            cat = row.get("category")
            sku = row.get("sku")
            price = row.get("price")
            qty = row.get("qty")
            location = row.get("location")
            reorder_at = row.get("reorder_at")

            p_name_str = str(p_name).strip() if p_name else ""
            sku_str = str(sku).strip() if sku else ""
            loc_str = str(location).strip() if location else ""

            # Required field checks
            if not p_name_str:
                errors.append("product_name is required")
            if not sku_str:
                errors.append("sku is required")
            if p_type not in ("PRODUCT", "SERVICE"):
                errors.append(f"Invalid type '{p_type}'. Must be PRODUCT or SERVICE")
            if not cat:
                errors.append("category is required")
            elif not auto_create_categories and cat not in categories:
                errors.append(f"Category '{cat}' does not exist in tenant vocabulary")

            # Price validation
            parsed_price: Optional[Decimal] = None
            if price is None or str(price).strip() == "":
                errors.append("price is required")
            else:
                try:
                    parsed_price = Decimal(str(price).strip())
                    if parsed_price < 0:
                        errors.append("price must be >= 0")
                except Exception:
                    errors.append(f"Invalid price value '{price}'")

            # Qty validation
            parsed_qty: Optional[int] = None
            if qty is not None and str(qty).strip() != "":
                try:
                    parsed_qty = int(str(qty).strip())
                    if parsed_qty < 0:
                        errors.append("qty must be >= 0")
                except Exception:
                    errors.append(f"Invalid qty value '{qty}'")

            # Reorder point validation
            if reorder_at is not None and str(reorder_at).strip() != "":
                try:
                    r_val = int(str(reorder_at).strip())
                    if r_val < 0:
                        errors.append("reorder_at must be >= 0")
                except Exception:
                    errors.append(f"Invalid reorder_at value '{reorder_at}'")

            # Location and Qty cross-check
            if parsed_qty is not None and parsed_qty > 0 and not loc_str:
                warnings.append(
                    "Quantity specified without location; stock level will not be created until a location is specified."
                )

            # Product-level consistency across rows
            if p_name_str:
                if p_name_str in seen_prod_types and seen_prod_types[p_name_str] != p_type:
                    errors.append(
                        f"Conflicting type for product '{p_name_str}': '{seen_prod_types[p_name_str]}' vs '{p_type}'"
                    )
                else:
                    seen_prod_types[p_name_str] = p_type

                if cat and p_name_str in seen_prod_categories and seen_prod_categories[p_name_str] != cat:
                    errors.append(
                        f"Conflicting category for product '{p_name_str}': '{seen_prod_categories[p_name_str]}' vs '{cat}'"
                    )
                elif cat:
                    seen_prod_categories[p_name_str] = cat

            # Variant-level consistency across rows and against database
            if sku_str:
                # 1. Intra-CSV product name consistency
                if sku_str in seen_skus and seen_skus[sku_str] != p_name_str:
                    errors.append(
                        f"Duplicate SKU '{sku_str}' references multiple product names ('{seen_skus[sku_str]}' vs '{p_name_str}')"
                    )
                else:
                    seen_skus[sku_str] = p_name_str

                # 2. Database cross-check: SKU already belongs to different product in DB
                if sku_str in db_sku_to_prod_name and db_sku_to_prod_name[sku_str] != p_name_str:
                    errors.append(
                        f"SKU '{sku_str}' already belongs to existing product '{db_sku_to_prod_name[sku_str]}' in catalog"
                    )

                # 3. Price consistency for same SKU
                if parsed_price is not None:
                    if sku_str in seen_sku_prices and seen_sku_prices[sku_str] != parsed_price:
                        errors.append(
                            f"Conflicting price for SKU '{sku_str}': '{seen_sku_prices[sku_str]}' vs '{parsed_price}'"
                        )
                    else:
                        seen_sku_prices[sku_str] = parsed_price

                # 4. Currency consistency for same SKU
                currency_val = (row.get("currency") or "USD").strip().upper()
                if sku_str in seen_sku_currencies and seen_sku_currencies[sku_str] != currency_val:
                    errors.append(
                        f"Conflicting currency for SKU '{sku_str}': '{seen_sku_currencies[sku_str]}' vs '{currency_val}'"
                    )
                else:
                    seen_sku_currencies[sku_str] = currency_val

                # 5. Options consistency for same SKU
                row_opts: Dict[str, str] = {}
                for k, v in row.items():
                    if k and k.lower().startswith("option_") and v:
                        opt_key = k[len("option_"):].strip().lower()
                        if opt_key:
                            row_opts[opt_key] = str(v).strip()

                if sku_str in seen_sku_options:
                    for opt_k, opt_v in row_opts.items():
                        if opt_k in seen_sku_options[sku_str] and seen_sku_options[sku_str][opt_k] != opt_v:
                            errors.append(
                                f"Conflicting option '{opt_k}' for SKU '{sku_str}': '{seen_sku_options[sku_str][opt_k]}' vs '{opt_v}'"
                            )
                        else:
                            seen_sku_options[sku_str][opt_k] = opt_v
                else:
                    seen_sku_options[sku_str] = dict(row_opts)

                # 6. Duplicate (SKU, location) in CSV
                if loc_str:
                    pair = (sku_str, loc_str)
                    if pair in seen_sku_locations:
                        errors.append(
                            f"Duplicate (sku, location) combination ('{sku_str}', '{loc_str}')"
                        )
                    else:
                        seen_sku_locations.add(pair)

                # 7. Reserved stock check against DB
                if loc_str and parsed_qty is not None:
                    pair = (sku_str, loc_str)
                    if pair in db_sku_loc_reserved:
                        res_qty = db_sku_loc_reserved[pair]
                        if parsed_qty < res_qty:
                            errors.append(
                                f"Cannot set qty_on_hand ({parsed_qty}) less than reserved ({res_qty}) for SKU '{sku_str}' at '{loc_str}'"
                            )

            is_valid = len(errors) == 0
            if is_valid:
                valid_count += 1
            else:
                error_count += 1

            results.append(
                RowValidationItem(
                    row_index=idx,
                    valid=is_valid,
                    errors=errors,
                    warnings=warnings,
                )
            )

        # Compute preview counts of products/variants to create vs update (ONLY FOR VALID ROWS)
        valid_product_names = {
            str(rows[idx].get("product_name") or rows[idx].get("name")).strip()
            for idx, res in enumerate(results)
            if res.valid and (rows[idx].get("product_name") or rows[idx].get("name"))
        }
        valid_skus = {
            str(rows[idx].get("sku")).strip()
            for idx, res in enumerate(results)
            if res.valid and rows[idx].get("sku")
        }

        existing_product_names = (
            set(
                p[0]
                for p in self.db.query(Product.name)
                .filter(
                    Product.tenant_id == tenant_id,
                    Product.name.in_(valid_product_names),
                )
                .all()
            )
            if valid_product_names
            else set()
        )

        existing_skus = (
            set(
                v[0]
                for v in self.db.query(Variant.sku)
                .filter(
                    Variant.tenant_id == tenant_id,
                    Variant.sku.in_(valid_skus),
                )
                .all()
            )
            if valid_skus
            else set()
        )

        products_to_update = len(existing_product_names)
        products_to_create = len(valid_product_names - existing_product_names)
        variants_to_update = len(existing_skus)
        variants_to_create = len(valid_skus - existing_skus)

        return ValidationReport(
            total_rows=len(rows),
            valid_count=valid_count,
            error_count=error_count,
            products_to_create=products_to_create,
            products_to_update=products_to_update,
            variants_to_create=variants_to_create,
            variants_to_update=variants_to_update,
            row_results=results,
        )

    def generate_findability(
        self,
        name: str,
        prod_type: str = "PRODUCT",
        category: Optional[str] = None,
        subcategory: Optional[str] = None,
        description: Optional[str] = None,
    ) -> GenerateFindabilityResponse:
        """
        Auto-generate AI Agent Findability & Sales Knowledge (keywords, use cases,
        target industries, value proposition, ICP, and discount guardrails)
        using OpenRouter AI LLM with robust local heuristic fallback.
        """
        cat_str = (category or "").strip()
        subcat_str = (subcategory or "").strip()
        desc_str = (description or "").strip()

        # 1. Try OpenRouter AI Generation if API key is present
        api_key = (
            os.environ.get("OPENROUTER_API_KEY")
            or os.environ.get("OPEN_ROUTER_API")
            or os.environ.get("OPENROUTER_API")
            or ""
        ).strip()

        if api_key:
            try:
                import requests

                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "HTTP-Referer": "https://rolesync.ai",
                    "X-Title": "RoleSync Enterprise AI",
                    "Content-Type": "application/json",
                }

                system_prompt = (
                    "You are an expert enterprise sales engineer and autonomous AI agent catalog specialist. "
                    "Analyze the product title, type, category, and description. Generate high-impact sales intelligence "
                    "for autonomous sales agents.\n\n"
                    "Provide:\n"
                    "1. keywords: 5-8 high-intent search keywords/phrases buyer prospects or AI agents use to find this.\n"
                    "2. use_cases: 3-5 real-world practical business/personal use cases.\n"
                    "3. target_industries: 3-5 relevant vertical industries.\n"
                    "4. value_proposition: 1-2 sentence compelling ROI and outcome-focused value proposition.\n"
                    "5. ideal_customer_profile: 1-2 sentence ideal buyer profile (organization size, pain points, buyer persona).\n"
                    "6. min_discount_pct: standard minimum discount allowance (number, default 5.0).\n"
                    "7. max_discount_pct: deal ceiling discount guardrail (number, default 20.0).\n\n"
                    "Respond ONLY with a valid JSON object matching this exact schema without markdown formatting:\n"
                    "{\n"
                    '  "keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5"],\n'
                    '  "use_cases": ["use case 1", "use case 2", "use case 3"],\n'
                    '  "target_industries": ["Tech", "Finance", "Healthcare"],\n'
                    '  "value_proposition": "...",\n'
                    '  "ideal_customer_profile": "...",\n'
                    '  "min_discount_pct": 5.0,\n'
                    '  "max_discount_pct": 20.0\n'
                    "}"
                )

                user_content = (
                    f"Product Name: {name}\n"
                    f"Product Type: {prod_type}\n"
                    f"Category: {cat_str}\n"
                    f"Subcategory: {subcat_str}\n"
                    f"Description: {desc_str[:3000]}"
                )

                candidate_models = [
                    "meta-llama/llama-3.3-70b-instruct:free",
                    "google/gemma-2-9b-it:free",
                    "liquid/lfm-2.5-2.6b:free",
                    "meta-llama/llama-3.1-8b-instruct:free",
                ]

                for model in candidate_models:
                    try:
                        res = requests.post(
                            "https://openrouter.ai/api/v1/chat/completions",
                            headers=headers,
                            json={
                                "model": model,
                                "messages": [
                                    {"role": "system", "content": system_prompt},
                                    {"role": "user", "content": user_content},
                                ],
                                "temperature": 0.3,
                                "max_tokens": 800,
                            },
                            timeout=8,
                        )
                        if res.status_code == 200:
                            data = res.json()
                            content = data["choices"][0]["message"]["content"].strip()
                            clean_json = re.sub(
                                r"^```json\s*|^```\s*|```$", "", content, flags=re.MULTILINE
                            ).strip()
                            parsed = json.loads(clean_json)

                            kw = [str(k).strip() for k in parsed.get("keywords", []) if str(k).strip()]
                            uc = [str(u).strip() for u in parsed.get("use_cases", []) if str(u).strip()]
                            ti = [str(t).strip() for t in parsed.get("target_industries", []) if str(t).strip()]
                            vp = str(parsed.get("value_proposition", "")).strip()
                            icp = str(parsed.get("ideal_customer_profile", "")).strip()

                            min_d = Decimal(str(parsed.get("min_discount_pct", 5.0)))
                            max_d = Decimal(str(parsed.get("max_discount_pct", 20.0)))

                            if kw and vp:
                                return GenerateFindabilityResponse(
                                    keywords=kw[:10],
                                    use_cases=uc[:6],
                                    target_industries=ti[:6],
                                    value_proposition=vp,
                                    ideal_customer_profile=icp,
                                    min_discount_pct=min_d,
                                    max_discount_pct=max_d,
                                )
                    except Exception as model_err:
                        logger.warning(f"OpenRouter model {model} attempt failed: {model_err}")
                        continue
            except Exception as e:
                logger.warning(f"AI findability generation network call failed: {e}")

        # 2. Local Intelligent Heuristic Fallback (deterministic, immediate, robust)
        return self._heuristic_findability(name, prod_type, cat_str, subcat_str, desc_str)

    def _heuristic_findability(
        self,
        name: str,
        prod_type: str,
        category: str,
        subcategory: str,
        description: str,
    ) -> GenerateFindabilityResponse:
        """Heuristic rule-based fallback generating realistic sales intelligence."""
        clean_name = name.strip()
        cat_display = (subcategory or category or "General").replace("_", " ").title()

        # Stop words filter
        stop_words = {
            "a", "an", "the", "for", "in", "on", "at", "to", "of", "and", "or",
            "is", "it", "with", "from", "by", "this", "that", "these", "those",
            "product", "service", "item", "new", "our", "all", "your", "we", "you",
        }

        # Extract tokens from name and description
        tokens = [
            w.lower()
            for w in re.findall(r"[a-zA-Z0-9\-\+]+", f"{clean_name} {category} {subcategory} {description}")
            if len(w) > 2 and w.lower() not in stop_words
        ]

        # Deduplicated keyword set
        seen = set()
        keywords: List[str] = []
        for t in tokens:
            if t not in seen:
                seen.add(t)
                keywords.append(t)
            if len(keywords) >= 6:
                break

        # Always include canonical phrases if name has multiple words
        name_words = clean_name.split()
        if len(name_words) >= 2:
            keywords.insert(0, clean_name.lower())

        # Tailored Use Cases
        if prod_type == "SERVICE":
            use_cases = [
                f"Enterprise {cat_display.lower()} onboarding and custom deployment",
                f"Strategic advisory and technical consulting for {clean_name}",
                "Workflow modernization, governance, and operational scaling",
                "Continuous maintenance, support, and SLA execution",
            ]
        else:
            use_cases = [
                f"Daily operational deployment for {cat_display.lower()} workflows",
                f"High-performance productivity and reliability with {clean_name}",
                "Workforce enablement, ergonomic comfort, and team collaboration",
                "Infrastructure optimization and scalable hardware rollout",
            ]

        # Target Industries based on category keywords
        industry_pool = ["Technology", "Enterprise SaaS", "Financial Services", "Healthcare & Life Sciences", "Professional Services"]
        target_industries = industry_pool[:4]

        # Crafted Value Proposition
        if description and len(description.strip()) > 30:
            first_sentence = description.split(".")[0].strip()
            value_prop = f"Empowers teams with {first_sentence.lower() if not first_sentence.startswith(clean_name) else first_sentence}."
        else:
            value_prop = f"Delivers premium enterprise-grade performance and dependable efficiency with {clean_name} for demanding business operations."

        # Crafted ICP
        if prod_type == "SERVICE":
            icp = f"Mid-to-large enterprise organizations requiring specialized {cat_display.lower()} expertise and SLA-backed execution."
        else:
            icp = f"Commercial teams and growth-focused businesses seeking reliable, high-grade {cat_display.lower()} solutions with rapid ROI."

        return GenerateFindabilityResponse(
            keywords=keywords[:8],
            use_cases=use_cases[:5],
            target_industries=target_industries,
            value_proposition=value_prop,
            ideal_customer_profile=icp,
            min_discount_pct=Decimal("5.0"),
            max_discount_pct=Decimal("20.0"),
        )

    def semantic_search(
        self,
        tenant_id: UUID,
        query: str,
        limit: int = 20,
        expand: bool = True,
    ) -> SemanticSearchResponse:
        """
        Relevance-ranked catalog search (BM25 over weighted product fields, see
        ``catalog.search_ranking``), optionally widened with synonyms from an LLM.
        """
        clean_query = query.strip()
        if not clean_query:
            return SemanticSearchResponse(query="", expanded_terms=[], results=[])

        expanded_terms = self._expand_query(clean_query) if expand else []
        products = (
            self.db.query(Product)
            .options(selectinload(Product.variants))
            .filter(Product.tenant_id == tenant_id, Product.status != "RETIRED")
            .all()
        )
        ranked = rank_products(
            clean_query,
            (
                SearchableProduct(
                    product_id=prod.id,
                    name=prod.name or "",
                    category=prod.category or "",
                    subcategory=prod.subcategory or "",
                    keywords=prod.keywords or [],
                    use_cases=prod.use_cases or [],
                    value_proposition=prod.value_proposition or "",
                    target_industries=prod.target_industries or [],
                    description=prod.description or "",
                    skus=[variant.sku for variant in prod.variants or [] if variant.sku],
                )
                for prod in products
            ),
            expanded_terms=expanded_terms,
            limit=limit,
        )
        return SemanticSearchResponse(
            query=clean_query,
            expanded_terms=expanded_terms,
            results=[
                SemanticMatchItem(
                    product_id=item.product_id,
                    score=item.score,
                    matched_terms=item.matched_terms,
                    rationale=item.rationale,
                )
                for item in ranked
            ],
        )

    @staticmethod
    def _expand_query(query: str) -> List[str]:
        """Up to 6 synonyms or related terms from an OpenRouter model; [] if unavailable."""
        api_key = (
            os.environ.get("OPENROUTER_API_KEY")
            or os.environ.get("OPEN_ROUTER_API")
            or os.environ.get("OPENROUTER_API")
            or ""
        ).strip()
        if not api_key:
            return []
        models = [
            model.strip()
            for model in os.environ.get("CATALOG_QUERY_EXPANSION_MODELS", "nvidia/nemotron-3.5-lightning:free").split(",")
            if model.strip()
        ]
        system_prompt = (
            "You are an expert sales catalog search analyzer. Given a user/customer query, "
            "extract 3-6 high-intent synonyms, related product categories, or search keywords. "
            "Respond ONLY with a JSON object: {\"expanded_terms\": [\"term1\", \"term2\", ...]}"
        )
        try:
            import requests

            res = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "HTTP-Referer": "https://rolesync.ai",
                    "X-Title": "RoleSync Enterprise AI",
                    "Content-Type": "application/json",
                },
                json={
                    "models": models,  # OpenRouter falls through to the next model on errors
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"Customer Query: {query}"},
                    ],
                    "temperature": 0.2,
                    "max_tokens": 150,
                    # Synonyms need no thinking; free reasoning models otherwise spend the whole budget on it.
                    "reasoning": {"enabled": False},
                },
                timeout=float(os.environ.get("CATALOG_QUERY_EXPANSION_TIMEOUT_SECONDS", "6")),
            )
            if res.status_code != 200:
                logger.warning("catalog query expansion: OpenRouter answered %s", res.status_code)
                return []
            content = res.json()["choices"][0]["message"].get("content") or ""
            match = re.search(r"\{.*\}", content, flags=re.DOTALL)
            parsed = json.loads(match.group(0)) if match else {}
        except Exception as exc:
            logger.warning("catalog query expansion failed: %s", exc)
            return []
        raw_terms = parsed.get("expanded_terms", []) if isinstance(parsed, dict) else []
        return [str(term).lower().strip() for term in raw_terms if str(term).strip()][:6]


