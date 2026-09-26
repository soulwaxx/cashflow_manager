import { useEffect, useRef, useState } from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';

const mobileLinks = [
  { to: '/', label: 'Dashboard', icon: '⌂' },
  { to: '/transactions', label: 'Transactions', icon: '↕' },
  { to: '/summary', label: 'Summary', icon: '▤' },
  { to: '/assets', label: 'Assets', icon: '◈' },
];

export default function AppShell() {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuTriggerRef = useRef<HTMLButtonElement>(null);
  const drawerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    const focusableSelector = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';
    const focusableElements = () => Array.from(drawerRef.current?.querySelectorAll<HTMLElement>(focusableSelector) ?? []);
    focusableElements()[0]?.focus();

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        setMenuOpen(false);
        return;
      }
      if (event.key !== 'Tab') return;
      const focusable = focusableElements();
      if (focusable.length === 0) {
        event.preventDefault();
      } else if (event.shiftKey && document.activeElement === focusable[0]) {
        event.preventDefault();
        focusable[focusable.length - 1].focus();
      } else if (!event.shiftKey && document.activeElement === focusable[focusable.length - 1]) {
        event.preventDefault();
        focusable[0].focus();
      }
    };
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      menuTriggerRef.current?.focus();
    };
  }, [menuOpen]);

  return (
    <div className="flex h-screen bg-canvas text-primary">
      <div className="hidden md:flex shrink-0"><Sidebar /></div>
      {menuOpen && (
        <div className="fixed inset-0 z-40 md:hidden">
          <button aria-label="Close navigation menu" className="absolute inset-0 bg-black/50" onClick={() => setMenuOpen(false)} />
          <div ref={drawerRef} role="dialog" aria-modal="true" aria-label="More navigation" className="relative z-50 h-full max-h-dvh w-64 overflow-y-auto overscroll-contain bg-surface shadow-xl"><Sidebar onClose={() => setMenuOpen(false)} /></div>
        </div>
      )}
      <div className="flex flex-col flex-1 min-w-0">
        <header className="md:hidden flex items-center justify-between px-4 h-14 bg-surface border-b border-line shrink-0">
          <span className="font-bold text-blue-900 dark:text-blue-300">CashFlow</span>
          <button ref={menuTriggerRef} onClick={(event) => { menuTriggerRef.current = event.currentTarget; setMenuOpen(true); }} aria-label="Open navigation menu" aria-expanded={menuOpen} className="px-3 py-2 min-h-11 rounded-lg text-secondary hover:bg-muted-bg focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-700">
            <span aria-hidden="true">☰</span>
          </button>
        </header>
        <main className="flex-1 overflow-auto bg-canvas p-4 pb-24 md:p-6 md:pb-6">
          <Outlet />
        </main>
        <nav aria-label="Primary navigation" className="md:hidden fixed bottom-0 inset-x-0 z-30 grid grid-cols-5 bg-surface border-t border-line pb-[env(safe-area-inset-bottom)]">
          {mobileLinks.map((link) => (
            <NavLink key={link.to} to={link.to} end={link.to === '/'} className={({ isActive }) => `flex min-h-14 flex-col items-center justify-center gap-0.5 text-xs ${isActive ? 'text-blue-800 dark:text-blue-300 font-semibold' : 'text-secondary'} focus-visible:outline focus-visible:outline-2 focus-visible:outline-inset focus-visible:outline-blue-700`}>
              <span aria-hidden="true" className="text-lg leading-5">{link.icon}</span>{link.label}
            </NavLink>
          ))}
          <button ref={menuTriggerRef} type="button" aria-label="More" aria-haspopup="dialog" aria-expanded={menuOpen} onClick={(event) => { menuTriggerRef.current = event.currentTarget; setMenuOpen(true); }} className="flex min-h-14 flex-col items-center justify-center gap-0.5 text-xs text-secondary focus-visible:outline focus-visible:outline-2 focus-visible:outline-inset focus-visible:outline-blue-700">
            <span aria-hidden="true" className="text-lg leading-5">☰</span>More
          </button>
        </nav>
      </div>
    </div>
  );
}
