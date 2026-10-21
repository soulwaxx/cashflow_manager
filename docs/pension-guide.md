# Pension setup and reconciliation

This guide describes the pension estimates and reconciliation controls in the current candidate. Pension projections are estimates, not proof that a pension provider received a contribution. The candidate is still undergoing integrated validation; this is not a deployment or release notice.

## Configure contributions

Pension settings are separate from salary settings. Configure:

- an employee contribution rate and its annual base;
- an employer contribution rate and its annual base;
- an explicit annual TFR contribution amount; and
- the pension account that receives the projected credits.

The bases are independent amounts. They do not follow RAL automatically. RAL remains gross employee salary and excludes employer-funded pension and TFR. A copied base is a one-time value, not a link. No pension configuration means no projected pension contribution. TFR is never inferred from salary; enter zero if it does not apply.

The shared contribution calendar controls when employee, employer, and TFR credits are projected. Monthly weights credit each month; quarterly weights can credit March, June, September, and December. Calendar weights are independent of whether salary is paid 12, 13, or 14 times per year. A mid-year configuration starts in its effective month and does not recalculate earlier months. Changing a calendar mid-year can change the annual projection.

## Understand salary and tax estimates

The salary calculation reports annualized pension components separately. For the ordinary payroll estimate, eligible employee and employer contributions share the effective tax configuration's annual cap. Employer contributions are included in the taxable-base calculation before any eligible relief; amounts above the cap can increase the taxable base. Employee contributions affect estimated cash net. Employer contributions and TFR are not direct cash deductions, and TFR is excluded from the cap calculation.

This is not a tax-return calculator and does not automatically model external personal payments, multiple employers, special first-employment relief, qualifying performance-bonus conversion, or other exceptional schemes. The cap display covers configured payroll contributions only. Use the manual net value to compare with actual payroll and seek payroll advice for cases outside that scope. Net divided by salary-payment count is an average, not an exact payslip prediction.

## Read pension balances

A pension opening balance is the amount at the **start** of its selected month. Earlier history is already included in that amount; projected credits and transfers begin in that month. A report before the opening month omits the account rather than inventing a zero balance.

A reconciliation snapshot is an authoritative balance at the **end** of its selected month. It includes that month's credits and transfers once. Later months project scheduled credits and net transfers from that snapshot. For example, a statement reconciled through March can be shown as a statement-reconciled balance through March and a projection through April; it is not an actual April statement balance.

Pension history carries across calendar years. A later snapshot replaces the earlier baseline for reports on or after its month. Removing it returns the calculation to the previous eligible snapshot or the opening balance. Use the source and notes fields to record whether a balance came from a statement or manual reconciliation and to explain returns, fees, or other differences.

## Transfers and bank records

Configured payroll credits are projected pension flows; they are not ledger entries. A pension transfer is an **additional** movement, such as a separate payment or a move between funds. Do not also record a configured payroll contribution as a transfer, or it will be counted twice. The app does not guess duplicates from dates, amounts, or notes. If older transfers already duplicate projected contributions, reconcile the account to a dated balance; do not change transfer records merely to force a match.

Projected pension credits do not create salary transactions or change transaction-based bank balances, monthly summaries, or transfer analytics. Record actual bank activity separately using the ordinary transaction and transfer features.

## Existing pension history and backups

The migration copies each legacy salary period's RAL into the independent employee and employer contribution bases, preserves its contribution rates, and sets TFR to zero. This preserves the configured contribution amounts, but corrected payroll calculations apply immediately and can change computed net salary. Manual net overrides remain unchanged; cumulative pension balances also include prior years and owned transfers rather than preserving the former annual-only estimate.

During the schema conversion, an old annual pension override has no stored statement date. It is preserved as a legacy reconciliation at **December of that year**, explicitly as an assumed month-end date, not as a claim about when the provider issued a statement. As a result, that value is not applied retroactively to every month in the year. Review historical balances and add a correctly dated statement snapshot when its actual month is known.

Take a consistent database backup before an upgrade that changes pension storage. The new effective contribution bases and dated snapshots cannot generally be converted back into the former salary-rate and annual-override representation. Rollback therefore means restoring the pre-upgrade backup, not downgrading the schema. Restoring that backup also removes every change made after it was taken. Verify the backup and keep it separate until the upgraded application and data have been checked.

For production SQLite backup and restore commands, see [Backup and restore](deployment.md#backup-and-restore). For the data model and service boundaries, see [Architecture](architecture.md#backend-backendapp).
