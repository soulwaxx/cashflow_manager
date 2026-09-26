import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { server } from '../mocks/server';
import App from '../../src/App';

function renderApp(path = '/') {
  window.history.pushState({}, '', path);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <App />
    </QueryClientProvider>
  );
}

test('unauthenticated user is redirected to /login', async () => {
  server.use(
    http.get('/api/v1/auth/me', () => HttpResponse.json(null, { status: 401 }))
  );
  renderApp('/');
  await waitFor(() =>
    expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument()
  );
});

test('unauthenticated user visiting /setup is redirected to /login', async () => {
  server.use(
    http.get('/api/v1/auth/me', () => HttpResponse.json(null, { status: 401 }))
  );
  renderApp('/setup');
  await waitFor(() =>
    expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument()
  );
});

test('authenticated user with onboarding complete sees dashboard', async () => {
  renderApp('/');
  await waitFor(() =>
    expect(screen.getByRole('navigation', { name: 'Primary navigation' })).toHaveTextContent('Dashboard')
  );
});

test('mobile navigation keeps primary destinations visible and exposes other routes from More', async () => {
  const user = userEvent.setup();
  renderApp('/');
  await waitFor(() => expect(screen.getByRole('navigation', { name: 'Primary navigation' })).toBeInTheDocument());
  const primary = screen.getByRole('navigation', { name: 'Primary navigation' });
  expect(primary).toHaveTextContent('Dashboard');
  expect(primary).toHaveTextContent('Transactions');
  expect(primary).toHaveTextContent('Summary');
  expect(primary).toHaveTextContent('Assets');
  expect(within(primary).getAllByRole('link')).toHaveLength(4);
  await user.click(screen.getByRole('button', { name: 'More' }));
  expect(screen.getByRole('dialog', { name: 'More navigation' })).toBeInTheDocument();
  const drawerNavs = screen.getAllByRole('navigation', { name: 'Main navigation' });
  expect(drawerNavs[drawerNavs.length - 1]).toHaveTextContent('Forecasting');
  const transferLinks = screen.getAllByRole('link', { name: 'Transfers' });
  await user.click(transferLinks[transferLinks.length - 1]);
  await waitFor(() => expect(window.location.pathname).toBe('/transfers'));
});

test('More drawer traps keyboard focus, closes on Escape, restores its trigger, and scrolls on short screens', async () => {
  const user = userEvent.setup();
  renderApp('/');
  await screen.findByRole('navigation', { name: 'Primary navigation' });
  const moreTab = screen.getByRole('button', { name: 'More' });
  await user.click(moreTab);

  const drawer = screen.getByRole('dialog', { name: 'More navigation' });
  const first = within(drawer).getByRole('button', { name: 'Close menu' });
  const last = within(drawer).getByRole('button', { name: 'Sign out' });
  expect(first).toHaveFocus();
  expect(within(drawer).getByRole('button', { name: 'Toggle dark mode' })).toBeInTheDocument();
  expect(drawer).toHaveClass('overflow-y-auto');
  expect(within(drawer).getByRole('navigation', { name: 'Main navigation' })).toHaveClass('min-h-full');

  last.focus();
  await user.tab();
  expect(first).toHaveFocus();
  await user.keyboard('{Escape}');
  await waitFor(() => expect(screen.queryByRole('dialog', { name: 'More navigation' })).not.toBeInTheDocument());
  expect(moreTab).toHaveFocus();
});

test('authenticated user with incomplete onboarding is redirected to /setup', async () => {
  server.use(
    http.get('/api/v1/onboarding/status', () =>
      HttpResponse.json({ complete: false })
    )
  );
  renderApp('/');
  await waitFor(() =>
    expect(screen.getByText(/setup your account/i)).toBeInTheDocument()
  );
});
