'use client';
import { useUsageData } from '@/lib/useUsageData';
import { Button } from './Material';
import { UsagePanel } from './UsagePanel';

export function UsagePage() {
  const { session, usageError, refresh } = useUsageData();
  return <div className="usage-page">
    {usageError && <div className="error" role="alert">用量读取失败：{usageError}<Button onClick={refresh}>重试</Button></div>}
    <div className="usage-toolbar"><Button variant="outlined" onClick={refresh}>刷新用量</Button></div>
    <UsagePanel session={session} />
  </div>;
}

