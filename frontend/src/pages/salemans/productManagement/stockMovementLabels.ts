import {
  ClipboardCheck,
  Lock,
  LockOpen,
  PackagePlus,
  PackageX,
  SearchX,
  ShoppingCart,
  Truck,
  Undo2,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import type {
  Product,
  StockEntryType,
  StockLedgerReason,
  StockMovementType,
  Variant,
} from '../../../api/catalogApi';

export const formatLocationType = (type?: string | null): string => {
  switch (type?.toUpperCase()) {
    case 'WAREHOUSE':
      return 'Warehouse';
    case 'STORE':
      return 'Store';
    case 'SUPPLIER':
      return 'Supplier';
    case 'IN_TRANSIT':
      return 'In transit';
    default:
      return type ? type.replace(/_/g, ' ').toLowerCase() : 'Location';
  }
};

/** "Desk Chair — Black / L" */
export const describeVariant = (variant: Variant, products: Product[]): string => {
  const name = products.find((p) => p.id === variant.product_id)?.name || 'Product';
  const options = variant.option_values.map((ov) => ov.value).join(' / ');
  return options ? `${name} — ${options}` : name;
};

export const ADMIN_ROLES = ['OWNER', 'ADMIN'];

interface MovementChoice {
  type: StockMovementType;
  label: string;
  hint: string;
  icon: LucideIcon;
}

/** What someone can record in Update Stock, in the order it is offered. */
export const MOVEMENT_CHOICES: MovementChoice[] = [
  { type: 'RECEIVED', label: 'Stock received', hint: 'Adds to the count', icon: PackagePlus },
  { type: 'SOLD', label: 'Sold', hint: 'Takes available units', icon: ShoppingCart },
  { type: 'SHIPPED', label: 'Shipped to another location', hint: 'Moves units between locations', icon: Truck },
  { type: 'DAMAGED', label: 'Damaged', hint: 'Writes units off', icon: PackageX },
  { type: 'LOST', label: 'Lost', hint: 'Writes units off', icon: SearchX },
  { type: 'RETURNED', label: 'Customer return', hint: 'Units coming back', icon: Undo2 },
  { type: 'COUNT_CORRECTION', label: 'Count correction', hint: 'Replaces the count', icon: ClipboardCheck },
];

interface EntryStyle {
  label: string;
  icon: LucideIcon;
  className: string;
}

/** How a history row is shown. */
export const ENTRY_STYLES: Record<StockEntryType, EntryStyle> = {
  RECEIVED: {
    label: 'Received',
    icon: PackagePlus,
    className: 'text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 border-emerald-500/25',
  },
  SOLD: { label: 'Sold', icon: ShoppingCart, className: 'text-sky-600 dark:text-sky-400 bg-sky-500/10 border-sky-500/25' },
  SHIPPED_OUT: {
    label: 'Shipped out',
    icon: Truck,
    className: 'text-violet-600 dark:text-violet-400 bg-violet-500/10 border-violet-500/25',
  },
  SHIPPED_IN: {
    label: 'Shipped in',
    icon: Truck,
    className: 'text-violet-600 dark:text-violet-400 bg-violet-500/10 border-violet-500/25',
  },
  DAMAGED: {
    label: 'Damaged',
    icon: PackageX,
    className: 'text-orange-600 dark:text-orange-400 bg-orange-500/10 border-orange-500/25',
  },
  LOST: { label: 'Lost', icon: SearchX, className: 'text-rose-600 dark:text-rose-400 bg-rose-500/10 border-rose-500/25' },
  RETURNED: { label: 'Returned', icon: Undo2, className: 'text-teal-600 dark:text-teal-400 bg-teal-500/10 border-teal-500/25' },
  CORRECTION: {
    label: 'Count correction',
    icon: ClipboardCheck,
    className: 'text-amber-600 dark:text-amber-400 bg-amber-500/10 border-amber-500/25',
  },
  RESERVED: { label: 'Reserved', icon: Lock, className: 'text-muted-foreground bg-muted/60 border-border' },
  RELEASED: { label: 'Released', icon: LockOpen, className: 'text-muted-foreground bg-muted/60 border-border' },
};

export type HistoryFilter =
  | 'ALL'
  | 'RECEIVED'
  | 'SOLD'
  | 'SHIPPED'
  | 'DAMAGED'
  | 'LOST'
  | 'RETURNED'
  | 'CORRECTION'
  | 'HOLDS';

/** History filter chips and the ledger reasons each one shows. */
export const HISTORY_FILTERS: Array<{ key: HistoryFilter; label: string; reasons: StockLedgerReason[] }> = [
  { key: 'ALL', label: 'All changes', reasons: [] },
  { key: 'RECEIVED', label: 'Received', reasons: ['RESTOCK'] },
  { key: 'SOLD', label: 'Sold', reasons: ['SALE'] },
  { key: 'SHIPPED', label: 'Shipped', reasons: ['TRANSFER_OUT', 'TRANSFER_IN'] },
  { key: 'DAMAGED', label: 'Damaged', reasons: ['DAMAGE'] },
  { key: 'LOST', label: 'Lost', reasons: ['LOST'] },
  { key: 'RETURNED', label: 'Returns', reasons: ['RETURN'] },
  { key: 'CORRECTION', label: 'Corrections', reasons: ['ADJUST'] },
  { key: 'HOLDS', label: 'Reservations', reasons: ['RESERVE', 'RELEASE'] },
];
