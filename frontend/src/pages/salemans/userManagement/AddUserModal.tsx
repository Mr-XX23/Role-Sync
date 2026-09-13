import React, { useEffect, useRef, useState } from 'react';
import { AlertCircle, Info, UserPlus, X } from 'lucide-react';
import { Button } from '../../../components/common/Button';
import { describeMemberError, membersApi } from '../../../api/membersApi';
import type { AssignableRole, InviteResult } from '../../../api/membersApi';
import { ROLE_META, validateNewUser } from './memberFormat';
import type { NewUserErrors, NewUserForm } from './memberFormat';

const control =
  'w-full py-2 px-3 rounded-xl border bg-background text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 disabled:opacity-70 disabled:cursor-not-allowed';
const okBorder = 'border-border focus:ring-primary/10 focus:border-primary';
const errorBorder = 'border-destructive focus:ring-destructive/10 focus:border-destructive';
const label = 'block text-[10px] font-mono font-bold uppercase tracking-wider text-muted-foreground';

const FieldError: React.FC<{ id: string; message?: string }> = ({ id, message }) =>
  message ? (
    <p id={id} className="text-[11px] text-destructive mt-1 flex items-center gap-1">
      <AlertCircle className="w-3 h-3 shrink-0" />
      {message}
    </p>
  ) : null;

