'use client';
import { useEffect, useState } from 'react';
import { api, downloadUrl } from '@/lib/api';
import { errorText } from '@/lib/format';
import { ActionLink, Button, MaterialDialog } from './Material';
export function ManifestView({ jobId, mediaId, onClose }: { jobId: string; mediaId: string; onClose: () => void }) {
  const [content, setContent] = useState(''), [error, setError] = useState('');
  useEffect(() => {
    let alive = true;
    void api.manifest(jobId, mediaId).then((value) => { if (alive) setContent(JSON.stringify(value, null, 2)); })
      .catch((cause) => { if (alive) setError(errorText(cause)); });
    return () => { alive = false; };
  }, [jobId, mediaId]);
  return <MaterialDialog open title="分析 JSON" onClose={onClose}>
    {error ? <div className="error" role="alert">{error}</div> : <pre className="manifest-json" tabIndex={0}>{content || '正在读取…'}</pre>}
    <div className="dialog-actions"><ActionLink href={downloadUrl(jobId, `manifest/${mediaId}`, true)} download>下载 JSON</ActionLink><Button onClick={onClose}>关闭</Button></div>
  </MaterialDialog>;
}
