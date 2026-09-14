import { knowledgeVaultApi } from '../../../api/knowledgeVaultApi';
import type { KnowledgeDocument } from '../../../api/knowledgeVaultApi';

/**
 * Files attached to a chat message.
 *
 * The agent engine takes text only, so attachments go into the workspace's Knowledge Vault
 * (documents parse locally or via LlamaParse, images are OCR'd) and the message tells the
 * agent which files were attached so it reads them with its knowledge-base tools.
 */

export const DOCUMENT_EXTENSIONS = ['pdf', 'docx', 'pptx', 'xlsx', 'csv', 'tsv', 'txt', 'md', 'json', 'yaml', 'yml'];
export const IMAGE_EXTENSIONS = ['png', 'jpg', 'jpeg', 'webp', 'gif'];
export const MAX_ATTACHMENTS = 2;
export const MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024; // matches MAX_UPLOAD_BYTES in the pipeline

/** Value for `<input accept>`: documents and images only (no audio/video or anything else). */
export const ATTACHMENT_ACCEPT = [
  ...DOCUMENT_EXTENSIONS.map((ext) => `.${ext}`),
  ...IMAGE_EXTENSIONS.map((ext) => `.${ext}`),
  'image/png',
  'image/jpeg',
  'image/webp',
  'image/gif',
].join(',');

export type AttachmentKind = 'image' | 'document';

export interface Attachment {
  id: string;
  file: File;
  kind: AttachmentKind;
  /** Object URL for image thumbnails; revoke it when the attachment goes away. */
  previewUrl: string | null;
}

function extensionOf(name: string): string {
  const dot = name.lastIndexOf('.');
  return dot === -1 ? '' : name.slice(dot + 1).toLowerCase();
}

/** Turns a picked file into an attachment, or explains why it cannot be attached. */
export function toAttachment(file: File): { attachment: Attachment } | { error: string } {
  const ext = extensionOf(file.name);
  const isImage = IMAGE_EXTENSIONS.includes(ext) || file.type.startsWith('image/');
  const isDocument = DOCUMENT_EXTENSIONS.includes(ext);
  if (file.type.startsWith('video/') || file.type.startsWith('audio/')) {
    return { error: `"${file.name}" is audio or video. Only documents and images can be attached.` };
  }
  if (!isImage && !isDocument) {
    return {
      error: `"${file.name}" is not supported. Attach a PDF, Word, Excel, PowerPoint, CSV, text, Markdown, JSON or image file.`,
    };
  }
  if (isImage && !IMAGE_EXTENSIONS.includes(ext)) {
    return { error: `"${file.name}" must be a PNG, JPG, WEBP or GIF image.` };
  }
  if (file.size === 0) {
    return { error: `"${file.name}" is empty.` };
  }
  if (file.size > MAX_ATTACHMENT_BYTES) {
    return { error: `"${file.name}" is larger than 25 MB.` };
  }
  return {
    attachment: {
      id: `${file.name}-${file.size}-${file.lastModified}-${Math.random().toString(36).slice(2, 8)}`,
      file,
      kind: isImage ? 'image' : 'document',
      previewUrl: isImage ? URL.createObjectURL(file) : null,
    },
  };
}

