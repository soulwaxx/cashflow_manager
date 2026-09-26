import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '../../hooks/useAuth';
import { authApi } from '../../api/auth';
import { Button } from '../../components/ui/Button';
import Modal from '../../components/ui/Modal';
import { Input } from '../../components/ui/Input';

export default function AccountSettings() {
  const { user, logout } = useAuth();
  const qc = useQueryClient();
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [password, setPassword] = useState('');
  const [changePwOpen, setChangePwOpen] = useState(false);
  const [currentPw, setCurrentPw] = useState('');
  const [newPw, setNewPw] = useState('');
  const [confirmPw, setConfirmPw] = useState('');
  const [changePwError, setChangePwError] = useState<string | null>(null);
  const [changePwDone, setChangePwDone] = useState(false);
  const requiresDeletePassword = Boolean(user?.has_password);

  const { mutate: changePassword, isPending: changePwPending } = useMutation({
    mutationFn: () => authApi.changePassword(currentPw, newPw),
    onSuccess: () => {
      setChangePwDone(true);
      setCurrentPw(''); setNewPw(''); setConfirmPw('');
      setChangePwError(null);
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setChangePwError(detail ?? 'Failed to change password. Please try again.');
    },
  });

  const { mutate: deleteAccount, isPending, error: deleteError } = useMutation({
    mutationFn: () => authApi.deleteMe(requiresDeletePassword ? password : undefined),
    onSuccess: () => {
      // Don't call logout() — the backend already cleared the JWT cookie.
      // Calling authApi.logout() would hit a dead session.
      qc.clear();
      window.location.href = '/login';
    },
  });

  return (
    <div className="space-y-4 max-w-lg min-w-0">
      <div className="bg-surface border border-line rounded-lg p-4 text-sm space-y-2">
        <div className="break-all"><span className="text-muted">Email: </span><span className="font-medium text-primary">{user?.email}</span></div>
        <div><span className="text-muted">Name: </span><span className="font-medium text-primary">{user?.name}</span></div>
        <div className="flex gap-2 text-xs text-faint">
          {user?.has_password && <span>Password auth</span>}
          {user?.has_oidc && <span>OIDC / SSO</span>}
        </div>
      </div>
      <div className="flex gap-2 flex-wrap">
        <Button variant="secondary" onClick={logout}>Sign out</Button>
        {user?.has_password && (
          <Button variant="secondary" onClick={() => { setChangePwOpen(true); setChangePwDone(false); setChangePwError(null); }}>
            Change password
          </Button>
        )}
        <Button
          variant="ghost"
          className="text-red-600 dark:text-red-400 hover:text-red-700"
          onClick={() => setDeleteOpen(true)}
        >
          Delete account
        </Button>
      </div>

      <Modal
        open={changePwOpen}
        onClose={() => { setChangePwOpen(false); setCurrentPw(''); setNewPw(''); setConfirmPw(''); setChangePwError(null); setChangePwDone(false); }}
        title="Change password"
      >
        {changePwDone ? (
          <div className="text-sm text-green-700 dark:text-green-400 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded p-3">
            Password changed successfully.
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            <Input
              label="Current password"
              type="password"
              value={currentPw}
              onChange={(e) => setCurrentPw(e.target.value)}
              placeholder="Current password"
            />
            <Input
              label="New password"
              type="password"
              value={newPw}
              onChange={(e) => setNewPw(e.target.value)}
              placeholder="At least 8 characters"
            />
            <Input
              label="Confirm new password"
              type="password"
              value={confirmPw}
              onChange={(e) => setConfirmPw(e.target.value)}
              placeholder="Repeat new password"
            />
            {changePwError && <p className="text-xs text-red-600">{changePwError}</p>}
            {newPw && confirmPw && newPw !== confirmPw && (
              <p className="text-xs text-red-600">Passwords do not match.</p>
            )}
            <Button
              isLoading={changePwPending}
              disabled={!currentPw || !newPw || newPw !== confirmPw || newPw.length < 8 || changePwPending}
              onClick={() => changePassword()}
            >
              Update password
            </Button>
          </div>
        )}
      </Modal>

      <Modal
        open={deleteOpen}
        onClose={() => { setDeleteOpen(false); setPassword(''); }}
        title="Delete account"
      >
        <div className="flex flex-col gap-4">
          <div className="text-sm text-secondary bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded p-3 space-y-1">
            <p className="font-semibold text-red-700 dark:text-red-400">This action is irreversible.</p>
            <p>All your data will be permanently deleted: transactions, transfers, salary configs, assets, and your account.</p>
          </div>
          {requiresDeletePassword ? (
            <Input
              label="Enter your password to confirm"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Password"
            />
          ) : (
            <p className="text-sm text-secondary">
              Your account uses OIDC / SSO only. No password confirmation is required.
            </p>
          )}
          {deleteError && (
            <p className="text-xs text-red-600">Failed to delete account. Please try again.</p>
          )}
          <Button
            isLoading={isPending}
            className="bg-red-600 hover:bg-red-700 text-white disabled:opacity-50"
            disabled={(requiresDeletePassword && !password) || isPending}
            onClick={() => deleteAccount()}
          >
            Permanently delete account
          </Button>
        </div>
      </Modal>
    </div>
  );
}
