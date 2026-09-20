import { render, screen } from '@testing-library/react';
import OutcomesByMethod from '../../src/components/dashboard/OutcomesByMethod';

test('OutcomesByMethod displays a refund as a positive net amount', () => {
  render(
    <OutcomesByMethod
      isLoading={false}
      summary={{
        year: 2026,
        month: 1,
        incomes: 0,
        outcomes_by_method: { 'Debit card': -25 },
        transfers_out_bank: 0,
        transfers_in_bank: 0,
        bank_balance: 5025,
      }}
    />,
  );

  expect(screen.getByText('Net purchases and card payments')).toBeInTheDocument();
  expect(screen.getByText('+€25,00')).toBeInTheDocument();
});