export function releaseAttachment(attachment: Attachment): void {
  if (attachment.previewUrl) {
    URL.revokeObjectURL(attachment.previewUrl);
  }
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/* ------------------------------------------------------------------ */
/* Upload + wait for indexing                                          */
/* ------------------------------------------------------------------ */

export interface UploadedAttachment {
  name: string;
  document: KnowledgeDocument;
}

/** Uploads attachments to the Knowledge Vault one at a time (the endpoint takes a single file). */
export async function uploadAttachments(
  attachments: Attachment[],
  onProgress: (done: number, total: number, name: string) => void
): Promise<UploadedAttachment[]> {
  const uploaded: UploadedAttachment[] = [];
  for (const [index, attachment] of attachments.entries()) {
    onProgress(index, attachments.length, attachment.file.name);
    const result = await knowledgeVaultApi.uploadFile(attachment.file);
    uploaded.push({ name: attachment.file.name, document: result.document });
  }
  onProgress(attachments.length, attachments.length, '');
  return uploaded;
}

export interface IndexingOutcome {
  /** Parsed and indexed; the agent can read these now. */
  ready: string[];
  /** Still parsing when we stopped waiting; the agent may not find them yet. */
  pending: string[];
  /** The pipeline could not read them (unsupported content, OCR failure, rejected). */
  unreadable: string[];
}

const sleep = (ms: number) => new Promise<void>((resolve) => window.setTimeout(resolve, ms));

/**
 * Parsing and embedding happen in the background after upload, so wait (briefly) for the
 * documents to be indexed before the agent is told to read them.
 */
export async function waitForIndexed(
  uploaded: UploadedAttachment[],
  options: { timeoutMs?: number; intervalMs?: number; onTick?: (outcome: IndexingOutcome) => void } = {}
): Promise<IndexingOutcome> {
  const { timeoutMs = 60_000, intervalMs = 3_000, onTick } = options;
  const byId = new Map(uploaded.map((item) => [item.document.doc_id, item.name]));
  const outcome: IndexingOutcome = { ready: [], pending: [...byId.values()], unreadable: [] };

  const apply = (documents: KnowledgeDocument[]) => {
    const ready: string[] = [];
    const pending: string[] = [];
    const unreadable: string[] = [];
    for (const [docId, name] of byId) {
      const doc = documents.find((row) => row.doc_id === docId);
      const status = doc?.status ?? 'Parsing';
      if (status === 'Indexed') ready.push(name);
      else if (status === 'Error' || status === 'Rejected') unreadable.push(name);
      else pending.push(name);
    }
    outcome.ready = ready;
    outcome.pending = pending;
    outcome.unreadable = unreadable;
  };

  // A duplicate upload returns the document that already exists, often already indexed.
  apply(uploaded.map((item) => item.document));
  const started = Date.now();
  while (outcome.pending.length > 0 && Date.now() - started < timeoutMs) {
    onTick?.(outcome);
    await sleep(intervalMs);
    try {
      apply(await knowledgeVaultApi.getDocuments());
    } catch {
      // Keep waiting; the next poll may succeed.
    }
  }
  return outcome;
}

/* ------------------------------------------------------------------ */
/* The note appended to the message                                    */
/* ------------------------------------------------------------------ */

const NOTE_PREFIX = 'Attached files';

/** What the agent is told about the files; it reads them from the knowledge base. */
export function attachmentNote(outcome: IndexingOutcome): string {
  const parts: string[] = [];
  if (outcome.ready.length) {
    parts.push(
      `${NOTE_PREFIX} (saved to the knowledge base; read them with the knowledge base tools before answering): ${outcome.ready.join(', ')}`
    );
  }
  if (outcome.pending.length) {
    parts.push(
      `${outcome.ready.length ? 'Still being indexed' : `${NOTE_PREFIX}, still being indexed in the knowledge base`} (search again if not found yet): ${outcome.pending.join(', ')}`
    );
  }
  if (outcome.unreadable.length) {
    parts.push(`Could not be read by the knowledge base: ${outcome.unreadable.join(', ')}`);
  }
  return parts.join('. ');
}

/** Splits a stored message into the rep's own words and the attached file names, for display. */
export function splitAttachmentNote(text: string): { body: string; names: string[] } {
  const marker = `\n\n${NOTE_PREFIX}`;
  const index = text.indexOf(marker);
  if (index === -1) {
    return { body: text, names: [] };
  }
  const note = text.slice(index + 2);
  const names = note
    .split(': ')
    .slice(1)
    .join(': ')
    .split(/\. (?:Still being indexed|Could not be read)[^:]*: /)
    .join(', ')
    .split(', ')
    .map((name) => name.trim())
    .filter(Boolean);
  return { body: text.slice(0, index), names };
}
