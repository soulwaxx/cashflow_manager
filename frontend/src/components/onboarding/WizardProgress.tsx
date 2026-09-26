interface Props {
  current: number;
  total: number;
}

export default function WizardProgress({ current, total }: Props) {
  return (
    <div className="mb-6">
      <p className="text-sm text-muted mb-2" role="status">Step {current} of {total}</p>
      <ol aria-label="Setup progress" className="flex gap-1">
        {Array.from({ length: total }, (_, i) => {
          const n = i + 1;
          const done = n < current;
          const active = n === current;
          return (
            <li
              key={n}
              aria-label={`Step ${n}${active ? ', current' : done ? ', complete' : ''}`}
              aria-current={active ? 'step' : undefined}
              className={`h-2 flex-1 rounded-full ${done ? 'bg-blue-600' : active ? 'bg-blue-300 dark:bg-blue-500' : 'bg-muted-bg'}`}
            />
          );
        })}
      </ol>
    </div>
  );
}
