import { useForm } from 'react-hook-form';
import { useQuery } from '@tanstack/react-query';
import { useOnboarding } from '../../contexts/OnboardingContext';
import { salaryApi } from '../../api/salary';
import { queryKeys } from '../../api/queryKeys';
import { Input } from '../ui/Input';
import { Button } from '../ui/Button';
import { fmt } from '../../utils/format';

interface SalaryFields {
  ral_str: string;
  employer_contrib_rate_pct: string;
  voluntary_contrib_rate_pct: string;
  regional_tax_rate_pct: string;
  municipal_tax_rate_pct: string;
  meal_vouchers_annual: string;
  welfare_annual: string;
  salary_months: string;
}

export default function StepSalaryConfig() {
  const { updateData, setStep } = useOnboarding();
  const { register, watch, handleSubmit } = useForm<SalaryFields>({
    defaultValues: {
      employer_contrib_rate_pct: '4',
      voluntary_contrib_rate_pct: '0',
      regional_tax_rate_pct: '1.73',
      municipal_tax_rate_pct: '0.1',
      meal_vouchers_annual: '0',
      welfare_annual: '0',
      salary_months: '12',
    },
  });
  const ral = parseFloat(watch('ral_str') || '0');
  const employer = parseFloat(watch('employer_contrib_rate_pct') || '0') / 100;
  const voluntary = parseFloat(watch('voluntary_contrib_rate_pct') || '0') / 100;
  const regional = parseFloat(watch('regional_tax_rate_pct') || '0') / 100;
  const municipal = parseFloat(watch('municipal_tax_rate_pct') || '0') / 100;
  const salaryMonths = parseInt(watch('salary_months') || '12') || 12;

  const today = new Date().toISOString().slice(0, 7);
  const { data: preview } = useQuery({
    queryKey: queryKeys.salary.calculate({ as_of: today, ral, employer, voluntary, regional, municipal, salaryMonths }),
    queryFn: () =>
      salaryApi.calculate({
        as_of: today,
        ral,
        employer_contrib_rate: employer,
        voluntary_contrib_rate: voluntary,
        regional_tax_rate: regional,
        municipal_tax_rate: municipal,
        salary_months: salaryMonths,
      }),
    enabled: ral > 0,
    staleTime: 0,
  });

  const onSubmit = (d: SalaryFields) => {
    const ral = parseFloat(d.ral_str);
    if (!ral || isNaN(ral)) {
      setStep(8);
      return;
    }
    const pct = (s: string) => (parseFloat(s) || 0) / 100;
    updateData({
      salary: {
        ral,
        employer_contrib_rate: pct(d.employer_contrib_rate_pct),
        voluntary_contrib_rate: pct(d.voluntary_contrib_rate_pct),
        regional_tax_rate: pct(d.regional_tax_rate_pct),
        municipal_tax_rate: pct(d.municipal_tax_rate_pct),
        meal_vouchers_annual: parseFloat(d.meal_vouchers_annual) || 0,
        welfare_annual: parseFloat(d.welfare_annual) || 0,
        salary_months: parseInt(d.salary_months) || 12,
      },
    });
    setStep(8);
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4">
      <h2 className="text-lg font-semibold">Salary configuration (optional)</h2>
      <Input label="RAL (€)" type="number" step="100" {...register('ral_str')} />
      <Input label="Employer pension rate (%)" type="number" step="0.01" {...register('employer_contrib_rate_pct')} />
      <Input label="Voluntary pension rate (%)" type="number" step="0.01" {...register('voluntary_contrib_rate_pct')} />
      <Input label="Regional tax rate (%)" type="number" step="0.001" {...register('regional_tax_rate_pct')} />
      <Input label="Municipal tax rate (%)" type="number" step="0.001" {...register('municipal_tax_rate_pct')} />
      <Input label="Meal vouchers annual (€)" type="number" step="1" {...register('meal_vouchers_annual')} />
      <Input label="Welfare annual (€)" type="number" step="1" {...register('welfare_annual')} />

      <div className="flex flex-col gap-1">
        <label htmlFor="setup-salary-months" className="text-sm font-medium text-secondary">Salary months</label>
        <select
          id="setup-salary-months"
          {...register('salary_months')}
          className="min-h-11 border border-line-strong rounded-lg px-3 py-2 text-base sm:text-sm bg-elevated text-primary"
        >
          <option value="12">12 (standard)</option>
          <option value="13">13 (tredicesima)</option>
          <option value="14">14 (tredicesima + quattordicesima)</option>
        </select>
      </div>

      {preview && (
        <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-3 text-sm space-y-1">
          <div className="font-medium text-blue-800 dark:text-blue-300">Estimated net: €{fmt(preview.net_monthly)}/mo</div>
          <div className="text-secondary">Social security: €{fmt(preview.social_security)} · Income tax: €{fmt(preview.income_tax_net)}</div>
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        <Button variant="secondary" type="button" onClick={() => setStep(6)}>Back</Button>
        <Button variant="ghost" type="button" onClick={() => setStep(8)}>Skip</Button>
        <Button type="submit">Next</Button>
      </div>
    </form>
  );
}
