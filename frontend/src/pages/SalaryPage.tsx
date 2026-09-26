import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { salaryApi } from '../api/salary';
import { taxConfigApi } from '../api/taxConfig';
import { queryKeys, invalidateFor } from '../api/queryKeys';
import { Input } from '../components/ui/Input';
import { Button } from '../components/ui/Button';
import Modal from '../components/ui/Modal';
import type { SalaryConfig } from '../types/api';
import { fmt } from '../utils/format';

function BreakdownPanel({ config }: { config: SalaryConfig }) {
  const calculateParams = {
    as_of: config.valid_from,
    ral: config.ral,
    employer_contrib_rate: config.employer_contrib_rate,
    voluntary_contrib_rate: config.voluntary_contrib_rate,
    regional_tax_rate: config.regional_tax_rate,
    municipal_tax_rate: config.municipal_tax_rate,
    meal_vouchers_annual: config.meal_vouchers_annual,
    welfare_annual: config.welfare_annual,
    salary_months: config.salary_months,
  };

  const { data: breakdown } = useQuery({
    queryKey: queryKeys.salary.calculate(calculateParams),
    queryFn: () => salaryApi.calculate(calculateParams),
  });

  const { data: taxConfigs = [] } = useQuery({
    queryKey: queryKeys.taxConfig.all,
    queryFn: taxConfigApi.list,
  });

  if (!breakdown) return null;

  const pensionCap = taxConfigs[taxConfigs.length - 1]?.pension_deductibility_cap ?? 5300;
  const employerPension = config.employer_contrib_rate * config.ral;
  const voluntaryPension = config.voluntary_contrib_rate * config.ral;

  const row = (label: string, val: number, negative = false, muted = false, indent = false) => (
    <div key={label} className={`flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 ${indent ? 'ml-3' : ''}`}>
      <span className={muted ? 'text-faint text-xs' : 'text-secondary'}>{label}</span>
      <span className={`tabular-nums font-medium text-xs ${negative ? 'text-red-500' : muted ? 'text-faint' : 'text-primary'}`}>
        {negative ? '−' : ''}€{fmt(Math.abs(val))}
      </span>
    </div>
  );

  return (
    <div className="bg-subtle border border-line rounded-lg p-4 text-sm space-y-2 mt-4">
      <div className="font-medium text-secondary mb-2">Breakdown</div>

      {row('Gross annual', breakdown.gross_annual)}
      {row('Social security (INPS)', breakdown.social_security, true)}

      {/* Pension section */}
      <div className="pt-1 border-t border-line">
        {row(`Employer pension (${(config.employer_contrib_rate * 100).toFixed(2)}%)`, employerPension, false, true, true)}
        {config.voluntary_contrib_rate > 0 &&
          row(`Voluntary pension (${(config.voluntary_contrib_rate * 100).toFixed(2)}%)`, voluntaryPension, false, true, true)}
        {row('Total contributions', employerPension + voluntaryPension, false, true, true)}
        {row(
          `Deductible (cap €${fmt(pensionCap)})`,
          breakdown.pension_deductible,
          true,
          false,
          true,
        )}
      </div>

      {row('Taxable base', breakdown.taxable_base)}
      {row('Income tax gross', breakdown.income_tax_gross, true)}
      {row('Employment deduction', breakdown.employment_deduction)}
      {row('Income tax net', breakdown.income_tax_net, true)}
      {row('Regional surtax', breakdown.regional_surtax, true)}
      {row('Municipal surtax', breakdown.municipal_surtax, true)}

      <div className="border-t border-line pt-1">
        {row('Net annual', breakdown.net_annual)}
        {row(`Net monthly${config.salary_months !== 12 ? ` (÷${config.salary_months})` : ''}`, breakdown.net_monthly)}
      </div>

      {breakdown.meal_vouchers_monthly > 0 && (
        <div className="flex justify-between text-blue-600 dark:text-blue-400 pt-1 border-t border-line">
          <span>Meal vouchers/mo</span>
          <span>€{fmt(breakdown.meal_vouchers_monthly)}</span>
        </div>
      )}
      {breakdown.welfare_monthly > 0 && (
        <div className="flex justify-between text-blue-600 dark:text-blue-400">
          <span>Welfare/mo</span>
          <span>€{fmt(breakdown.welfare_monthly)}</span>
        </div>
      )}
    </div>
  );
}

