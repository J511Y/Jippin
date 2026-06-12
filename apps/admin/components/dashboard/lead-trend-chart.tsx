'use client';

import { Area, AreaChart, CartesianGrid, XAxis, YAxis } from 'recharts';

import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig
} from '@/components/ui/chart';
import type { DailyLeadCount } from '@/lib/data/dashboard';

const chartConfig = {
  count: { label: '상담 신청', color: 'var(--foreground)' }
} satisfies ChartConfig;

export function LeadTrendChart({ data }: { data: DailyLeadCount[] }) {
  return (
    <ChartContainer config={chartConfig} className="h-64 w-full">
      <AreaChart data={data} margin={{ left: -24, right: 8, top: 8 }}>
        <CartesianGrid vertical={false} strokeDasharray="3 3" />
        <XAxis
          dataKey="day"
          tickLine={false}
          axisLine={false}
          tickMargin={8}
          minTickGap={32}
          tickFormatter={(value: string) => value.slice(5).replace('-', '/')}
        />
        <YAxis tickLine={false} axisLine={false} allowDecimals={false} width={48} />
        <ChartTooltip
          cursor={false}
          content={<ChartTooltipContent indicator="line" nameKey="count" />}
        />
        <Area
          dataKey="count"
          type="monotone"
          fill="var(--color-count)"
          fillOpacity={0.08}
          stroke="var(--color-count)"
          strokeWidth={1.5}
        />
      </AreaChart>
    </ChartContainer>
  );
}
