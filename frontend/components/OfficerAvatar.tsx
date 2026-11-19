'use client';

import { useState } from 'react';
import { cn } from '@/lib/utils';

/** "A. Katherine Saranya" -> "AK" (first letters of the first two words). */
export function initials(name: string): string {
  const words = name.replace(/[.,]/g, ' ').split(/\s+/).filter(Boolean);
  return words.slice(0, 2).map((w) => w[0]?.toUpperCase() ?? '').join('') || '?';
}

const sizes = {
  sm: 'h-9 w-9 rounded-lg text-xs',
  lg: 'h-24 w-24 rounded-2xl text-3xl',
};

/**
 * The officer's photo when the research agent found one, else initials.
 * Photos are hot-linked from where they were published, so a broken or
 * blocked image falls back to the initials.
 */
export function OfficerAvatar({
  name,
  photoUrl,
  size = 'sm',
}: {
  name: string;
  photoUrl?: string | null;
  size?: keyof typeof sizes;
}) {
  const [failed, setFailed] = useState(false);
  const box = cn(
    'flex shrink-0 items-center justify-center overflow-hidden border border-white/10',
    sizes[size],
  );
  if (photoUrl && !failed) {
    return (
      <div className={box}>
        {/* eslint-disable-next-line @next/next/no-img-element -- remote hosts vary per officer */}
        <img
          src={photoUrl}
          alt={name}
          referrerPolicy="no-referrer"
          className="h-full w-full object-cover object-top"
          onError={() => setFailed(true)}
        />
      </div>
    );
  }
  return (
    <div
      className={cn(box, 'bg-brand-indigo/15 font-semibold text-brand-cyan')}
      aria-label={name}
    >
      {initials(name)}
    </div>
  );
}
