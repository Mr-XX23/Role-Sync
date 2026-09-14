from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple, Union
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from billing.charges import charge_catalog_ai
from billing.metering import usage_scope
from billing.preflight import require_credits
from catalog.auth import CatalogContext, get_catalog_context, get_catalog_writer_context
from catalog.database import get_catalog_db
from catalog.schemas import (
    CategoryCreate,
    CategoryResponse,
    ProductCreate,
    ProductUpdate,
    ProductResponse,
    ProductDetailResponse,
    SetOptionsRequest,
    ProductOptionResponse,
    CandidateGridResponse,
    BatchUpsertVariantsRequest,
    VariantResponse,
    LocationCreate,
    LocationResponse,
    SetStockRequest,
    BatchSetStockRequest,
    AdjustStockRequest,
    ReserveStockRequest,
    ReservationResponse,
    ReleaseStockResponse,
    TransferStockRequest,
    TransferStockResponse,
    RecordMovementRequest,
    RecordMovementResponse,
    StockMovementHistoryResponse,
    StockMovementSummaryResponse,
    InventoryLevelResponse,
    VariantAvailabilityResponse,
    CheckAvailabilityResponse,
    DescribeCatalogResponse,
    ValidationReport,
    ImportCommitRequest,
    ImportCommitResponse,
    ImportJobResponse,
    GenerateFindabilityRequest,
    GenerateFindabilityResponse,
    SemanticSearchRequest,
    SemanticSearchResponse,
)
from catalog.service import ProductService
from catalog.stock_movements import StockConflictError, StockPermissionError
from catalog.csv_importer import (
    catalog_import_worker,
    generate_csv_template,
    parse_csv,
)

router = APIRouter(tags=["Catalog & Inventory"])



def get_service(
    db: Session = Depends(get_catalog_db),
) -> ProductService:
    return ProductService(db)


