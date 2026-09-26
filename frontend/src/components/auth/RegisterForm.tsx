import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { authApi } from '../../api/auth';
import { AUTH_ME_QUERY_KEY } from '../../hooks/useCurrentUser';
import { Input } from '../ui/Input';
import { Button } from '../ui/Button';

interface Fields { email: string; name: string; password: string; }

export default function RegisterForm() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const { register, handleSubmit, formState: { isSubmitting } } = useForm<Fields>();

  const onSubmit = async (data: Fields) => {
    setError(null);
    try {
      const user = await authApi.register(data.email, data.name, data.password);
      queryClient.setQueryData(AUTH_ME_QUERY_KEY, user);
      navigate('/');
    } catch {
      setError('Registration failed. Email may already be in use.');
    }
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4">
      <Input label="Email" type="email" autoComplete="email" {...register('email', { required: true })} />
      <Input label="Name" type="text" autoComplete="name" {...register('name', { required: true })} />
      <Input label="Password" type="password" autoComplete="new-password" {...register('password', { required: true, minLength: 8 })} />
      {error && (
        <div role="alert" className="text-sm text-red-700 dark:text-red-300 bg-red-50 dark:bg-red-900/20 rounded-lg p-3">
          {error}
        </div>
      )}
      <Button type="submit" isLoading={isSubmitting}>Create account</Button>
    </form>
  );
}
