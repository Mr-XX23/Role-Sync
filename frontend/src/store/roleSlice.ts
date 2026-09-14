import { createSlice } from '@reduxjs/toolkit';
import type { PayloadAction } from '@reduxjs/toolkit';

export type RolePack = 'sales' | 'teacher' | 'student';

/** The Salesman Engine is the only persona that ships today, so it is always active. */
export const DEFAULT_ROLE: RolePack = 'sales';

interface RoleState {
  activeRolePack: RolePack;
  availableRoles: RolePack[];
}

const initialState: RoleState = {
  activeRolePack: DEFAULT_ROLE,
  availableRoles: [DEFAULT_ROLE],
};

const roleSlice = createSlice({
  name: 'role',
  initialState,
  reducers: {
    setActiveRole: (state, action: PayloadAction<RolePack>) => {
      state.activeRolePack = action.payload;
    },
    clearActiveRole: (state) => {
      state.activeRolePack = DEFAULT_ROLE;
    },
  },
});

export const { setActiveRole, clearActiveRole } = roleSlice.actions;
export default roleSlice.reducer;