export const AddUserModal: React.FC<{
  workspaceName: string;
  assignableRoles: AssignableRole[];
  onClose: () => void;
  onAdded: (result: InviteResult, email: string) => void;
}> = ({ workspaceName, assignableRoles, onClose, onAdded }) => {
  const roles = assignableRoles.length > 0 ? assignableRoles : (['MEMBER', 'VIEWER'] as AssignableRole[]);
  const [form, setForm] = useState<NewUserForm>({
    firstName: '',
    lastName: '',
    email: '',
    role: roles.includes('MEMBER') ? 'MEMBER' : roles[0],
  });
  const [errors, setErrors] = useState<NewUserErrors>({});
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const firstField = useRef<HTMLInputElement>(null);

  useEffect(() => {
    firstField.current?.focus();
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !busy) onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [busy, onClose]);

  const set = <K extends keyof NewUserForm>(field: K, value: NewUserForm[K]) => {
    setForm((current) => ({ ...current, [field]: value }));
    if (field in errors) {
      setErrors((current) => ({ ...current, [field]: undefined }));
    }
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (busy) return;
    const found = validateNewUser(form);
    setErrors(found);
    if (Object.values(found).some(Boolean)) {
      setProblem(null);
      return;
    }
    setProblem(null);
    setBusy(true);
    const email = form.email.trim().toLowerCase();
    try {
      const result = await membersApi.invite({
        email,
        first_name: form.firstName.trim(),
        last_name: form.lastName.trim() || null,
        role_name: form.role,
      });
      onAdded(result, email);
    } catch (error) {
      setProblem(describeMemberError(error));
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-xs">
      <form
        role="dialog"
        aria-modal="true"
        aria-labelledby="add-user-title"
        onSubmit={(event) => void submit(event)}
        noValidate
        className="relative w-full max-w-lg max-h-[92vh] bg-card border border-border/80 rounded-2xl shadow-2xl overflow-hidden flex flex-col"
      >
        <div className="px-6 py-4 border-b border-border/60 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-10 h-10 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center text-primary shrink-0">
              <UserPlus className="w-5 h-5" />
            </div>
            <div className="min-w-0">
              <h3 id="add-user-title" className="text-base font-bold text-foreground">
                Add user
              </h3>
              <p className="text-xs text-muted-foreground truncate">to {workspaceName}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={busy}
            aria-label="Close"
            className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors disabled:opacity-30 cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {problem && (
            <div role="alert" className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-2.5 text-xs text-red-700 dark:text-red-300">
              {problem}
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="space-y-1">
              <label htmlFor="new-user-first" className={label}>
                First name
              </label>
              <input
                ref={firstField}
                id="new-user-first"
                className={`${control} ${errors.firstName ? errorBorder : okBorder}`}
                value={form.firstName}
                maxLength={50}
                autoComplete="off"
                placeholder="Jane"
                disabled={busy}
                aria-invalid={Boolean(errors.firstName)}
                aria-describedby={errors.firstName ? 'new-user-first-error' : undefined}
                onChange={(event) => set('firstName', event.target.value)}
              />
              <FieldError id="new-user-first-error" message={errors.firstName} />
            </div>
            <div className="space-y-1">
              <label htmlFor="new-user-last" className={label}>
                Last name <span className="normal-case font-normal tracking-normal">(optional)</span>
              </label>
              <input
                id="new-user-last"
                className={`${control} ${errors.lastName ? errorBorder : okBorder}`}
                value={form.lastName}
                maxLength={50}
                autoComplete="off"
                placeholder="Doe"
                disabled={busy}
                aria-invalid={Boolean(errors.lastName)}
                onChange={(event) => set('lastName', event.target.value)}
              />
              <FieldError id="new-user-last-error" message={errors.lastName} />
            </div>
          </div>

          <div className="space-y-1">
            <label htmlFor="new-user-email" className={label}>
              Email
            </label>
            <input
              id="new-user-email"
              type="email"
              className={`${control} ${errors.email ? errorBorder : okBorder}`}
              value={form.email}
              maxLength={100}
              autoComplete="off"
              placeholder="jane@company.com"
              disabled={busy}
              aria-invalid={Boolean(errors.email)}
              aria-describedby={errors.email ? 'new-user-email-error' : 'new-user-email-help'}
              onChange={(event) => set('email', event.target.value)}
            />
            {errors.email ? (
              <FieldError id="new-user-email-error" message={errors.email} />
            ) : (
              <p id="new-user-email-help" className="text-[11px] text-muted-foreground">
                This is also the email they sign in with.
              </p>
            )}
          </div>

          <fieldset className="space-y-1.5" disabled={busy}>
            <legend className={label}>Role</legend>
            {roles.map((role) => (
              <label
                key={role}
                className={`flex items-start gap-3 rounded-xl border px-3 py-2.5 cursor-pointer transition-colors ${
                  form.role === role ? 'border-primary/50 bg-primary/5' : 'border-border/70 hover:bg-muted/40'
                }`}
              >
                <input
                  type="radio"
                  name="new-user-role"
                  value={role}
                  checked={form.role === role}
                  onChange={() => set('role', role)}
                  className="mt-0.5 accent-current text-primary"
                />
                <span className="min-w-0">
                  <span className="block text-sm font-semibold text-foreground">{ROLE_META[role].label}</span>
                  <span className="block text-xs text-muted-foreground">{ROLE_META[role].description}</span>
                </span>
              </label>
            ))}
            {!roles.includes('ADMIN') && (
              <p className="text-[11px] text-muted-foreground">Only the workspace owner can add admins.</p>
            )}
          </fieldset>

          <div className="flex items-start gap-2 rounded-xl border border-border/60 bg-muted/30 px-3 py-2.5 text-xs text-muted-foreground">
            <Info className="w-3.5 h-3.5 mt-0.5 shrink-0" />
            <p>
              If they don’t have an account yet, we create one that’s already verified and email them a temporary password. They
              choose their own password the first time they sign in. If they already have an account, they get access right
              away.
            </p>
          </div>
        </div>

        <div className="px-6 py-3 border-t border-border/60 bg-muted/20 flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            disabled={busy}
            className="px-4 py-2 text-xs font-medium rounded-xl border border-border/70 hover:bg-muted/60 text-muted-foreground hover:text-foreground transition-colors cursor-pointer disabled:opacity-50"
          >
            Cancel
          </button>
          <Button type="submit" className="px-4 py-2 w-auto text-xs" isLoading={busy} loadingText="Adding…">
            Add user
          </Button>
        </div>
      </form>
    </div>
  );
};
