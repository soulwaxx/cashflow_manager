import { NavLink } from 'react-router-dom';
import { useAuth } from '../../hooks/useAuth';
import { useTheme } from '../../hooks/useTheme';
import { Button } from '../ui/Button';

const primaryLinks = [
  { to: '/', label: 'Dashboard' },
  { to: '/transactions', label: 'Transactions' },
  { to: '/summary', label: 'Summary' },
  { to: '/assets', label: 'Assets' },
];
const otherLinks = [
  { to: '/transfers', label: 'Transfers' },
  { to: '/salary', label: 'Salary' },
  { to: '/analytics', label: 'Analytics' },
  { to: '/forecasting', label: 'Forecasting' },
  { to: '/settings', label: 'Settings' },
];

interface SidebarProps {
  onClose?: () => void;
}

export default function Sidebar({ onClose }: SidebarProps = {}) {
  const { logout } = useAuth();
  const { dark, toggle } = useTheme();
  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `block min-h-11 px-4 py-3 text-sm rounded-lg mx-2 transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700 ${isActive ? 'bg-blue-50 dark:bg-blue-900/40 text-blue-800 dark:text-blue-200 font-semibold' : 'text-secondary hover:bg-muted-bg'}`;
  const links = (items: typeof primaryLinks) => items.map((link) => (
    <NavLink key={link.to} to={link.to} end={link.to === '/'} onClick={onClose} className={linkClass}>
      {link.label}
    </NavLink>
  ));

  return (
    <nav aria-label="Main navigation" className="w-60 bg-surface border-r border-line flex flex-col py-4 gap-1 min-h-full">
      <div className="px-4 pb-5 flex items-center justify-between">
        <span className="font-bold text-lg text-blue-900 dark:text-blue-300">CashFlow</span>
        {onClose && (
          <button onClick={onClose} aria-label="Close menu" className="p-2 rounded text-secondary hover:bg-muted-bg md:hidden min-h-11 min-w-11">
            <span aria-hidden="true">×</span>
          </button>
        )}
      </div>
      <p className="px-4 mx-2 mb-1 text-xs font-semibold uppercase tracking-wide text-muted">Overview</p>
      {links(primaryLinks)}
      <p className="px-4 mx-2 mt-5 mb-1 text-xs font-semibold uppercase tracking-wide text-muted">Manage</p>
      {links(otherLinks)}
      <div className="mt-auto px-4 flex flex-col gap-2 pt-4">
        <button onClick={toggle} aria-label="Toggle dark mode" className="w-full text-left px-3 py-3 min-h-11 text-sm rounded-lg text-secondary hover:bg-muted-bg transition-colors">
          {dark ? '☀ Light mode' : '◐ Dark mode'}
        </button>
        <Button variant="ghost" className="w-full text-left" onClick={logout}>Sign out</Button>
      </div>
    </nav>
  );
}
