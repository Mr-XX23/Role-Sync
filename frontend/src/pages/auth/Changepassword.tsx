import React, { useEffect, useState } from 'react';
import { AlertCircle, CheckCircle2, Circle, Eye, EyeOff, KeyRound, LogOut, UserRoundKey } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { Button } from '../../components/common/Button';
import { Input } from '../../components/common/Input';
import { useAppDispatch, useAppSelector } from '../../store';
import { clearUpdateState, logoutUser, updatePassword } from '../../store/authSlice';

// The same rules auth-service applies (services/user/PasswordPolicy.java).
function passwordChecks(password: string) {
  return {
    length: password.length >= 12 && password.length <= 128,
    mixedCase: /\p{Ll}/u.test(password) && /\p{Lu}/u.test(password),
    numberAndSymbol: /\p{Nd}/u.test(password) && /[^\p{L}\p{Nd}\s]/u.test(password),
    noEdgeSpaces: password === password.trim(),
  };
}

const Requirement: React.FC<{ met: boolean; children: React.ReactNode }> = ({ met, children }) => (
  <li className={`flex items-center gap-2 ${met ? 'text-primary font-medium' : 'text-muted-foreground'}`}>
    {met ? <CheckCircle2 className="w-4 h-4 text-primary" /> : <Circle className="w-4 h-4" />}
    <span>{children}</span>
  </li>
);

