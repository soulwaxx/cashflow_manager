import { useState } from 'react';
import ForecastList from '../components/forecasting/ForecastList';
import CreateForecastForm from '../components/forecasting/CreateForecastForm';
import Modal from '../components/ui/Modal';
import { Button } from '../components/ui/Button';

export default function ForecastingPage() {
  const [createOpen, setCreateOpen] = useState(false);

  return (
    <div className="max-w-3xl space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-primary">Spending commitment forecasts</h1>
        <Button onClick={() => setCreateOpen(true)}>+ New forecast</Button>
      </div>
      <ForecastList />
      <Modal open={createOpen} onClose={() => setCreateOpen(false)} title="Create forecast">
        <CreateForecastForm onSuccess={() => setCreateOpen(false)} />
      </Modal>
    </div>
  );
}