def _stock_change_refused(exc: Exception) -> HTTPException:
    """The HTTP answer to a stock change the service refused."""
    if isinstance(exc, StockPermissionError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    if isinstance(exc, StockConflictError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


# ---------------------------------------------------------------------------
# Describe Catalog (AI Access Tool)
# ---------------------------------------------------------------------------

@router.get("/describe", response_model=DescribeCatalogResponse)
def describe_catalog(
    ctx: CatalogContext = Depends(get_catalog_context),
    service: ProductService = Depends(get_service),
):
    """Describe tenant catalog vocabulary, filterable fields, and option types for AI agents."""
    return service.describe_catalog(ctx.tenant_id)


@router.post("/ai/generate-findability", response_model=GenerateFindabilityResponse)
def generate_product_findability(
    data: GenerateFindabilityRequest,
    background_tasks: BackgroundTasks,
    ctx: CatalogContext = Depends(get_catalog_context),
    service: ProductService = Depends(get_service),
):
    """Auto-generate AI agent findability, keywords, use-cases, and sales intelligence."""
    # Paid model work: a workspace out of credits gets 402 before any model is called.
    require_credits(ctx.tenant_id, ctx.user_id)
    with usage_scope() as usage:
        result = service.generate_findability(
            name=data.name,
            prod_type=data.type,
            category=data.category,
            subcategory=data.subcategory,
            description=data.description,
        )
    # Reported after the response is sent, so billing never slows the answer down.
    background_tasks.add_task(
        charge_catalog_ai, workspace_id=ctx.tenant_id, user_id=ctx.user_id, feature="findability", meter=usage
    )
    return result


@router.post("/ai/semantic-search", response_model=SemanticSearchResponse)
def semantic_search_catalog(
    data: SemanticSearchRequest,
    background_tasks: BackgroundTasks,
    ctx: CatalogContext = Depends(get_catalog_context),
    service: ProductService = Depends(get_service),
):
    """Relevance-ranked catalog search, optionally widened by LLM query expansion."""
    # Search is near-free and never refused for credits; its query expansion is charged.
    with usage_scope() as usage:
        result = service.semantic_search(
            tenant_id=ctx.tenant_id,
            query=data.query,
            limit=data.limit,
            expand=data.expand,
        )
    background_tasks.add_task(
        charge_catalog_ai, workspace_id=ctx.tenant_id, user_id=ctx.user_id, feature="query_expansion", meter=usage
    )
    return result


# ---------------------------------------------------------------------------
# Categories Endpoints
# ---------------------------------------------------------------------------

@router.get("/categories", response_model=List[CategoryResponse])
def list_categories(
    ctx: CatalogContext = Depends(get_catalog_context),
    service: ProductService = Depends(get_service),
):
    """List all categories in the tenant's controlled vocabulary."""
    return service.list_categories(ctx.tenant_id)


@router.post("/categories", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
def upsert_category(
    data: CategoryCreate,
    ctx: CatalogContext = Depends(get_catalog_writer_context),
    service: ProductService = Depends(get_service),
):
    """Add or update a category in the tenant's vocabulary."""
    return service.upsert_category(ctx.tenant_id, data)


@router.delete("/categories/{key}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(
    key: str,
    ctx: CatalogContext = Depends(get_catalog_writer_context),
    service: ProductService = Depends(get_service),
):
    """Remove a category that no product uses and that isn't the parent of another category."""
    try:
        found = service.delete_category(ctx.tenant_id, key)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    if not found:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Category '{key}' not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Products Endpoints
# ---------------------------------------------------------------------------

@router.get("/products", response_model=List[ProductResponse])
def list_products(
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
    limit: int = Query(60, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    ctx: CatalogContext = Depends(get_catalog_context),
    service: ProductService = Depends(get_service),
):
    """List products with filters on status, category, price range, keywords, and availability."""
    return service.list_products(
        tenant_id=ctx.tenant_id,
        status=status,
        category=category,
        subcategory=subcategory,
        type=type,
        min_price=min_price,
        max_price=max_price,
        keywords=keywords,
        target_industry=target_industry,
        in_stock=in_stock,
        location_id=location_id,
        limit=limit,
        offset=offset,
    )


@router.post("/products", response_model=ProductDetailResponse, status_code=status.HTTP_201_CREATED)
def create_product(
    data: ProductCreate,
    ctx: CatalogContext = Depends(get_catalog_writer_context),
    service: ProductService = Depends(get_service),
):
    """Create a new product with options and AI-findability attributes."""
    try:
        return service.upsert_product(
            tenant_id=ctx.tenant_id,
            data=data,
            user_id=ctx.user_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/products/{product_id}", response_model=ProductDetailResponse)
def get_product(
    product_id: UUID,
    ctx: CatalogContext = Depends(get_catalog_context),
    service: ProductService = Depends(get_service),
):
    """Get full product details including options and variants."""
    try:
        return service.get_product(ctx.tenant_id, product_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.put("/products/{product_id}", response_model=ProductDetailResponse)
def update_product(
    product_id: UUID,
    data: ProductUpdate,
    ctx: CatalogContext = Depends(get_catalog_writer_context),
    service: ProductService = Depends(get_service),
):
    """Update product attributes and options."""
    try:
        return service.upsert_product(
            tenant_id=ctx.tenant_id,
            data=data,
            user_id=ctx.user_id,
            product_id=product_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/products/{product_id}", response_model=Union[ProductResponse, Dict[str, Any]])
def delete_product(
    product_id: UUID,
    permanent: bool = Query(
        False,
        description="If True, permanently hard-deletes the product and all dependent variants/stock from database. If False, soft-deletes by setting status to RETIRED.",
    ),
    ctx: CatalogContext = Depends(get_catalog_writer_context),
    service: ProductService = Depends(get_service),
):
    """Delete product: soft-delete (RETIRED) by default, or permanent hard-delete when permanent=True."""
    try:
        if permanent:
            service.hard_delete_product(ctx.tenant_id, product_id)
            return {"status": "DELETED", "id": str(product_id), "permanent": True}
        return service.delete_product(ctx.tenant_id, product_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


# ---------------------------------------------------------------------------
# Product Options Endpoints
# ---------------------------------------------------------------------------

@router.put("/products/{product_id}/options", response_model=List[ProductOptionResponse])
def set_options(
    product_id: UUID,
    payload: SetOptionsRequest,
    ctx: CatalogContext = Depends(get_catalog_writer_context),
    service: ProductService = Depends(get_service),
):
    """Replace all options and values for a product."""
    try:
        return service.set_options(ctx.tenant_id, product_id, payload.options)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ---------------------------------------------------------------------------
# Variant Grid Generator (Candidates)
# ---------------------------------------------------------------------------

@router.get("/products/{product_id}/variant-grid", response_model=CandidateGridResponse)
def generate_variant_grid(
    product_id: UUID,
    ctx: CatalogContext = Depends(get_catalog_context),
    service: ProductService = Depends(get_service),
):
    """Generate Cartesian candidate grid for options without persisting to the database."""
    try:
        return service.generate_variant_grid(ctx.tenant_id, product_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


# ---------------------------------------------------------------------------
# Variants Upsert & Lookup
# ---------------------------------------------------------------------------

@router.post("/products/{product_id}/variants", response_model=List[VariantResponse])
def upsert_variants(
    product_id: UUID,
    payload: BatchUpsertVariantsRequest,
    ctx: CatalogContext = Depends(get_catalog_writer_context),
    service: ProductService = Depends(get_service),
):
    """Persist enabled variants with SKU and price."""
    try:
        return service.upsert_variants(ctx.tenant_id, product_id, payload.variants)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/variants/{sku}", response_model=VariantResponse)
def get_variant(
    sku: str,
    ctx: CatalogContext = Depends(get_catalog_context),
    service: ProductService = Depends(get_service),
):
    """Look up a variant by SKU."""
    try:
        return service.get_variant(ctx.tenant_id, sku)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


# ---------------------------------------------------------------------------
# Locations
# ---------------------------------------------------------------------------

@router.get("/locations", response_model=List[LocationResponse])
def list_locations(
    ctx: CatalogContext = Depends(get_catalog_context),
    service: ProductService = Depends(get_service),
):
    """List all stock locations ordered by priority."""
    return service.list_locations(ctx.tenant_id)


@router.post("/locations", response_model=LocationResponse, status_code=status.HTTP_201_CREATED)
def upsert_location(
    data: LocationCreate,
    ctx: CatalogContext = Depends(get_catalog_writer_context),
    service: ProductService = Depends(get_service),
):
    """Create a new stock location."""
    try:
        return service.upsert_location(ctx.tenant_id, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.put("/locations/{location_id}", response_model=LocationResponse)
def update_location(
    location_id: UUID,
    data: LocationCreate,
    ctx: CatalogContext = Depends(get_catalog_writer_context),
    service: ProductService = Depends(get_service),
):
    """Update an existing stock location."""
    try:
        return service.upsert_location(ctx.tenant_id, data, location_id=location_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/locations/{location_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_location(
    location_id: UUID,
    ctx: CatalogContext = Depends(get_catalog_writer_context),
    service: ProductService = Depends(get_service),
):
    """Delete a stock location (must have zero active inventory)."""
    try:
        service.delete_location(ctx.tenant_id, location_id)
        return None
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ---------------------------------------------------------------------------
# Inventory Ledger & Operations
# ---------------------------------------------------------------------------

@router.post("/inventory/set-stock", response_model=InventoryLevelResponse)
def set_stock(
    payload: SetStockRequest,
    ctx: CatalogContext = Depends(get_catalog_writer_context),
    service: ProductService = Depends(get_service),
):
    """Set the on-hand count and log the delta in the ledger.

    Opening stock for anyone who can edit; replacing an existing count is a count correction,
    for owners and admins only, with a note.
    """
    try:
        inv = service.set_stock(
            tenant_id=ctx.tenant_id,
            variant_id=payload.variant_id,
            location_id=payload.location_id,
            qty=payload.qty,
            reason=payload.reason,
            ref_id=payload.ref_id,
            note=payload.note,
            created_by=ctx.user_id,
            can_correct=ctx.is_admin,
        )
        return InventoryLevelResponse(
            id=inv.id,
            variant_id=inv.variant_id,
            location_id=inv.location_id,
            tenant_id=inv.tenant_id,
            qty_on_hand=inv.qty_on_hand,
            qty_reserved=inv.qty_reserved,
            qty_available=max(0, inv.qty_on_hand - inv.qty_reserved),
            reorder_at=inv.reorder_at,
        )
    except (ValueError, StockPermissionError) as e:
        raise _stock_change_refused(e)


@router.post("/inventory/batch-set-stock", response_model=List[InventoryLevelResponse])
def batch_set_stock(
    payload: BatchSetStockRequest,
    ctx: CatalogContext = Depends(get_catalog_writer_context),
    service: ProductService = Depends(get_service),
):
    """Atomically set stock levels for multiple (variant, location) pairs in a single transaction."""
    try:
        updated_levels = service.batch_set_stock(
            tenant_id=ctx.tenant_id,
            items=payload.items,
            created_by=ctx.user_id,
            can_correct=ctx.is_admin,
        )
        return [
            InventoryLevelResponse(
                id=inv.id,
                variant_id=inv.variant_id,
                location_id=inv.location_id,
                tenant_id=inv.tenant_id,
                qty_on_hand=inv.qty_on_hand,
                qty_reserved=inv.qty_reserved,
                qty_available=max(0, inv.qty_on_hand - inv.qty_reserved),
                reorder_at=inv.reorder_at,
            )
            for inv in updated_levels
        ]
    except (ValueError, StockPermissionError) as e:
        raise _stock_change_refused(e)


@router.post("/inventory/adjust-stock", response_model=InventoryLevelResponse)
def adjust_stock(
    payload: AdjustStockRequest,
    ctx: CatalogContext = Depends(get_catalog_writer_context),
    service: ProductService = Depends(get_service),
):
    """Adjust stock by delta and log to ledger."""
    try:
        inv = service.adjust_stock(
            tenant_id=ctx.tenant_id,
            variant_id=payload.variant_id,
            location_id=payload.location_id,
            delta=payload.delta,
            reason=payload.reason,
            ref_id=payload.ref_id,
            note=payload.note,
            created_by=ctx.user_id,
            can_correct=ctx.is_admin,
        )
        return InventoryLevelResponse(
            id=inv.id,
            variant_id=inv.variant_id,
            location_id=inv.location_id,
            tenant_id=inv.tenant_id,
            qty_on_hand=inv.qty_on_hand,
            qty_reserved=inv.qty_reserved,
            qty_available=max(0, inv.qty_on_hand - inv.qty_reserved),
            reorder_at=inv.reorder_at,
        )
    except (ValueError, StockPermissionError) as e:
        raise _stock_change_refused(e)


@router.post("/inventory/reserve", response_model=ReservationResponse)
def reserve_stock(
    payload: ReserveStockRequest,
    ctx: CatalogContext = Depends(get_catalog_writer_context),
    service: ProductService = Depends(get_service),
):
    """Reserve stock with priority allocation and row-level locking."""
    try:
        return service.reserve(
            tenant_id=ctx.tenant_id,
            sku=payload.sku,
            qty=payload.qty,
            location_id=payload.location_id,
            created_by=ctx.user_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/inventory/release/{reservation_id}", response_model=ReleaseStockResponse)
def release_stock(
    reservation_id: UUID,
    ctx: CatalogContext = Depends(get_catalog_writer_context),
    service: ProductService = Depends(get_service),
):
    """Release a previously reserved stock allocation."""
    try:
        return service.release(ctx.tenant_id, reservation_id, created_by=ctx.user_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/inventory/transfer", response_model=TransferStockResponse)
def transfer_stock(
    payload: TransferStockRequest,
    ctx: CatalogContext = Depends(get_catalog_writer_context),
    service: ProductService = Depends(get_service),
):
    """Transfer stock between locations with paired ledger movements."""
    try:
        return service.transfer(
            tenant_id=ctx.tenant_id,
            sku=payload.sku,
            from_location_id=payload.from_location_id,
            to_location_id=payload.to_location_id,
            qty=payload.qty,
            note=payload.note,
            created_by=ctx.user_id,
            reference=payload.reference,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ---------------------------------------------------------------------------
# Stock Movements
# ---------------------------------------------------------------------------

@router.post("/inventory/movements", response_model=RecordMovementResponse)
def record_stock_movement(
    payload: RecordMovementRequest,
    ctx: CatalogContext = Depends(get_catalog_writer_context),
    service: ProductService = Depends(get_service),
):
    """Record what happened to stock: received, sold, shipped, damaged, lost, returned, or a
    count correction (owners and admins only, with a note)."""
    try:
        return service.record_movement(
            ctx.tenant_id,
            payload,
            created_by=ctx.user_id,
            can_correct=ctx.is_admin,
        )
    except (ValueError, StockPermissionError) as e:
        raise _stock_change_refused(e)


@router.get("/inventory/movements", response_model=StockMovementHistoryResponse)
def list_stock_movements(
    variant_id: Optional[UUID] = None,
    location_id: Optional[UUID] = None,
    reason: Optional[List[str]] = Query(None, description="Ledger reasons to include, e.g. SALE"),
    date_from: Optional[datetime] = Query(None, description="Inclusive"),
    date_to: Optional[datetime] = Query(None, description="Exclusive"),
    include_holds: bool = Query(False, description="Include reservation holds (RESERVE, RELEASE)"),
    ref_id: Optional[UUID] = Query(None, description="Only the rows of one action, e.g. a reservation_id"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    ctx: CatalogContext = Depends(get_catalog_context),
    service: ProductService = Depends(get_service),
):
    """Stock movement history, newest first, by product, location, reason and date."""
    try:
        return service.list_movements(
            ctx.tenant_id,
            variant_id=variant_id,
            location_id=location_id,
            reasons=reason,
            date_from=date_from,
            date_to=date_to,
            include_holds=include_holds,
            ref_id=ref_id,
            limit=limit,
            offset=offset,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/inventory/movements/summary", response_model=StockMovementSummaryResponse)
def summarize_stock_movements(
    variant_id: Optional[UUID] = None,
    location_id: Optional[UUID] = None,
    date_from: Optional[datetime] = Query(None, description="Inclusive"),
    date_to: Optional[datetime] = Query(None, description="Exclusive"),
    ctx: CatalogContext = Depends(get_catalog_context),
    service: ProductService = Depends(get_service),
):
    """Per-location totals received, sold, shipped, damaged, lost, returned and corrected."""
    return service.movement_summary(
        ctx.tenant_id,
        variant_id=variant_id,
        location_id=location_id,
        date_from=date_from,
        date_to=date_to,
    )


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------

@router.get("/inventory/availability", response_model=Dict[str, VariantAvailabilityResponse])
def get_batch_availability(
    skus: Optional[List[str]] = Query(None),
    ctx: CatalogContext = Depends(get_catalog_context),
    service: ProductService = Depends(get_service),
):
    """Get sellable availability and per-location breakdown for multiple or all SKUs in a single call."""
    return service.batch_availability(ctx.tenant_id, skus=skus)


@router.get("/variants/{sku}/availability", response_model=VariantAvailabilityResponse)
def get_availability(
    sku: str,
    ctx: CatalogContext = Depends(get_catalog_context),
    service: ProductService = Depends(get_service),
):
    """Get total sellable availability and per-location breakdown."""
    try:
        return service.availability(ctx.tenant_id, sku)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/variants/{sku}/check-availability", response_model=CheckAvailabilityResponse)
def check_availability(
    sku: str,
    qty: int = Query(1, gt=0),
    location_id: Optional[UUID] = None,
    ctx: CatalogContext = Depends(get_catalog_context),
    service: ProductService = Depends(get_service),
):
    """Check if requested quantity can be fulfilled."""
    try:
        return service.check_availability(
            tenant_id=ctx.tenant_id,
            sku=sku,
            qty=qty,
            location_id=location_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


# ---------------------------------------------------------------------------
# CSV Import Dry-Run Validation
# ---------------------------------------------------------------------------

@router.post("/validate-rows", response_model=ValidationReport)
def validate_rows(
    rows: List[Dict[str, Any]],
    ctx: CatalogContext = Depends(get_catalog_context),
    service: ProductService = Depends(get_service),
):
    """Dry-run validation for CSV import rows without writing to DB."""
    return service.validate_rows(ctx.tenant_id, rows)


# ---------------------------------------------------------------------------
# CSV Import Pipeline Endpoints
# ---------------------------------------------------------------------------

async def _extract_csv_payload(request: Request) -> Tuple[str, bool, bool]:
    """Extract CSV text, skip_invalid, and auto_create_categories from request."""
    content_type = request.headers.get("content-type", "").lower()
    skip_invalid = False
    auto_create_categories = True

    if "skip_invalid" in request.query_params:
        skip_invalid = request.query_params["skip_invalid"].lower() in ("true", "1", "yes")
    if "auto_create_categories" in request.query_params:
        auto_create_categories = request.query_params["auto_create_categories"].lower() in ("true", "1", "yes")

    csv_text = ""
    if "multipart/form-data" in content_type:
        form = await request.form()
        if "file" in form and hasattr(form["file"], "read"):
            file_obj = form["file"]
            content = await file_obj.read()
            csv_text = content.decode("utf-8-sig", errors="replace")
        elif "csv_text" in form:
            csv_text = str(form["csv_text"])
        elif "csv_content" in form:
            csv_text = str(form["csv_content"])

        if "skip_invalid" in form:
            skip_invalid = str(form["skip_invalid"]).lower() in ("true", "1", "yes")
        if "auto_create_categories" in form:
            auto_create_categories = str(form["auto_create_categories"]).lower() in ("true", "1", "yes")

    elif "application/json" in content_type:
        try:
            body = await request.json()
            if isinstance(body, dict):
                csv_text = (
                    body.get("csv_content")
                    or body.get("csv_text")
                    or body.get("content")
                    or ""
                )
                if "skip_invalid" in body:
                    skip_invalid = bool(body["skip_invalid"])
                if "auto_create_categories" in body:
                    auto_create_categories = bool(body["auto_create_categories"])
            elif isinstance(body, str):
                csv_text = body
        except Exception:
            pass
    else:
        body_bytes = await request.body()
        csv_text = body_bytes.decode("utf-8-sig", errors="replace")

    return csv_text, skip_invalid, auto_create_categories


@router.get("/import/template.csv")
def get_csv_template():
    """Download the canonical CSV catalog import template with sample rows and headers."""
    template_content = generate_csv_template()
    return Response(
        content=template_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="catalog_import_template.csv"'
        },
    )


@router.post("/import/validate", response_model=ValidationReport)
async def validate_import_csv(
    request: Request,
    ctx: CatalogContext = Depends(get_catalog_context),
    service: ProductService = Depends(get_service),
):
    """Dry-run validation for CSV file upload or text. Returns preview counts and errors."""
    csv_text, _, auto_create_categories = await _extract_csv_payload(request)
    if not csv_text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No CSV content provided in request",
        )

    try:
        rows = parse_csv(csv_text)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to parse CSV: {str(e)}",
        )

    return service.validate_rows(
        tenant_id=ctx.tenant_id,
        rows=rows,
        auto_create_categories=auto_create_categories,
    )


@router.post(
    "/import/commit",
    response_model=ImportCommitResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def commit_import_job(
    request: Request,
    ctx: CatalogContext = Depends(get_catalog_writer_context),
):
    """Enqueue an async CSV import job and return 202 Accepted with job_id."""
    csv_text, skip_invalid, auto_create_categories = await _extract_csv_payload(request)
    if not csv_text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No CSV content provided in request",
        )

    job = catalog_import_worker.create_job(
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        csv_content=csv_text,
        skip_invalid=skip_invalid,
        auto_create_categories=auto_create_categories,
        can_correct=ctx.is_admin,
    )
    await catalog_import_worker.enqueue(job.job_id)

    return ImportCommitResponse(
        job_id=job.job_id,
        status=job.status,
        message="Import job queued successfully",
    )


@router.get("/import/jobs/{job_id}", response_model=ImportJobResponse)
def get_import_job_status(
    job_id: UUID,
    ctx: CatalogContext = Depends(get_catalog_context),
):
    """Get current status, progress percentage, summary counts, and errors of an import job."""
    job = catalog_import_worker.get_job(job_id, tenant_id=ctx.tenant_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Import job '{job_id}' not found",
        )
    return job

