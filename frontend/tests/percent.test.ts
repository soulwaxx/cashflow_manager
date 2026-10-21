import { fractionToPercentText, percentToFraction } from '../src/utils/percent';

test('percentage transport preserves hundredth-of-percent precision in backend fractions', () => {
  expect(percentToFraction('0.07')).toBe(0.0007);
  expect(percentToFraction('2.01')).toBe(0.0201);
  expect(percentToFraction('100')).toBe(1);
  expect(fractionToPercentText(0.0007)).toBe('0.07');
  expect(fractionToPercentText(0.0201)).toBe('2.01');
  expect(fractionToPercentText(0.001)).toBe('0.1');
});

test.each(['0.001', '101', '-1', '1e-3'])('rejects unsupported percentage input %s', (value) => {
  expect(percentToFraction(value)).toBeUndefined();
});
