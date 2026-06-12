'use client';

import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from 'recharts';

import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig
} from '@/components/ui/chart';
import type { FunnelEntry } from '@/lib/data/dashboard';
import { SESSION_STATUS_LABELS } from '@/lib/labels';

const chartConfig = {
  count: { label: '세션', color: 'var(--foreground)' }
} satisfies ChartConfig;

export function SessionFunnelChart({ data }: { data: FunnelEntry[] }) {
  const rows = data.map((entry) => ({
    ...entry,
    label: SESSION_STATUS_LABELS[entry.status] ?? entry.status
  }));

  return (
    <ChartContainer config={chartConfig} className="h-64 w-full">
      <BarChart data={rows} layout="vertical" margin={{ left: 8, right: 16 }}>
        <CartesianGrid horizontal={false} strokeDasharray="3 3" />
        <XAxis type="number" tickLine={false} axisLine={false} allowDecimals={false} />
        <YAxis
          dataKey="label"
          type="category"
          tickLine={false}
          axisLine={false}
          width={88}
          tick={{ fontSize: 12 }}
        />
        <ChartTooltip cursor={false} content={<ChartTooltipContent nameKey="count" />} />
        <Bar dataKey="count" fill="var(--color-count)" radius={3} barSize={14} />
      </BarChart>
    </ChartContainer>
  );
}
