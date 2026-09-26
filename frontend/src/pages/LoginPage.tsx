import { Link } from 'react-router-dom';
import LoginForm from '../components/auth/LoginForm';

export default function LoginPage() {
  return (
    <main className="min-h-dvh flex items-center justify-center bg-canvas px-4 py-8 sm:py-16">
      <div className="bg-surface rounded-2xl shadow-sm border border-line p-5 sm:p-8 w-full max-w-md">
        <p className="text-center text-sm font-semibold tracking-wide text-blue-800 dark:text-blue-300 mb-3">CashFlow Manager</p>
        <h1 className="text-2xl font-bold mb-2 text-center text-primary">Sign in</h1>
        <p className="text-sm text-muted text-center mb-6">Your finances, all in one place.</p>
        <LoginForm />
        <p className="mt-4 text-center text-sm text-muted">
          Don't have an account?{' '}
          <Link to="/register" className="text-blue-700 dark:text-blue-300 underline-offset-2 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-600">
            Register
          </Link>
        </p>
      </div>
    </main>
  );
}
