import React from 'react';
import { Navigate } from 'react-router-dom';
import { useAppSelector } from '../../store';

/**
 * Opens the Super Admin Console only for platform super admins. This is a convenience: every
 * console API checks the caller on the server, so hiding it is not what protects it.
 */
export const SuperAdminRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const isSuperAdmin = useAppSelector((state) => state.auth.user?.platformRole === 'SUPER_ADMIN');
  if (!isSuperAdmin) {
    return <Navigate to="/salesman" replace />;
  }
  return <>{children}</>;
};
