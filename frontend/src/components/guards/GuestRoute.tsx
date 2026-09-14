import React, { useEffect, useState } from 'react';
import { Navigate, useSearchParams } from 'react-router-dom';
import { useAppSelector } from '../../store';
import { redirectParam, rememberRedirect, rememberedRedirect } from '../../utils/authRedirect';

interface GuestRouteProps {
  children: React.ReactNode;
}

export const GuestRoute: React.FC<GuestRouteProps> = ({ children }) => {
  const { isAuthenticated } = useAppSelector((state) => state.auth);
  const [searchParams] = useSearchParams();
  // A page that sent them here (`?redirect=/pricing`), or one remembered while they signed up.
  const [remembered] = useState(rememberedRedirect);

  useEffect(() => {
    if (isAuthenticated) rememberRedirect(null);
  }, [isAuthenticated]);

  if (isAuthenticated) {
    return <Navigate to={redirectParam(searchParams) ?? remembered ?? '/salesman'} replace />;
  }

  return <>{children}</>;
};
