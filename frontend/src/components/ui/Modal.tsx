import { useEffect, useId, useRef } from 'react';

interface Props {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  fullScreenMobile?: boolean;
}

export default function Modal({ open, onClose, title, children, fullScreenMobile = false }: Props) {
  const titleId = useId();
  const dialogRef = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    if (!open) return;
    const previouslyFocused = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    document.body.style.overflow = 'hidden';
    const focusableSelector = [
      'a[href]',
      'button:not([disabled])',
      'textarea:not([disabled])',
      'input:not([disabled])',
      'select:not([disabled])',
      '[tabindex]:not([tabindex="-1"])',
    ].join(',');
    const focusableElements = () =>
      Array.from(dialogRef.current?.querySelectorAll<HTMLElement>(focusableSelector) ?? [])
        .filter((el) => !el.hasAttribute('disabled'));

    (focusableElements()[0] ?? dialogRef.current)?.focus();

    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onCloseRef.current();
        return;
      }
      if (e.key !== 'Tab') return;
      const focusable = focusableElements();
      if (focusable.length === 0) {
        e.preventDefault();
        dialogRef.current?.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', handler);
    return () => {
      document.body.style.overflow = '';
      document.removeEventListener('keydown', handler);
      previouslyFocused?.focus();
    };
  }, [open]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/40">
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className={`bg-surface shadow-xl p-5 pb-[max(1.25rem,env(safe-area-inset-bottom))] sm:p-6 w-full ${fullScreenMobile ? 'h-full max-h-full rounded-none sm:h-auto sm:max-h-[90vh] sm:rounded-xl' : 'max-h-[90dvh] rounded-t-2xl sm:rounded-xl'} sm:max-w-lg overflow-y-auto overscroll-contain`}
      >
        <div className="flex justify-between items-center mb-4">
          <h2 id={titleId} className="text-lg font-semibold text-primary">{title}</h2>
          <button aria-label="Close modal" onClick={onClose} className="min-h-11 min-w-11 rounded-lg text-faint hover:text-secondary text-xl focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-600">×</button>
        </div>
        {children}
      </div>
    </div>
  );
}
