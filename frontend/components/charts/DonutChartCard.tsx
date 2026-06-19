'use client';

import {
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
} from 'recharts';
import { CHART_COLORS } from '@/lib/utils';
import { tooltipStyle } from './tooltip';

interface DonutChartViewProps {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  data: any[];
  nameKey: string;
  valueKey: string;
  height?: number;
}

export function DonutChartView({
  data,
  nameKey,
  valueKey,
  height = 280,
}: DonutChartViewProps) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <PieChart>
        <Pie
          data={data}
          dataKey={valueKey}
          nameKey={nameKey}
          innerRadius={60}
          outerRadius={95}
          paddingAngle={3}
          stroke="none"
        >
          {data.map((_, i) => (
            <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
          ))}
        </Pie>
        <Tooltip contentStyle={tooltipStyle} />
        <Legend
          verticalAlign="bottom"
          iconType="circle"
          wrapperStyle={{ fontSize: 12, color: '#94a3b8' }}
        />
      </PieChart>
    </ResponsiveContainer>
  );
}
