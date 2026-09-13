import React from 'react';
import ReactMarkdown from 'react-markdown';
import type { Components } from 'react-markdown';
import remarkBreaks from 'remark-breaks';
import remarkGfm from 'remark-gfm';
import { Link } from 'react-router-dom';
import { ExternalLink, ImageOff } from 'lucide-react';

/** Links inside this app (a document in the knowledge vault, a deal). */
const isAppLink = (url: string): boolean => /^\/salesman\/[\w\-/?=&.%#]*$/.test(url);

/**
 * Only web, mail and in-app links survive. Model output can echo text from web pages and emails,
 * so anything else (javascript:, data:, relative paths outside the app) is dropped.
 */
function safeUrl(url: string): string {
  const value = url.trim();
  if (/^https?:\/\//i.test(value) || /^mailto:/i.test(value) || isAppLink(value)) {
    return value;
  }
  return '';
}

const components: Components = {
  p: ({ children }) => <p className="my-2 first:mt-0 last:mb-0 leading-relaxed">{children}</p>,
  h1: ({ children }) => <h3 className="mt-4 mb-2 first:mt-0 text-base font-bold text-foreground">{children}</h3>,
  h2: ({ children }) => <h3 className="mt-4 mb-2 first:mt-0 text-[15px] font-bold text-foreground">{children}</h3>,
  h3: ({ children }) => <h4 className="mt-3.5 mb-1.5 first:mt-0 text-sm font-bold text-foreground">{children}</h4>,
  h4: ({ children }) => <h5 className="mt-3 mb-1 first:mt-0 text-sm font-semibold text-foreground">{children}</h5>,
  h5: ({ children }) => <h6 className="mt-3 mb-1 first:mt-0 text-sm font-semibold text-foreground/90">{children}</h6>,
  h6: ({ children }) => <h6 className="mt-3 mb-1 first:mt-0 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{children}</h6>,
  ul: ({ children, className }) => (
    <ul
      className={`my-2 first:mt-0 last:mb-0 space-y-1 ${
        className?.includes('contains-task-list') ? 'pl-1 list-none' : 'pl-5 list-disc marker:text-muted-foreground'
      }`}
    >
      {children}
    </ul>
  ),
  ol: ({ children, start }) => (
    <ol start={start} className="my-2 first:mt-0 last:mb-0 pl-5 list-decimal space-y-1 marker:text-muted-foreground marker:font-mono marker:text-xs">
      {children}
    </ol>
  ),
  li: ({ children }) => <li className="pl-0.5 leading-relaxed [&>ol]:my-1 [&>ul]:my-1 [&>p]:my-1">{children}</li>,
  input: ({ checked, type }) =>
    type === 'checkbox' ? (
      <input type="checkbox" checked={Boolean(checked)} disabled readOnly className="mr-1.5 align-middle accent-primary" />
    ) : null,
  strong: ({ children }) => <strong className="font-semibold text-foreground">{children}</strong>,
  em: ({ children }) => <em className="italic">{children}</em>,
  del: ({ children }) => <del className="text-muted-foreground line-through">{children}</del>,
  blockquote: ({ children }) => (
    <blockquote className="my-3 first:mt-0 last:mb-0 border-l-2 border-primary/40 pl-3 text-muted-foreground [&>p]:my-1">
      {children}
    </blockquote>
  ),
  hr: () => <hr className="my-4 border-border" />,
  a: ({ href, children }) => {
    const url = href ?? '';
    const className = 'font-medium text-primary underline decoration-primary/35 underline-offset-2 hover:decoration-primary';
    if (!url) {
      return <span>{children}</span>;
    }
    if (isAppLink(url)) {
      return (
        <Link to={url} className={className}>
          {children}
        </Link>
      );
    }
    return (
      <a href={url} target="_blank" rel="noopener noreferrer nofollow" className={`${className} inline-flex items-baseline gap-0.5`}>
        {children}
        {!url.startsWith('mailto:') && <ExternalLink className="w-3 h-3 self-center shrink-0 opacity-60" aria-hidden />}
      </a>
    );
  },
  // Remote images are never loaded: an image URL can carry data to whoever serves it.
  img: ({ src, alt }) => {
    const url = typeof src === 'string' ? src : '';
    const label = alt || 'image';
    return url ? (
      <a
        href={url}
        target="_blank"
        rel="noopener noreferrer nofollow"
        className="inline-flex items-center gap-1 rounded-md border border-border bg-muted/50 px-1.5 py-0.5 text-xs text-muted-foreground hover:text-foreground"
      >
        <ImageOff className="w-3 h-3" aria-hidden />
        {label}
      </a>
    ) : (
      <span className="text-muted-foreground">{label}</span>
    );
  },
  pre: ({ children }) => (
    <pre className="my-3 first:mt-0 last:mb-0 overflow-x-auto rounded-xl border border-border bg-background/70 p-3 font-mono text-xs leading-relaxed text-foreground [&>code]:bg-transparent [&>code]:p-0 [&>code]:text-xs">
      {children}
    </pre>
  ),
  code: ({ children, className }) => (
    <code className={`rounded-md border border-border/60 bg-muted/70 px-1.5 py-0.5 font-mono text-[0.85em] text-foreground ${className ?? ''}`}>
      {children}
    </code>
  ),
  table: ({ children }) => (
    <div className="my-3 first:mt-0 last:mb-0 overflow-x-auto rounded-xl border border-border">
      <table className="w-full border-collapse text-xs">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-muted/40">{children}</thead>,
  th: ({ children, style }) => (
    <th style={style} className="px-3 py-2 text-left font-mono text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
      {children}
    </th>
  ),
  td: ({ children, style }) => (
    <td style={style} className="border-t border-border/60 px-3 py-2 align-top text-foreground">
      {children}
    </td>
  ),
};

/**
 * Markdown written by the agent, styled with the app's theme. Raw HTML is never rendered, links
 * are limited to web, mail and in-app addresses, and images are shown as links instead of loaded.
 */
export const Markdown: React.FC<{ children: string; className?: string }> = ({ children, className = '' }) => (
  <div className={`min-w-0 break-words text-sm text-foreground ${className}`}>
    <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]} components={components} urlTransform={safeUrl} skipHtml>
      {children}
    </ReactMarkdown>
  </div>
);
