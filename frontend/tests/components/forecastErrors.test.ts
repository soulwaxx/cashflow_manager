import { expect, test } from 'vitest';
import { forecastError } from '../../src/components/forecasting/forecastErrors';

test('model-level API validation errors display the actual reason', () => {
  const result = forecastError({ response: { data: {
    detail: [{ loc: ['body'], msg: 'An adjustment already exists for this month' }],
  } } });
  expect(result.message).toContain('already exists');
  expect(result.fields).toEqual({});
});
