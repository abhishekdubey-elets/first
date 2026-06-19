import { Inbox } from 'lucide-react';
import { ReactNode } from 'react';

export function EmptyState({
  title = 'No data yet',
  message = 'The agents are still discovering — check back soon.',
  icon,
}: {
  title?: string;
  message?: string;
  icon?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 px-6 py-14 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-white/5 text-slate-400">
        {icon ?? <Inbox className="h-6 w-6" />}
      </div>
      <div>
        <p className="font-medium text-slate-200">{title}</p>
        <p className="mt-1 max-w-sm text-sm text-slate-400">{message}</p>
      </div>
    </div>
  );
}
