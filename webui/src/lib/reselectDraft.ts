import type { DraftFile } from './types';

export function reselectDraft(drafts: readonly DraftFile[], key: string, file: File): DraftFile {
  const draft = drafts.find((item) => item.key === key);
  if (!draft) throw new Error('待恢复的文件已被移除，请重新导入。');
  if (file.name !== draft.name || file.size !== draft.size) {
    throw new Error(`请选择原文件“${draft.name}”（${draft.size} 字节）；当前文件名称或大小不匹配。`);
  }
  return { ...draft, file, sent: 0, state: 'pending', error: undefined };
}