// Rates stored as % strings in the form (e.g. "4" for 4% = 0.04)
interface PeriodFields {
  valid_from: string;
  ral: string;
  employer_contrib_rate_pct: string;
  voluntary_contrib_rate_pct: string;
  regional_tax_rate_pct: string;
  municipal_tax_rate_pct: string;
  meal_vouchers_annual: string;
  welfare_annual: string;
  salary_months: string;
  manual_net_override: string;
}

function configToFields(cfg: SalaryConfig): PeriodFields {
  return {
    valid_from: cfg.valid_from,
    ral: String(cfg.ral),
    employer_contrib_rate_pct: (cfg.employer_contrib_rate * 100).toFixed(3).replace(/\.?0+$/, ''),
    voluntary_contrib_rate_pct: (cfg.voluntary_contrib_rate * 100).toFixed(3).replace(/\.?0+$/, ''),
    regional_tax_rate_pct: (cfg.regional_tax_rate * 100).toFixed(4).replace(/\.?0+$/, ''),
    municipal_tax_rate_pct: (cfg.municipal_tax_rate * 100).toFixed(4).replace(/\.?0+$/, ''),
    meal_vouchers_annual: String(cfg.meal_vouchers_annual),
    welfare_annual: String(cfg.welfare_annual),
    salary_months: String(cfg.salary_months ?? 12),
    manual_net_override: cfg.manual_net_override == null ? '' : String(cfg.manual_net_override),
  };
}

function fieldsToBody(d: PeriodFields) {
  return {
    valid_from: d.valid_from,
    ral: parseFloat(d.ral),
    employer_contrib_rate: parseFloat(d.employer_contrib_rate_pct) / 100,
    voluntary_contrib_rate: parseFloat(d.voluntary_contrib_rate_pct) / 100,
    regional_tax_rate: parseFloat(d.regional_tax_rate_pct) / 100,
    municipal_tax_rate: parseFloat(d.municipal_tax_rate_pct) / 100,
    meal_vouchers_annual: parseFloat(d.meal_vouchers_annual) || 0,
    welfare_annual: parseFloat(d.welfare_annual) || 0,
    salary_months: parseInt(d.salary_months) || 12,
    manual_net_override: d.manual_net_override === '' ? null : parseFloat(d.manual_net_override),
  };
}

