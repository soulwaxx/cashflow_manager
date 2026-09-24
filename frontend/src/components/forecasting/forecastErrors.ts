export function forecastError(error: unknown): { message: string; fields: Record<string, string> } {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof detail === 'string') return { message: detail, fields: {} };
  if (Array.isArray(detail)) {
    const fields: Record<string, string> = {};
    const general: string[] = [];
    for (const issue of detail) {
      const field = issue?.loc?.at(-1);
      if (typeof issue?.msg !== 'string') continue;
      if (typeof field === 'string' && field !== 'body') fields[field] = issue.msg;
      else general.push(issue.msg);
    }
    return {
      message: general.length ? general.join('; ') : 'Please correct the highlighted fields.',
      fields,
    };
  }
  return { message: 'Could not save. Please try again.', fields: {} };
}