const Changepassword: React.FC = () => {
  const navigate = useNavigate();
  const dispatch = useAppDispatch();
  const { user, isUpdateLoading, updateSuccess, updateError } = useAppSelector((state) => state.auth);
  // Remember why the page opened: the flag clears as soon as the new password is saved.
  const [forced] = useState(() => Boolean(user?.mustChangePassword));

  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showCurrent, setShowCurrent] = useState(false);
  const [showNew, setShowNew] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  useEffect(() => {
    dispatch(clearUpdateState());
    return () => {
      dispatch(clearUpdateState());
    };
  }, [dispatch]);

  const checks = passwordChecks(newPassword);
  const allMet = checks.length && checks.mixedCase && checks.numberAndSymbol && checks.noEdgeSpaces;
  const error = localError || updateError;

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    setLocalError(null);
    dispatch(clearUpdateState());
    if (!currentPassword) {
      setLocalError(forced ? 'Enter the temporary password from your invitation email.' : 'Enter your current password.');
      return;
    }
    if (!allMet) {
      setLocalError(
        checks.noEdgeSpaces ? 'Your new password doesn’t meet all the requirements yet.' : 'Your new password can’t start or end with a space.'
      );
      return;
    }
    if (newPassword !== confirmPassword) {
      setLocalError('The new passwords don’t match.');
      return;
    }
    if (newPassword === currentPassword) {
      setLocalError('Choose a new password that’s different from your current one.');
      return;
    }
    void dispatch(updatePassword({ currentPassword, newPassword }));
  };

  const goToApp = () => navigate('/salesman', { replace: true });

  const signOut = () => {
    void dispatch(logoutUser());
  };

  return (
    <div className="min-h-screen bg-background text-foreground flex flex-col justify-center items-center py-8 px-4 sm:px-6">
      <main className="w-full max-w-md">
        {updateSuccess ? (
          <div className="bg-card rounded-lg border border-border p-6 md:p-8 shadow-sm text-center space-y-4">
            <div className="mx-auto w-14 h-14 rounded-full bg-primary/15 text-primary flex items-center justify-center">
              <CheckCircle2 className="w-8 h-8" strokeWidth={1.5} />
            </div>
            <div className="space-y-1.5">
              <h2 className="font-serif text-2xl font-bold text-foreground">Password updated</h2>
              <p className="text-sm text-muted-foreground">
                {forced
                  ? 'You’re all set. Use your new password the next time you sign in.'
                  : 'Use your new password the next time you sign in. Any other devices you were signed in on have been signed out.'}
              </p>
            </div>
            <Button onClick={goToApp}>{forced ? 'Continue' : 'Back to the app'}</Button>
          </div>
        ) : (
          <>
            <div className="flex flex-col items-center mb-6 text-center">
              <div className="w-12 h-12 rounded-2xl bg-primary/10 text-primary flex items-center justify-center mb-3">
                <KeyRound className="w-6 h-6" />
              </div>
              <h2 className="text-[28px] leading-tight font-bold mb-2 font-serif text-foreground">
                {forced ? 'Choose your password' : 'Change password'}
              </h2>
              <p className="text-muted-foreground text-sm max-w-sm">
                {forced
                  ? 'Your workspace admin set up your account with a temporary password. Choose your own to continue.'
                  : 'Use a strong password that you don’t use for anything else.'}
              </p>
              {user?.email && <p className="text-xs font-mono text-muted-foreground mt-2">{user.email}</p>}
            </div>

            <div className="bg-card rounded-lg border border-border p-4 md:p-6 lg:p-8 shadow-sm">
              {error && (
                <div
                  role="alert"
                  className="bg-destructive/10 border border-destructive/20 text-destructive text-xs py-2.5 px-3 rounded-lg mb-4 flex items-start gap-2"
                >
                  <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
                  <p className="grow">{error}</p>
                </div>
              )}

              <form className="space-y-4" onSubmit={handleSubmit} noValidate>
                <Input
                  label={forced ? 'Temporary password' : 'Current password'}
                  id="current-password"
                  type={showCurrent ? 'text' : 'password'}
                  autoComplete="current-password"
                  value={currentPassword}
                  onChange={(event) => setCurrentPassword(event.target.value)}
                  leftElement={<UserRoundKey className="w-4 h-4" />}
                  helperText={forced ? 'The one from your invitation email.' : undefined}
                  rightElementInside={
                    <button
                      type="button"
                      onClick={() => setShowCurrent((value) => !value)}
                      className="text-muted-foreground hover:text-foreground transition-colors cursor-pointer flex items-center"
                      aria-label={showCurrent ? 'Hide password' : 'Show password'}
                    >
                      {showCurrent ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  }
                />

                <Input
                  label="New password"
                  id="new-password"
                  type={showNew ? 'text' : 'password'}
                  autoComplete="new-password"
                  value={newPassword}
                  onChange={(event) => setNewPassword(event.target.value)}
                  leftElement={<UserRoundKey className="w-4 h-4" />}
                  rightElementInside={
                    <button
                      type="button"
                      onClick={() => setShowNew((value) => !value)}
                      className="text-muted-foreground hover:text-foreground transition-colors cursor-pointer flex items-center"
                      aria-label={showNew ? 'Hide password' : 'Show password'}
                    >
                      {showNew ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  }
                />

                <ul className="bg-muted/30 rounded-lg p-3 space-y-1.5 border border-border/40 text-xs" aria-label="Password requirements">
                  <Requirement met={checks.length}>At least 12 characters</Requirement>
                  <Requirement met={checks.mixedCase}>Upper and lower case letters</Requirement>
                  <Requirement met={checks.numberAndSymbol}>A number and a symbol</Requirement>
                </ul>

                <Input
                  label="Confirm new password"
                  id="confirm-password"
                  type={showNew ? 'text' : 'password'}
                  autoComplete="new-password"
                  value={confirmPassword}
                  onChange={(event) => setConfirmPassword(event.target.value)}
                  leftElement={<UserRoundKey className="w-4 h-4" />}
                  error={confirmPassword && confirmPassword !== newPassword ? 'The passwords don’t match.' : undefined}
                />

                <Button type="submit" isLoading={isUpdateLoading} loadingText="Saving…" className="mt-2">
                  {forced ? 'Save password and continue' : 'Update password'}
                </Button>
              </form>

              <div className="mt-6 pt-5 border-t border-border text-center">
                {forced ? (
                  <button
                    type="button"
                    onClick={signOut}
                    className="inline-flex items-center gap-1.5 text-xs font-semibold text-muted-foreground hover:text-primary transition-colors cursor-pointer"
                  >
                    <LogOut className="w-4 h-4" />
                    Sign out
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={goToApp}
                    className="text-xs font-semibold text-muted-foreground hover:text-primary transition-colors cursor-pointer"
                  >
                    Cancel
                  </button>
                )}
              </div>
            </div>
          </>
        )}

        <div className="mt-8 text-center space-y-2 select-none">
          <div className="flex justify-center gap-4 text-xs">
            <Link to="/privacy" className="text-muted-foreground hover:text-primary transition-colors">
              Privacy Policy
            </Link>
            <span className="text-border">•</span>
            <Link to="/terms" className="text-muted-foreground hover:text-primary transition-colors">
              Terms of Service
            </Link>
          </div>
          <p className="font-mono text-[12px] text-muted-foreground/90">© {new Date().getFullYear()} RoleSync AI.</p>
        </div>
      </main>
    </div>
  );
};

export default Changepassword;
