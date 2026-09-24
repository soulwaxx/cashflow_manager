import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useQueryClient } from '@tanstack/react-query';
import { authApi, fetchAuthConfigOrLegacy } from '../../api/auth';
import { queryKeys } from '../../api/queryKeys';
import { Input } from '../ui/Input';
import { Button } from '../ui/Button';

interface Fields { email: string; password: string; }

export default function LoginForm() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const { register, handleSubmit, formState: { isSubmitting } } = useForm<Fields>();
  const { data: authConfig } = useQuery({
    queryKey: queryKeys.auth.config,
    queryFn: fetchAuthConfigOrLegacy,
    retry: false,
    staleTime: 30_000,
  });

  const basicAuthEnabled = authConfig?.basic_auth_enabled ?? true;
  const oidcEnabled = authConfig?.oidc_enabled ?? false;

  const onSubmit = async (data: Fields) => {
    if (!basicAuthEnabled) return;
    setError(null);
    try {
      const user = await authApi.login(data.email, data.password);
      queryClient.setQueryData(queryKeys.auth.me, user);
      navigate('/');
    } catch {
      setError('Invalid email or password.');
    }
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4">
      {basicAuthEnabled ? (
        <>
          <Input label="Email" type="email" autoComplete="email" {...register('email', { required: true })} />
          <Input label="Password" type="password" autoComplete="current-password" {...register('password', { required: true })} />
          {error && (
            <div role="alert" className="text-sm text-red-600 bg-red-50 rounded p-2">
              {error}
            </div>
          )}
          <Button type="submit" isLoading={isSubmitting}>Sign in</Button>
        </>
      ) : (
        <div className="text-sm text-muted text-center">
          Email and password sign-in is disabled for this instance.
        </div>
      )}
      {oidcEnabled && (
        <div className="text-center">
          <a href={authApi.oidcLoginUrl()} className="text-sm text-blue-600 hover:underline">
            Sign in with SSO
          </a>
        </div>
      )}
    </form>
  );
}
