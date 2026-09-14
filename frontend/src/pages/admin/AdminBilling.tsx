import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  Activity,
  ArrowRight,
  Building2,
  CircleDollarSign,
  Cpu,
  Gift,
  Layers,
  Percent,
  PieChart,
  ShoppingCart,
  Users,
  Wallet,
} from 'lucide-react';
import { billingApi } from '../../api/billingApi';
import { CategoryUsageBars } from '../../components/billing/CategoryUsageBars';
import { PeriodPicker } from '../../components/billing/PeriodPicker';
import type { PeriodDays } from '../../components/billing/PeriodPicker';
import { useBillingQuery } from '../../hooks/useBillingQuery';
import { formatCreditAmount, formatCredits, formatDayLabel, formatPercent, formatUsd } from '../../utils/billingFormat';
import { AdminPage, Card, ErrorBlock, LoadingBlock, RefreshButton, Segmented, StatCard } from './components/AdminUi';
import type { Tone } from './components/AdminUi';
import { StackedBarChart } from './components/Charts';
import { formatNumber } from './adminFormat';
import { useDirectory } from './useDirectory';
import { revenueText } from './billing/billingMeta';
import { TopWorkspaces } from './billing/TopWorkspaces';
import { ModelTable, OperationTable } from './billing/UsageTables';

type Measure = 'credits' | 'cost';

function marginTone(percent: number | null | undefined): Tone {
  if (percent === null || percent === undefined) return 'neutral';
  if (percent < 0) return 'danger';
  return percent < 50 ? 'warning' : 'success';
}

