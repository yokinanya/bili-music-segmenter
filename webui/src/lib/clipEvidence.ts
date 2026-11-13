export function record(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown> : {};
}

const statuses: Record<string, string> = {
  matched: '已匹配', no_match: '未匹配', disabled: '未启用', error: '请求失败',
  unmatched: '未识别', unresolved: '未确认', single_provider: '单一来源识别',
  conflict: '识曲结果不一致，请手动填写',
  manual: '人工确认',
};

export interface EvidenceRow { readonly label: string; readonly text: string }

function text(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

function status(value: unknown): string {
  return statuses[text(value)] || text(value) || '未记录';
}

export function clipEvidence(recognition: unknown, resolution: unknown): EvidenceRow[] {
  const sources = record(recognition);
  const result = record(resolution);
  const rows: EvidenceRow[] = [{ label: '标题结论', text: status(result.status) }];
  for (const [key, label] of Object.entries({ shazam: 'Shazam', netease: '网易云' })) {
    const source = record(sources[key]);
    if (!Object.keys(source).length) continue;
    const song = [text(source.title), text(source.artist)].filter(Boolean).join(' · ');
    rows.push({ label, text: [status(source.status), song, text(source.error)].filter(Boolean).join(' · ') });
  }
  // 扫描时听到的主播报幕；没有明确报幕时留空，不参与判定。
  if (text(sources.announcer_hint)) rows.push({ label: '主播报幕', text: text(sources.announcer_hint) });
  const manual = record(result.manual);
  if (text(manual.reason)) rows.push({ label: '人工修订依据', text: text(manual.reason) });
  return rows;
}
