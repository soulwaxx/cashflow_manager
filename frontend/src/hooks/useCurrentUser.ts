import { useQuery } from '@tanstack/react-query';
import { fetchMeOrNull } from '../api/auth';
import { queryKeys } from '../api/queryKeys';
import type { User } from '../types/api';

export const AUTH_ME_QUERY_KEY = queryKeys.auth.me;
// Single canonical staleTime for the /auth/me query.
// Both AuthContext and AuthGuard must import from here to stay in sync.
const AUTH_ME_STALE_TIME = 30_000;

export function useCurrentUser() {
  return useQuery<User | null>({
    queryKey: AUTH_ME_QUERY_KEY,
    queryFn: fetchMeOrNull,
    retry: false,
    staleTime: AUTH_ME_STALE_TIME,
  });
}
