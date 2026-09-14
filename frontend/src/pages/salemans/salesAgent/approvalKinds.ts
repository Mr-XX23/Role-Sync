import {
  Archive,
  ArchiveRestore,
  Boxes,
  BriefcaseBusiness,
  CalendarPlus,
  FilePen,
  FolderMinus,
  FolderPen,
  FolderPlus,
  Globe,
  Handshake,
  FileText,
  Mail,
  MapPinOff,
  MapPinPen,
  MessageSquare,
  Package,
  PackageMinus,
  PackagePlus,
  Receipt,
  RefreshCw,
  ShieldCheck,
  Tags,
  Trash2,
  Truck,
  Undo2,
  Warehouse,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import type { ApprovalCardModel } from './chatState';

/** The kind of action a card is about (set by the engine's preview). */
export function previewKind(card: ApprovalCardModel): string {
  const kind = card.preview.kind;
  if (typeof kind === 'string' && kind) {
    return kind;
  }
  return card.tool === 'send_email' ? 'email' : 'generic';
}

const KINDS: Record<string, { title: string; approve: string; icon: LucideIcon }> = {
  email: { title: 'Send this email?', approve: 'Approve & send', icon: Mail },
  calendar_event: { title: 'Create this calendar event?', approve: 'Approve & create', icon: CalendarPlus },
  slack_message: { title: 'Post this Slack message?', approve: 'Approve & post', icon: MessageSquare },
  notion_page: { title: 'Create this Notion page?', approve: 'Approve & create', icon: FileText },
  document: { title: 'Create this document?', approve: 'Approve & create', icon: FileText },
  quote: { title: 'Create this quote?', approve: 'Approve & create', icon: Receipt },
  deal_create: { title: 'Create this deal?', approve: 'Approve & create', icon: Handshake },
  deal_update: { title: 'Update this deal?', approve: 'Approve & update', icon: BriefcaseBusiness },
  catalog_item: { title: 'Add this item to the catalog?', approve: 'Approve & add', icon: PackagePlus },
  catalog_update: { title: 'Update this catalog item?', approve: 'Approve & update', icon: Package },
  catalog_retire: { title: 'Retire this catalog item?', approve: 'Approve & retire', icon: Archive },
  catalog_restore: { title: 'Restore this catalog item?', approve: 'Approve & restore', icon: ArchiveRestore },
  catalog_skus: { title: 'Add these SKUs?', approve: 'Approve & add', icon: PackagePlus },
  stock_change: { title: 'Correct this stock count?', approve: 'Approve & correct', icon: Boxes },
  stock_movement: { title: 'Record this stock movement?', approve: 'Approve & record', icon: Truck },
  stock_reservation: { title: 'Reserve this stock?', approve: 'Approve & reserve', icon: PackagePlus },
  stock_release: { title: 'Release this reservation?', approve: 'Approve & release', icon: PackageMinus },
  knowledge_add_url: { title: 'Add this web page to the knowledge base?', approve: 'Approve & add', icon: Globe },
  knowledge_update: { title: 'Update this document’s classification?', approve: 'Approve & update', icon: FilePen },
  knowledge_reclassify: { title: 'Classify this document again?', approve: 'Approve & classify', icon: Tags },
  knowledge_reindex: { title: 'Index this document again?', approve: 'Approve & re-index', icon: RefreshCw },
  knowledge_delete: { title: 'Delete this document?', approve: 'Approve & delete', icon: Trash2 },
  undo: { title: 'Undo these actions?', approve: 'Undo them', icon: Undo2 },
};

/** Cards whose wording depends on what the action does to the thing (add, change or remove). */
const BY_ACTION: Record<string, Record<string, { title: string; approve: string; icon: LucideIcon }>> = {
  catalog_category: {
    create: { title: 'Add this catalog category?', approve: 'Approve & add', icon: FolderPlus },
    update: { title: 'Change this catalog category?', approve: 'Approve & change', icon: FolderPen },
    delete: { title: 'Remove this catalog category?', approve: 'Approve & remove', icon: FolderMinus },
  },
  stock_location: {
    create: { title: 'Add this stock location?', approve: 'Approve & add', icon: Warehouse },
    update: { title: 'Change this stock location?', approve: 'Approve & change', icon: MapPinPen },
    delete: { title: 'Remove this stock location?', approve: 'Approve & remove', icon: MapPinOff },
  },
};

export function describeKind(card: ApprovalCardModel): { title: string; approve: string; icon: LucideIcon } {
  const kind = previewKind(card);
  if (kind === 'knowledge_add_url' && card.preview.existing) {
    return { title: 'Refresh this web page in the knowledge base?', approve: 'Approve & refresh', icon: Globe };
  }
  const byAction = BY_ACTION[kind]?.[String(card.preview.action)];
  if (byAction) {
    return byAction;
  }
  return KINDS[kind] ?? { title: `Allow ${card.tool}?`, approve: 'Approve', icon: ShieldCheck };
}
