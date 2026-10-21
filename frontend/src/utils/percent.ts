const PERCENT_TEXT = /^(?:\d+)(?:\.\d{0,2})?$/;

/** Convert a percentage string into the backend's four-decimal fraction schema. */
export function percentToFraction(value: string): number | undefined {
  const text = value.trim();
  if (text === '') return 0;
  if (!PERCENT_TEXT.test(text)) return undefined;
  const [wholeText, fractionText = ''] = text.split('.');
  const whole = Number(wholeText);
  const hundredths = Number(fractionText.padEnd(2, '0') || '0');
  if (!Number.isSafeInteger(whole) || whole > 100 || (whole === 100 && hundredths > 0)) return undefined;
  return (whole * 100 + hundredths) / 10000;
}

/** Display a backend four-decimal fractional rate without binary-float tails. */
export function fractionToPercentText(value: number): string {
  if (!Number.isFinite(value) || value < 0 || value > 1) return '';
  const units = Math.round(Number(value.toFixed(4)) * 10000);
  const whole = Math.floor(units / 100);
  const hundredths = units % 100;
  return hundredths === 0 ? String(whole) : `${whole}.${String(hundredths).padStart(2, '0').replace(/0+$/, '')}`;
}
