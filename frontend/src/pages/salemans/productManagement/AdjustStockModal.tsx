import React, { useState, useEffect, useCallback } from 'react';
import {
  X,
  Package,
  AlertCircle,
  CheckCircle2,
  Loader2,
  ArrowRight,
  History,
  Lock,
  RefreshCw,
} from 'lucide-react';
import {
  catalogApi,
  type Variant,
  type Location,
  type Product,
  type StockMovementType,
  type RecordMovementRequest,
} from '../../../api/catalogApi';
import { useToast } from '../../../context/ToastContext';
import { useAppSelector } from '../../../store';
import { SearchableSelect, type DropdownOption } from './SearchableSelect';
import { ADMIN_ROLES, MOVEMENT_CHOICES, describeVariant, formatLocationType } from './stockMovementLabels';

interface AdjustStockModalProps {
  isOpen: boolean;
  onClose: () => void;
  onStockUpdated: () => void;
  variants: Variant[];
  products: Product[];
  locations: Location[];
  initialVariantId?: string;
  initialLocationId?: string;
  onOpenHistory?: (variantId?: string, locationId?: string) => void;
}

interface Level {
  onHand: number;
  reserved: number;
}

const NO_STOCK: Level = { onHand: 0, reserved: 0 };
const MAX_QTY = 1_000_000_000;

const QUANTITY_LABEL: Record<StockMovementType, string> = {
  RECEIVED: 'Units received',
  SOLD: 'Units sold',
  SHIPPED: 'Units shipped',
  DAMAGED: 'Units damaged',
  LOST: 'Units lost',
  RETURNED: 'Units returned',
  COUNT_CORRECTION: 'Counted quantity',
};

const SUBMIT_LABEL: Record<StockMovementType, string> = {
  RECEIVED: 'Record stock received',
  SOLD: 'Record sale',
  SHIPPED: 'Ship stock',
  DAMAGED: 'Record damaged units',
  LOST: 'Record lost units',
  RETURNED: 'Record return',
  COUNT_CORRECTION: 'Save count correction',
};

const NOTE_PLACEHOLDER: Record<StockMovementType, string> = {
  RECEIVED: 'e.g. Delivery checked, all boxes sealed',
  SOLD: 'e.g. Picked up in store',
  SHIPPED: 'e.g. Restocking the city store',
  DAMAGED: 'e.g. Water damage in aisle 4',
  LOST: 'e.g. Missing after the warehouse move',
  RETURNED: 'e.g. Wrong size ordered',
  COUNT_CORRECTION: 'e.g. Monthly shelf count found 2 fewer units than the system',
};

// Who the stock came from or went to, and the paperwork that goes with it.
const COUNTERPARTY_FIELD: Partial<Record<StockMovementType, { label: string; placeholder: string }>> = {
  RECEIVED: { label: 'Supplier', placeholder: 'e.g. Acme Supply Co.' },
  SOLD: { label: 'Customer', placeholder: 'e.g. Northwind Traders' },
  RETURNED: { label: 'Customer', placeholder: 'e.g. Northwind Traders' },
};
const REFERENCE_FIELD: Partial<Record<StockMovementType, { label: string; placeholder: string }>> = {
  RECEIVED: { label: 'PO / delivery note', placeholder: 'e.g. PO-89410' },
  SOLD: { label: 'Order / invoice no.', placeholder: 'e.g. INV-1234' },
  SHIPPED: { label: 'Shipment / tracking no.', placeholder: 'e.g. SHIP-2231' },
  RETURNED: { label: 'Return / order no.', placeholder: 'e.g. RMA-118' },
};

type ApiError = { response?: { status?: number; data?: { detail?: unknown } }; message?: string };

const errorDetail = (err: unknown, fallback: string): string => {
  const detail = (err as ApiError)?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    const messages = detail.map((d) => (d as { msg?: string })?.msg).filter(Boolean);
    if (messages.length > 0) return messages.join('; ');
  }
  return (err as ApiError)?.message || fallback;
};