export default function SalaryPage() {
  const qc = useQueryClient();
  const [addOpen, setAddOpen] = useState(false);
  const [editConfig, setEditConfig] = useState<SalaryConfig | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const { data: configs = [], isLoading } = useQuery({
    queryKey: queryKeys.salary.list,
    queryFn: salaryApi.list,
  });

  const { register, handleSubmit, reset } = useForm<PeriodFields>({
    defaultValues: {
      employer_contrib_rate_pct: '4',
      voluntary_contrib_rate_pct: '0',
      regional_tax_rate_pct: '1.73',
      municipal_tax_rate_pct: '0.1',
      meal_vouchers_annual: '0',
      welfare_annual: '0',
      salary_months: '12',
      manual_net_override: '',
    },
  });

  const { register: regEdit, handleSubmit: handleEditSubmit, reset: resetEdit } = useForm<PeriodFields>();

  const { mutate: addPeriod, isPending: adding } = useMutation({
    mutationFn: (d: PeriodFields) => salaryApi.create(fieldsToBody(d)),
    onSuccess: () => {
      invalidateFor(qc, 'salary');
      setAddOpen(false);
      reset();
    },
  });

  const { mutate: updatePeriod, isPending: updating } = useMutation({
    mutationFn: (d: PeriodFields) => salaryApi.update(editConfig!.id, fieldsToBody(d)),
    onSuccess: () => {
      invalidateFor(qc, 'salary');
      setEditConfig(null);
    },
  });

  const selectedConfig = selectedId === null ? configs[configs.length - 1] : configs.find((c) => c.id === selectedId);

  const periodForm = (reg: typeof register, submitHandler: typeof handleSubmit, isPending: boolean, onSubmit: (d: PeriodFields) => void, hideDate = false) => (
    <form onSubmit={submitHandler(onSubmit)} className="flex flex-col gap-3">
      {!hideDate && <Input label="Valid from" type="date" {...reg('valid_from', { required: true })} />}
      <Input label="RAL (€)" type="number" step="100" required {...reg('ral', { required: true })} />
      <Input label="Employer pension rate (%)" type="number" step="0.01" required {...reg('employer_contrib_rate_pct', { required: true })} />
      <Input label="Voluntary pension rate (%)" type="number" step="0.01" {...reg('voluntary_contrib_rate_pct', { required: true })} />
      <Input label="Regional tax rate (%)" type="number" step="0.001" required {...reg('regional_tax_rate_pct', { required: true })} />
      <Input label="Municipal tax rate (%)" type="number" step="0.001" required {...reg('municipal_tax_rate_pct', { required: true })} />
      <Input label="Meal vouchers annual (€)" type="number" step="1" {...reg('meal_vouchers_annual', { required: true })} />
      <Input label="Welfare annual (€)" type="number" step="1" {...reg('welfare_annual', { required: true })} />
      <Input label="Manual net override (€ / month)" type="number" min="0" step="0.01" hint="Optional; this becomes the effective monthly net while the calculated value is retained." {...reg('manual_net_override')} />
      <div className="flex flex-col gap-1">
        <label className="text-sm font-medium text-secondary">Salary months *</label>
        <select
          {...reg('salary_months', { required: true })}
          className="border border-line-strong rounded px-3 py-2 text-sm bg-elevated text-primary"
        >
          <option value="12">12 (standard)</option>
          <option value="13">13 (tredicesima)</option>
          <option value="14">14 (tredicesima + quattordicesima)</option>
        </select>
      </div>
      <Button type="submit" isLoading={isPending}>Save</Button>
    </form>
  );

  return (
    <div className="max-w-3xl space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-bold text-primary">Salary Config</h1>
        <Button onClick={() => setAddOpen(true)}>+ Add period</Button>
      </div>

      {isLoading ? (
        <div className="animate-pulse h-32 bg-muted-bg rounded" />
      ) : (
        <div className="space-y-2">
          {configs.map((cfg) => (
            <div
              key={cfg.id}
              className={`bg-surface border border-line rounded-xl p-4 sm:p-5 ${selectedConfig?.id === cfg.id ? 'ring-2 ring-blue-500' : ''}`}
            >
              <div className="flex flex-col gap-3 sm:flex-row sm:justify-between sm:items-start">
                <div className="min-w-0">
                  <button type="button" aria-expanded={selectedConfig?.id === cfg.id} onClick={() => setSelectedId(selectedConfig?.id === cfg.id ? '' : cfg.id)} className="min-h-11 font-medium text-primary text-left rounded focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-600">From <span>{cfg.valid_from}</span> · {selectedConfig?.id === cfg.id ? 'Hide breakdown' : 'Show breakdown'}</button>
                  <p className="text-muted text-sm">RAL €{fmt(cfg.ral)}</p>
                </div>
                <div className="flex flex-wrap items-center justify-between gap-3 sm:justify-end">
                  <Button
                    variant="ghost"
                    className="text-xs"
                    onClick={(e) => {
                      e.stopPropagation();
                      resetEdit(configToFields(cfg));
                      setEditConfig(cfg);
                    }}
                  >
                    Edit
                  </Button>
                  <div className="sm:text-right">
                    <div className="text-lg font-bold text-blue-700 dark:text-blue-400">€{fmt(cfg.effective_net_monthly ?? cfg.manual_net_override ?? cfg.computed_net_monthly)}<span className="text-sm text-faint">/mo</span></div>
                    {cfg.manual_net_override != null && (
                      <div className="text-xs text-yellow-600">manual override (computed: €{fmt(cfg.computed_net_monthly)})</div>
                    )}
                  </div>
                </div>
              </div>
              {selectedConfig?.id === cfg.id && <BreakdownPanel config={cfg} />}
            </div>
          ))}
        </div>
      )}

      <Modal open={addOpen} onClose={() => setAddOpen(false)} title="Add salary period">
        {periodForm(register, handleSubmit, adding, (d) => addPeriod(d))}
      </Modal>

      <Modal open={!!editConfig} onClose={() => setEditConfig(null)} title="Edit salary period">
        {periodForm(regEdit, handleEditSubmit, updating, (d) => updatePeriod(d), true)}
      </Modal>
    </div>
  );
}
