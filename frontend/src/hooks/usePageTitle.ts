import { useEffect } from 'react';
import { setDocumentTitle } from '../utils/pageTitle';

/**
 * Custom hook to allow individual components or pages to dynamically set/override the document title.
 * Automatically cleans up or updates as title changes.
 *
 * Example:
 *   usePageTitle('Acme Corp Deal');
 */
export function usePageTitle(title?: string): void {
  useEffect(() => {
    if (!title) return;
    setDocumentTitle(title);
  }, [title]);
}