const DeltaBadge: React.FC<{ value: number }> = ({ value }) =>
  value === 0 ? (
    <span className="text-muted-foreground">(no change)</span>
  ) : (
    <span className={value > 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'}>
      ({value > 0 ? '+' : '−'}
      {Math.abs(value)})
    </span>
  );

export const AdjustStockModal: React.FC<AdjustStockModalProps> = ({
  isOpen,
  onClose,
  onStockUpdated,
  variants,
  products,
  locations,
  initialVariantId,
  initialLocationId,
  onOpenHistory,
}) => {
  const toast = useToast();
  const role = useAppSelector((state) => state.workspace.currentWorkspace?.role);
  const canWrite = role !== 'VIEWER';
  const canCorrect = ADMIN_ROLES.includes(role ?? '');

  // The parent mounts this modal when it opens, so every open starts from a clean form.
  const [movementType, setMovementType] = useState<StockMovementType>('RECEIVED');
  const [selectedVariantId, setSelectedVariantId] = useState<string>(
    () => initialVariantId || (variants[0]?.id ?? '')
  );
  const [selectedLocationId, setSelectedLocationId] = useState<string>(
    () => initialLocationId || (locations[0]?.id ?? '')
  );
  const [destinationId, setDestinationId] = useState<string>(() => {
    const source = initialLocationId || (locations[0]?.id ?? '');
    return locations.find((l) => l.id !== source)?.id ?? '';
  });
  const [quantity, setQuantity] = useState<string>('');
  const [resellable, setResellable] = useState<boolean>(true);
  const [counterparty, setCounterparty] = useState<string>('');
  const [reference, setReference] = useState<string>('');
  const [note, setNote] = useState<string>('');
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Current stock of the chosen product at every location, fetched fresh for the form.
  // Bumping the reload counter fetches it again.
  const sku = variants.find((v) => v.id === selectedVariantId)?.sku;
  const [reloads, setReloads] = useState(0);
  const [fetched, setFetched] = useState<{ key: string; levels: Record<string, Level> | null } | null>(null);
  const levelsKey = `${sku ?? ''}#${reloads}`;

  useEffect(() => {
    if (!isOpen || !sku) return;
    let cancelled = false;
    catalogApi.getAvailability(sku).then(
      (availability) => {
        if (cancelled) return;
        const next: Record<string, Level> = {};
        availability.by_location.forEach((l) => {
          next[l.location_id] = { onHand: l.qty_on_hand, reserved: l.qty_reserved };
        });
        setFetched({ key: levelsKey, levels: next });
      },
      () => {
        if (!cancelled) setFetched({ key: levelsKey, levels: null });
      }
    );
    return () => {
      cancelled = true;
    };
  }, [isOpen, sku, levelsKey]);

  const reloadLevels = useCallback(() => setReloads((n) => n + 1), []);

  if (!isOpen) return null;

  const levelsState: 'loading' | 'ready' | 'failed' =
    fetched?.key !== levelsKey ? 'loading' : fetched.levels ? 'ready' : 'failed';
  const levels = (levelsState === 'ready' && fetched?.levels) || {};
  const location = locations.find((l) => l.id === selectedLocationId);
  const destination = locations.find((l) => l.id === destinationId);
  const here = levels[selectedLocationId] ?? NO_STOCK;
  const there = levels[destinationId] ?? NO_STOCK;
  const available = Math.max(0, here.onHand - here.reserved);
  const isCorrection = movementType === 'COUNT_CORRECTION';
  const qty = /^\d+$/.test(quantity.trim()) ? Number(quantity.trim()) : null;
  const counterpartyField = COUNTERPARTY_FIELD[movementType];
  const referenceField = REFERENCE_FIELD[movementType];

  const notEnough = () =>
    `Only ${available} available at ${location?.name} (${here.onHand} on hand, ${here.reserved} reserved).`;

  // Why the form can't be saved yet, checked the same way the server checks it.
  const problem = ((): string | null => {
    if (!canWrite) return "Viewers can't change stock in this workspace.";
    if (!selectedVariantId || !location) return 'Choose a product and a location.';
    if (isCorrection && !canCorrect) return 'Only workspace owners and admins can correct a count.';
    if (levelsState === 'loading') return 'Loading current stock…';
    if (levelsState === 'failed') return 'Current stock could not be loaded.';
    if (qty === null) return isCorrection ? 'Enter the quantity you counted.' : 'Enter how many units.';
    if (!isCorrection && qty < 1) return 'Enter a quantity of at least 1.';
    if (qty > MAX_QTY) return 'That quantity is too large.';
    switch (movementType) {
      case 'SOLD':
        if (!location.sellable) {
          return `${location.name} isn't a sellable location. Ship the stock to a sellable location first.`;
        }
        return qty > available ? notEnough() : null;
      case 'DAMAGED':
      case 'LOST':
        return qty > available ? notEnough() : null;
      case 'SHIPPED':
        if (!destination) return 'Choose where the stock is going.';
        if (destination.id === location.id) return 'Choose a different location to ship to.';
        return qty > available ? notEnough() : null;
      case 'COUNT_CORRECTION':
        if (qty < here.reserved) {
          return `${here.reserved} units here are reserved for customers, so the count can't go below ${here.reserved}.`;
        }
        return note.trim() ? null : 'Add a note saying why the count is being corrected.';
      default:
        return null;
    }
  })();

  // What the counts will be once this is saved.
  const preview = ((): { lines: { name: string; before: number; after: number }[]; detail?: string } | null => {
    if (!location || qty === null || levelsState !== 'ready') return null;
    const atSource = (after: number) => ({ name: location.name, before: here.onHand, after });
    switch (movementType) {
      case 'RECEIVED':
        return { lines: [atSource(here.onHand + qty)] };
      case 'SOLD':
      case 'DAMAGED':
      case 'LOST':
        return { lines: [atSource(here.onHand - qty)] };
      case 'SHIPPED':
        return {
          lines:
            destination && destination.id !== location.id
              ? [atSource(here.onHand - qty), { name: destination.name, before: there.onHand, after: there.onHand + qty }]
              : [atSource(here.onHand - qty)],
        };
      case 'RETURNED':
        return resellable
          ? { lines: [atSource(here.onHand + qty)] }
          : {
              lines: [atSource(here.onHand)],
              detail: `${qty} recorded as returned, then written off as damaged.`,
            };
      case 'COUNT_CORRECTION': {
        const difference = qty - here.onHand;
        return {
          lines: [atSource(qty)],
          detail:
            difference === 0
              ? 'Matches the current count, so nothing will change.'
              : `Recorded as a count correction of ${difference > 0 ? '+' : '−'}${Math.abs(difference)} units.`,
        };
      }
      default:
        return null;
    }
  })();

  // Only point out a problem once there's something to point it out about.
  const visibleProblem =
    problem && (qty !== null || (isCorrection && !canCorrect) || !canWrite) && levelsState === 'ready'
      ? problem
      : null;

  const quantityHint = (() => {
    switch (movementType) {
      case 'RECEIVED':
        return 'Added to what is already there';
      case 'RETURNED':
        return resellable ? 'Added back to sellable stock' : 'Counted as returned and written off';
      case 'COUNT_CORRECTION':
        return `Replaces the current count of ${here.onHand}`;
      default:
        return `Up to ${available} available`;
    }
  })();

  const productOptions: DropdownOption[] = variants.map((v) => ({
    value: v.id,
    label: describeVariant(v, products),
    sub: `SKU: ${v.sku}`,
  }));

  const locationOptions: DropdownOption[] = locations.map((loc) => ({
    value: loc.id,
    label: loc.name,
    sub: loc.sellable ? formatLocationType(loc.type) : `${formatLocationType(loc.type)} · not sellable`,
  }));

  const chooseLocation = (id: string) => {
    setSelectedLocationId(id);
    if (id === destinationId) {
      setDestinationId(locations.find((l) => l.id !== id)?.id ?? '');
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (problem || qty === null || !location) {
      setErrorMessage(problem);
      return;
    }

    const payload: RecordMovementRequest = {
      type: movementType,
      variant_id: selectedVariantId,
      location_id: location.id,
      qty,
      note: note.trim() || null,
    };
    if (movementType === 'SHIPPED') payload.to_location_id = destinationId;
    if (movementType === 'RETURNED') payload.resellable = resellable;
    if (isCorrection) payload.expected_on_hand = here.onHand;
    if (counterpartyField) payload.counterparty = counterparty.trim() || null;
    if (referenceField) payload.reference = reference.trim() || null;

    setIsSubmitting(true);
    setErrorMessage(null);
    try {
      const result = await catalogApi.recordMovement(payload);
      const title = MOVEMENT_CHOICES.find((c) => c.type === movementType)?.label ?? 'Stock updated';
      let message = result.levels
        .map((l) => `${l.location_name}: ${l.qty_on_hand_before} → ${l.qty_on_hand}`)
        .join(' · ');
      if (!result.changed) message = 'The count already matched, so nothing changed.';
      if (movementType === 'RETURNED' && !resellable) {
        message = `${qty} returned units written off as damaged at ${location.name}.`;
      }
      toast.success(message, title);
      onStockUpdated();
      onClose();
    } catch (err) {
      const msg = errorDetail(err, 'Failed to update stock.');
      setErrorMessage(msg);
      toast.error(msg, 'Stock not updated');
      if ((err as ApiError)?.response?.status === 409) {
        // Someone changed this stock meanwhile: show the new figure.
        reloadLevels();
        onStockUpdated();
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const inputClass =
    'w-full px-3 py-2.5 text-xs rounded-xl bg-background border border-border/80 text-foreground focus:outline-hidden focus:ring-2 focus:ring-primary/40';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-xs animate-in fade-in duration-200">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="update-stock-title"
        className="relative w-full max-w-2xl bg-card border border-border/80 rounded-2xl shadow-2xl overflow-visible flex flex-col max-h-[90vh]"
      >
        {/* Header */}
        <div className="px-6 py-4 border-b border-border/60 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center text-primary">
              <Package className="w-5 h-5" />
            </div>
            <div>
              <h3 id="update-stock-title" className="font-semibold text-foreground text-base">
                Update Stock
              </h3>
              <p className="text-xs text-muted-foreground">Record what happened to stock at a location</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-5 overflow-y-auto">
          {errorMessage && (
            <div
              role="alert"
              className="p-3 rounded-xl bg-destructive/10 border border-destructive/25 text-destructive text-xs flex items-start gap-2"
            >
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              <span>{errorMessage}</span>
            </div>
          )}

          {/* What happened */}
          <fieldset>
            <legend className="block text-xs font-medium text-foreground mb-2">What happened?</legend>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
              {MOVEMENT_CHOICES.map((choice) => {
                const Icon = choice.icon;
                const locked = choice.type === 'COUNT_CORRECTION' && !canCorrect;
                const selected = movementType === choice.type;
                return (
                  <button
                    key={choice.type}
                    type="button"
                    aria-pressed={selected}
                    disabled={locked}
                    onClick={() => {
                      setMovementType(choice.type);
                      setErrorMessage(null);
                    }}
                    className={`p-2.5 rounded-xl border text-left transition-all flex items-start gap-2 ${
                      selected
                        ? 'border-primary ring-2 ring-primary/25 bg-primary/5'
                        : 'border-border/80 bg-background'
                    } ${
                      locked ? 'opacity-60 cursor-not-allowed' : 'cursor-pointer hover:border-primary/40 hover:bg-muted/40'
                    }`}
                  >
                    <Icon className={`w-4 h-4 shrink-0 mt-0.5 ${selected ? 'text-primary' : 'text-muted-foreground'}`} />
                    <span className="min-w-0">
                      <span className={`block text-xs font-semibold ${selected ? 'text-primary' : 'text-foreground'}`}>
                        {choice.label}
                      </span>
                      <span className="flex items-center gap-1 text-[11px] text-muted-foreground mt-0.5">
                        {locked && <Lock className="w-3 h-3 shrink-0" />}
                        {locked ? 'Owners & admins only' : choice.hint}
                      </span>
                    </span>
                  </button>
                );
              })}
            </div>
          </fieldset>

          {/* Product & location */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label htmlFor="stock-product" className="block text-xs font-medium text-foreground mb-1.5">
                Product
              </label>
              <SearchableSelect
                id="stock-product"
                options={productOptions}
                value={selectedVariantId}
                onChange={setSelectedVariantId}
                placeholder="Select a product…"
                searchable
              />
            </div>
            <div>
              <label htmlFor="stock-location" className="block text-xs font-medium text-foreground mb-1.5">
                {movementType === 'SHIPPED' ? 'From location' : 'Location'}
              </label>
              <SearchableSelect
                id="stock-location"
                options={locationOptions}
                value={selectedLocationId}
                onChange={chooseLocation}
                placeholder="Select a location…"
              />
            </div>
          </div>

          {/* Current stock where it happened */}
          {location && sku && (
            <div className="px-3.5 py-2.5 rounded-xl bg-muted/40 border border-border/60 flex flex-wrap items-center justify-between gap-2 text-xs">
              {levelsState === 'loading' ? (
                <span className="flex items-center gap-2 text-muted-foreground">
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  Loading current stock…
                </span>
              ) : levelsState === 'failed' ? (
                <span className="flex items-center gap-2 text-destructive">
                  Couldn't load current stock.
                  <button
                    type="button"
                    onClick={reloadLevels}
                    className="underline inline-flex items-center gap-1 cursor-pointer"
                  >
                    <RefreshCw className="w-3 h-3" />
                    Retry
                  </button>
                </span>
              ) : (
                <span className="flex flex-wrap items-center gap-x-3 gap-y-1 text-muted-foreground">
                  <span>Now at {location.name}:</span>
                  <span>
                    <strong className="text-foreground font-semibold">{here.onHand}</strong> on hand
                  </span>
                  <span>
                    <strong className={`font-semibold ${here.reserved > 0 ? 'text-amber-500' : 'text-foreground'}`}>
                      {here.reserved}
                    </strong>{' '}
                    reserved
                  </span>
                  <span>
                    <strong className="text-foreground font-semibold">{available}</strong> available
                  </span>
                </span>
              )}
              {onOpenHistory && (
                <button
                  type="button"
                  onClick={() => onOpenHistory(selectedVariantId, selectedLocationId)}
                  className="text-primary hover:underline font-medium inline-flex items-center gap-1 cursor-pointer"
                >
                  <History className="w-3.5 h-3.5" />
                  History
                </button>
              )}
            </div>
          )}

          {/* Where a shipment goes */}
          {movementType === 'SHIPPED' && (
            <div>
              <label htmlFor="stock-destination" className="block text-xs font-medium text-foreground mb-1.5">
                To location
              </label>
              <SearchableSelect
                id="stock-destination"
                options={locationOptions.filter((o) => o.value !== selectedLocationId)}
                value={destinationId}
                onChange={setDestinationId}
                placeholder="Where is the stock going?"
              />
              {destination && levelsState === 'ready' && (
                <span className="text-[11px] text-muted-foreground mt-1 block">
                  {there.onHand} on hand at {destination.name} now
                </span>
              )}
            </div>
          )}

          {/* Quantity, and for a return whether it can be sold again */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label htmlFor="stock-qty" className="block text-xs font-medium text-foreground mb-1.5">
                {QUANTITY_LABEL[movementType]}
              </label>
              <input
                id="stock-qty"
                type="number"
                inputMode="numeric"
                min={isCorrection ? 0 : 1}
                step={1}
                value={quantity}
                onChange={(e) => setQuantity(e.target.value)}
                className={inputClass}
                placeholder={isCorrection ? `e.g. ${here.onHand}` : 'e.g. 20'}
              />
              <span className="text-[11px] text-muted-foreground mt-1 block">{quantityHint}</span>
            </div>

            {movementType === 'RETURNED' && (
              <div>
                <span id="stock-resellable" className="block text-xs font-medium text-foreground mb-1.5">
                  Can these units be sold again?
                </span>
                <div role="radiogroup" aria-labelledby="stock-resellable" className="grid grid-cols-2 gap-2">
                  {[
                    { value: true, label: 'Yes, back to stock' },
                    { value: false, label: 'No, write off' },
                  ].map((option) => (
                    <button
                      key={option.label}
                      type="button"
                      role="radio"
                      aria-checked={resellable === option.value}
                      onClick={() => setResellable(option.value)}
                      className={`px-3 py-2.5 text-xs rounded-xl border transition-all cursor-pointer ${
                        resellable === option.value
                          ? 'border-primary ring-2 ring-primary/25 bg-primary/5 text-primary font-semibold'
                          : 'border-border/80 bg-background text-foreground hover:bg-muted/40'
                      }`}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Who and which paperwork */}
          {(counterpartyField || referenceField) && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {counterpartyField && (
                <div>
                  <label htmlFor="stock-counterparty" className="block text-xs font-medium text-foreground mb-1.5">
                    {counterpartyField.label} <span className="text-muted-foreground font-normal">(optional)</span>
                  </label>
                  <input
                    id="stock-counterparty"
                    type="text"
                    maxLength={255}
                    value={counterparty}
                    onChange={(e) => setCounterparty(e.target.value)}
                    placeholder={counterpartyField.placeholder}
                    className={inputClass}
                  />
                </div>
              )}
              {referenceField && (
                <div>
                  <label htmlFor="stock-reference" className="block text-xs font-medium text-foreground mb-1.5">
                    {referenceField.label} <span className="text-muted-foreground font-normal">(optional)</span>
                  </label>
                  <input
                    id="stock-reference"
                    type="text"
                    maxLength={255}
                    value={reference}
                    onChange={(e) => setReference(e.target.value)}
                    placeholder={referenceField.placeholder}
                    className={inputClass}
                  />
                </div>
              )}
            </div>
          )}

          <div>
            <label htmlFor="stock-note" className="block text-xs font-medium text-foreground mb-1.5">
              {isCorrection ? 'Why is the count being corrected?' : 'Note'}{' '}
              <span className="text-muted-foreground font-normal">{isCorrection ? '(required)' : '(optional)'}</span>
            </label>
            <textarea
              id="stock-note"
              rows={2}
              maxLength={1000}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder={NOTE_PLACEHOLDER[movementType]}
              className={`${inputClass} resize-none`}
            />
          </div>

          {/* What the counts will be */}
          {(preview || visibleProblem) && (
            <div
              className={`p-3.5 rounded-xl border text-xs space-y-1.5 ${
                visibleProblem ? 'border-amber-500/30 bg-amber-500/5' : 'border-border/60 bg-muted/30'
              }`}
            >
              {preview?.lines.map((line) => (
                <div key={line.name} className="flex items-center justify-between gap-3">
                  <span className="text-muted-foreground truncate">{line.name}</span>
                  <span className="flex items-center gap-2 font-mono shrink-0">
                    <span className="text-muted-foreground">{line.before}</span>
                    <ArrowRight className="w-3.5 h-3.5 text-primary" />
                    <span className={`font-semibold ${line.after < 0 ? 'text-destructive' : 'text-foreground'}`}>
                      {line.after}
                    </span>
                    <DeltaBadge value={line.after - line.before} />
                  </span>
                </div>
              ))}
              {preview?.detail && <p className="text-muted-foreground">{preview.detail}</p>}
              {visibleProblem && (
                <p className="text-amber-600 dark:text-amber-400 flex items-start gap-1.5">
                  <AlertCircle className="w-3.5 h-3.5 shrink-0 mt-px" />
                  <span>{visibleProblem}</span>
                </p>
              )}
            </div>
          )}

          {/* Footer Actions */}
          <div className="pt-3 border-t border-border/60 flex items-center justify-end gap-2.5">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2.5 text-xs font-medium rounded-xl border border-border/70 hover:bg-muted/50 text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting || Boolean(problem)}
              title={problem ?? undefined}
              className="px-5 py-2.5 text-xs font-semibold rounded-xl bg-primary text-primary-foreground hover:opacity-95 active:scale-98 transition-all flex items-center gap-2 shadow-xs disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  Saving...
                </>
              ) : (
                <>
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  {SUBMIT_LABEL[movementType]}
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
