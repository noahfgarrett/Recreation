import { Activity, Database, Shield } from 'lucide-react';
import type { JobStatus, ServiceInfo } from '../types';

interface StatusStripProps {
  service: ServiceInfo | null;
  job: JobStatus | null;
  message: string;
}

export function StatusStrip({ service, job, message }: StatusStripProps) {
  return (
    <footer className="status-strip">
      <span>
        <Activity size={13} />
        {message}
      </span>
      {job ? (
        <span>
          <Database size={13} />
          {job.status} {job.progress}%
        </span>
      ) : null}
      <span>
        <Shield size={13} />
        <span className={`status-accent${service ? ' status-connected' : ''}`}>
          {service ? 'Connected' : 'Offline'}
        </span>
        {service ? ` :${service.port}` : ' service pending'}
      </span>
    </footer>
  );
}
