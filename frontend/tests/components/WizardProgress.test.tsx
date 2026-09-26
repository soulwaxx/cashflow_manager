import { render, screen } from '@testing-library/react';
import WizardProgress from '../../src/components/onboarding/WizardProgress';

test('WizardProgress shows current step out of total', () => {
  render(<WizardProgress current={3} total={8} />);
  expect(screen.getByText(/step 3 of 8/i)).toBeInTheDocument();
});

test('WizardProgress highlights completed steps', () => {
  render(<WizardProgress current={3} total={8} />);
  const steps = screen.getAllByRole('listitem');
  // Steps 1 and 2 are completed; step 3 is active
  expect(steps[0]).toHaveClass('bg-blue-600');
  expect(steps[1]).toHaveClass('bg-blue-600');
  expect(steps[2]).toHaveClass('bg-blue-300');
  expect(steps[2]).toHaveAttribute('aria-current', 'step');
  expect(screen.getByRole('list', { name: 'Setup progress' })).toBeInTheDocument();
});
