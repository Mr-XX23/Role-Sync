import React, { useEffect } from 'react';
import { Outlet, useLocation, useMatches } from 'react-router-dom';
import { deriveTitleFromPathname, setDocumentTitle } from '../../utils/pageTitle';

interface RouteHandle {
  title?: string | ((params: Record<string, string | undefined>) => string);
}

export const PageTitleManager: React.FC = () => {
  const location = useLocation();
  const matches = useMatches();

  useEffect(() => {
    // Check matched routes from deepest child up to parent for a custom title handle
    const matchWithTitle = [...matches].reverse().find(
      (m) => Boolean((m.handle as RouteHandle | undefined)?.title)
    );

    const handle = matchWithTitle?.handle as RouteHandle | undefined;
    let title: string | undefined;

    if (typeof handle?.title === 'function') {
      title = handle.title(matchWithTitle?.params ?? {});
    } else if (typeof handle?.title === 'string') {
      title = handle.title;
    }

    if (title) {
      setDocumentTitle(title);
    } else {
      setDocumentTitle(deriveTitleFromPathname(location.pathname));
    }
  }, [location.pathname, matches]);

  return <Outlet />;
};
