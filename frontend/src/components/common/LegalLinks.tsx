import React from 'react';
import { Link } from 'react-router-dom';

/** "Privacy Policy · Terms of Service" for the footers of the sign-in and verification pages. */
export const LegalLinks: React.FC<{ className?: string }> = ({ className = '' }) => (
  <p className={`flex items-center justify-center gap-3 text-[11px] ${className}`}>
    <Link to="/privacy" className="text-muted-foreground hover:text-primary transition-colors">
      Privacy Policy
    </Link>
    <span className="text-border" aria-hidden>
      •
    </span>
    <Link to="/terms" className="text-muted-foreground hover:text-primary transition-colors">
      Terms of Service
    </Link>
  </p>
);
