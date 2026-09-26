import { BANK_BALANCE_LINE_COLOR, formatBalanceTick } from '../../src/components/dashboard/BankBalanceTrend';

test('chart line color references the light/dark theme token', () => {
  expect(BANK_BALANCE_LINE_COLOR).toBe('var(--color-chart-line)');
});

test.each([
  [0, '€0'],
  [400, '€400'],
  [-400, '−€400'],
  [1500, '€1.5k'],
  [-1500, '−€1.5k'],
  [12500, '€12.5k'],
])('formats balance axis tick %s as %s', (value, expected) => {
  expect(formatBalanceTick(value)).toBe(expected);
});
