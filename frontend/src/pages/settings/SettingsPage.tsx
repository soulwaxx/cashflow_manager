import { NavLink, Outlet } from 'react-router-dom';

const tabs = [
  { to: 'payment-methods', label: 'Payment methods' },
  { to: 'categories', label: 'Categories' },
  { to: 'tax-config', label: 'Tax config' },
  { to: 'account', label: 'Account' },
];

export default function SettingsPage() {
  return (
    <div className="max-w-4xl space-y-4">
      <h1 className="text-xl font-bold text-primary">Settings</h1>
      <nav aria-label="Settings sections" className="grid grid-cols-2 gap-2 sm:flex sm:gap-1 border-b border-line">
        {tabs.map((t) => (
          <NavLink
            key={t.to}
            to={t.to}
            className={({ isActive }) =>
              `min-h-11 flex items-center justify-center px-3 py-2 text-center text-sm rounded-t-lg border-b-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-600 ${isActive ? 'border-blue-600 text-blue-700 dark:text-blue-400 font-medium' : 'border-transparent text-secondary hover:text-secondary'}`
            }
          >
            {t.label}
          </NavLink>
        ))}
      </nav>
      <div>
        <Outlet />
      </div>
    </div>
  );
}
