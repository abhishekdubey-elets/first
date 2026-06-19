'use client';

import { useQuery } from '@tanstack/react-query';
import { getMe } from './api';

export function useAuth() {
  return useQuery({
    queryKey: ['me'],
    queryFn: getMe,
    retry: false,
    staleTime: 5 * 60_000,
  });
}