/** Billing across the platform: revenue, credits sold, granted and used, what usage cost and who used it. */
export const AdminBilling: React.FC = () => {
  const navigate = useNavigate();
  const [days, setDays] = useState<PeriodDays>(30);
  const [measure, setMeasure] = useState<Measure>('credits');
  const overview = useBillingQuery(() => billingApi.admin.overview(days), `overview:${days}`, 'admin');
  const usage = useBillingQuery(() => billingApi.admin.usage(days), `usage:${days}`, 'admin');
  const directory = useDirectory();

  const data = overview.data;
  const statsLoading = !data && !overview.error;
  const denied = overview.errorStatus === 403;
  const refresh = () => {
    overview.reload();
    usage.reload();
  };

  const bars = (data?.dailyUsage ?? []).map((day) => ({
    label: formatDayLabel(day.date),
    values: [measure === 'credits' ? day.credits : day.costUsd],
  }));
  const margin = data?.grossMarginPercent ?? null;
  // While the overview loads, or when it failed (the error above says why and offers a retry).
  const overviewPlaceholder = (className: string) =>
    overview.error ? (
      <p className={`text-xs text-muted-foreground text-center ${className}`}>Unavailable</p>
    ) : (
      <LoadingBlock className={className} />
    );

  return (
    <AdminPage
      title="Billing"
      icon={Wallet}
      description="Money in, credits out and what usage costs the platform. Revenue counts payments that succeeded; gross margin compares USD revenue with provider cost over the same period."
      actions={
        <>
          <PeriodPicker value={days} onChange={setDays} />
          <RefreshButton onClick={refresh} loading={overview.loading || usage.loading} label="Refresh billing" />
        </>
      }
    >
      {overview.error && !data && <ErrorBlock message={overview.error} onRetry={denied ? undefined : overview.reload} />}

      {!denied && (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <StatCard
              label="Revenue"
              icon={CircleDollarSign}
              tone="success"
              loading={statsLoading}
              value={revenueText(data)}
              hint={data ? `${formatNumber(data.successfulPayments)} payments` : undefined}
            />
            <StatCard
              label="Provider cost"
              icon={Cpu}
              tone="warning"
              loading={statsLoading}
              value={formatUsd(data?.providerCostUsd)}
              hint="What usage cost us"
            />
            <StatCard
              label="Gross margin"
              icon={Percent}
              tone={marginTone(margin)}
              loading={statsLoading}
              value={margin === null ? '—' : formatPercent(margin)}
              hint={data ? (margin === null ? 'No USD revenue' : 'After provider cost') : undefined}
            />
            <StatCard
              label="Unspent credits"
              icon={Wallet}
              tone="info"
              loading={statsLoading}
              value={formatCredits(data?.outstandingCredits)}
              hint="In all balances now"
            />
            <StatCard label="Credits sold" icon={ShoppingCart} loading={statsLoading} value={formatCredits(data?.creditsSold)} hint="Paid packs" />
            <StatCard
              label="Credits granted"
              icon={Gift}
              tone="violet"
              loading={statsLoading}
              value={formatCredits(data?.creditsGranted)}
              hint="Welcome + admin"
            />
            <StatCard
              label="Credits used"
              icon={Activity}
              loading={statsLoading}
              value={formatCreditAmount(data?.creditsUsed)}
              hint="Metered usage"
            />
            <StatCard
              label="Accounts"
              icon={Users}
              tone="neutral"
              loading={statsLoading}
              value={formatNumber(data?.accounts)}
              hint={
                data ? (
                  <span title={`${formatNumber(data.suspendedAccounts)} suspended, ${formatNumber(data.negativeBalanceAccounts)} below zero`}>
                    {formatNumber(data.suspendedAccounts)} suspended · {formatNumber(data.negativeBalanceAccounts)} negative
                  </span>
                ) : undefined
              }
            />
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
            <Card
              className="xl:col-span-2"
              title="Daily usage"
              subtitle={`${measure === 'credits' ? 'Credits used' : 'Provider cost'} per day, last ${days} days (UTC)`}
              icon={Activity}
              actions={
                <Segmented<Measure>
                  label="Daily usage measure"
                  size="sm"
                  value={measure}
                  onChange={setMeasure}
                  options={[
                    { value: 'credits', label: 'Credits' },
                    { value: 'cost', label: 'Cost' },
                  ]}
                />
              }
            >
              {!data ? (
                overviewPlaceholder('py-20')
              ) : (
                <StackedBarChart
                  data={bars}
                  series={[
                    measure === 'credits'
                      ? { name: 'Credits used', className: 'bg-primary/80' }
                      : { name: 'Provider cost', className: 'bg-amber-500/80' },
                  ]}
                  height={200}
                  formatValue={measure === 'credits' ? formatCreditAmount : formatUsd}
                  emptyLabel="No usage in this period"
                />
              )}
            </Card>

            <Card title="Usage by category" subtitle="Share of the credits used, with provider cost" icon={PieChart}>
              {!data ? (
                overviewPlaceholder('py-16')
              ) : data.usageByCategory.every((row) => row.credits <= 0) ? (
                <p className="text-xs text-muted-foreground py-10 text-center">No usage in this period.</p>
              ) : (
                <CategoryUsageBars categories={data.usageByCategory} showCost />
              )}
            </Card>
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
            <Card
              title="Top workspaces"
              subtitle="Most credits used in the period"
              icon={Building2}
              actions={
                <Link to="/admin/credits" className="text-[11px] font-semibold text-primary hover:underline flex items-center gap-1">
                  All accounts <ArrowRight className="w-3 h-3" />
                </Link>
              }
            >
              {!data ? (
                overviewPlaceholder('py-16')
              ) : (
                <TopWorkspaces
                  rows={data.topWorkspaces}
                  directory={directory}
                  onOpen={(workspaceId) => navigate('/admin/credits', { state: { open: workspaceId } })}
                />
              )}
            </Card>

            <Card className="xl:col-span-2" title="By operation" subtitle="What was charged, and what it cost us" icon={Layers} bodyClassName="p-0">
              {usage.error && !usage.data ? (
                <div className="p-5">
                  <ErrorBlock message={usage.error} onRetry={usage.errorStatus === 403 ? undefined : usage.reload} compact />
                </div>
              ) : !usage.data ? (
                <LoadingBlock className="py-16" />
              ) : (
                <OperationTable rows={usage.data.byOperation} />
              )}
            </Card>
          </div>

          <Card title="By model" subtitle="Metered model calls and the tokens behind them" icon={Cpu} bodyClassName="p-0">
            {usage.error && !usage.data ? (
              <div className="p-5">
                <ErrorBlock message={usage.error} onRetry={usage.errorStatus === 403 ? undefined : usage.reload} compact />
              </div>
            ) : !usage.data ? (
              <LoadingBlock className="py-16" />
            ) : (
              <ModelTable rows={usage.data.byModel} />
            )}
          </Card>
        </>
      )}
    </AdminPage>
  );
};

export default AdminBilling;
