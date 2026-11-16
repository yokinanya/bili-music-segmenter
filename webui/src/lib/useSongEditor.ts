'use client';
import { useCallback, useEffect, useReducer, useRef, useState } from 'react';
import { api, transfer } from './api';
import { editorApi, type Waveform } from './editorApi';
import { editHistory, removeProject, splitClip, type EditorProject, type SongClip } from './editor';
import { errorText } from './format';
import { selectionAtTime } from './playheadSelection';
import { selectSongRange } from './rangeSelection';

export function useSongEditor() {
  const [projects, setProjects] = useState<EditorProject[]>([]), [project, setProject] = useState<EditorProject | null>(null);
  const [history, dispatch] = useReducer(editHistory, { past: [], present: [], future: [] });
  const [selected, setSelected] = useState<string[]>([]), [time, setTime] = useState(0);
  const [marks, setMarks] = useState<{ start: number | null; end: number | null }>({ start: null, end: null });
  const [waveform, setWaveform] = useState<Waveform | null>(null), [error, setError] = useState('');
  const [busy, setBusy] = useState(''), [notice, setNotice] = useState(''), [waveError, setWaveError] = useState('');
  const [importProgress, setImportProgress] = useState<{ name: string; index: number; count: number; sent: number; size: number; stage: 'registering' | 'uploading' | 'probing' } | null>(null);
  const openSequence = useRef(0);
  const preserveSelection = useRef(false);
  const selectionAnchor = useRef<string | null>(null);
  const updateTime = (value: number, explicit = false) => {
    if (explicit) preserveSelection.current = false;
    setTime(value);
    setSelected(current => {
      const next = selectionAtTime({ clips: history.present, selected: current, time: value,
        keepEndpoint: !explicit, preserveSelection: preserveSelection.current });
      return next.length === current.length && next.every((id, index) => id === current[index]) ? current : next;
    });
  };
  const run = async (label: string, work: () => Promise<void>) => {
    setBusy(label); setError('');
    try { await work(); } catch (cause) { setError(errorText(cause)); } finally { setBusy(''); }
  };
  const open = useCallback((value: EditorProject) => {
    const sequence = ++openSequence.current;
    preserveSelection.current = false;
    selectionAnchor.current = null;
    setProject(value); dispatch({ type: 'open', clips: value.clips }); setSelected([]); setTime(0); setWaveform(null); setWaveError('');
    setMarks({ start: null, end: null });
    localStorage.setItem('bms-editor-project', value.id);
    void editorApi.waveform(value.id).then(data => { if (sequence === openSequence.current) setWaveform(data); })
      .catch(cause => { if (sequence === openSequence.current) setWaveError(errorText(cause)); });
  }, []);
  useEffect(() => {
    void editorApi.list().then(data => {
      setProjects(data.projects);
      const retained = data.projects.find(value => value.id === localStorage.getItem('bms-editor-project'));
      // Fall back to the first import: an empty preview next to a populated asset list
      // reads as a loading failure rather than as "nothing open".
      const first = retained ?? data.projects[0];
      if (first) open(first);
    }).catch(cause => setError(errorText(cause)));
  }, [open]);
  const importFiles = (files: File[]) => run('正在导入录像…', async () => {
    try { for (const [index, file] of files.entries()) {
      const progress = { name: file.name, index: index + 1, count: files.length, sent: 0, size: file.size, stage: 'registering' as const };
      setImportProgress(progress);
      const source = await api.register(file);
      setImportProgress({ ...progress, stage: 'uploading' });
      await transfer(source, file, { signal: new AbortController().signal, update: bytes => {
        setBusy(`正在上传 ${file.name} · ${Math.round(bytes / file.size * 100)}%`);
        setImportProgress({ ...progress, stage: 'uploading', sent: bytes });
      } });
      setImportProgress({ ...progress, stage: 'probing', sent: file.size });
      setBusy('正在读取媒体信息…');
      const created = await editorApi.create(source.id);
      setProjects(values => [...values, created]); open(created);
    } } finally { setImportProgress(null); }
  });
  const save = async () => {
    if (!project) throw new Error('请先导入录像');
    const saved = await editorApi.save(project, history.present);
    setProject(saved); setProjects(values => values.map(value => value.id === saved.id ? saved : value)); setNotice('草稿已保存');
    return saved;
  };
  const switchProject = (value: EditorProject) => run('正在切换录像…', async () => {
    if (project && JSON.stringify(project.clips) !== JSON.stringify(history.present)) await save();
    open(value);
  });
  const remove = (value: EditorProject) => run('正在删除素材…', async () => {
    await editorApi.remove(value.id);
    const next = removeProject(projects, value.id, project?.id ?? null);
    setProjects(next.projects);
    if (next.openId === project?.id) return;
    if (next.openId) { const retained = next.projects.find(item => item.id === next.openId); if (retained) open(retained); }
    else { setProject(null); dispatch({ type: 'open', clips: [] }); setSelected([]); setWaveform(null); localStorage.removeItem('bms-editor-project'); }
    setNotice('素材已删除');
  });
  const change = (clips: SongClip[]) => dispatch({ type: 'replace', clips });
  const add = () => {
    if (!project || marks.start === null || marks.end === null || marks.start >= marks.end) return;
    const id = crypto.randomUUID();
    change([...history.present, { id, start_seconds: marks.start, end_seconds: marks.end, title: '', artist: '', name: `song-${history.present.length + 1}.mp4` }]);
    setSelected([id]); preserveSelection.current = true; setMarks({ start: null, end: null });
  };
  const splitTarget = history.present.find(c => selected.includes(c.id) && c.start_seconds < time && time < c.end_seconds);
  const split = () => {
    const clip = splitTarget;
    if (!clip) return;
    try { change(history.present.flatMap(c => c.id === clip.id ? splitClip(c, time, crypto.randomUUID()) : [c])); setError(''); }
    catch (cause) { setError(errorText(cause)); }
  };
  const select = (id: string, multi: boolean) => {
    preserveSelection.current = multi;
    selectionAnchor.current = id;
    setSelected(values => multi ? values.includes(id) ? values.filter(v => v !== id) : [...values, id] : [id]);
  };
  const selectRange = (id: string) => {
    preserveSelection.current = true;
    setSelected(current => selectSongRange({ ids: history.present.map(clip => clip.id),
      anchor: selectionAnchor.current ?? current[0] ?? null, target: id }));
    if (selectionAnchor.current === null) selectionAnchor.current = id;
  };
  const locateBoundary = (value: number) => { preserveSelection.current = true; setTime(value); };
  return { projects, project, history, dispatch, selected, setSelected, time, setTime: updateTime, seekTime: (value: number) => updateTime(value, true), locateBoundary, waveform, waveError, error, setError, busy, importProgress, notice, setNotice, run, open: switchProject, importFiles, remove, save, change, add, split, select, selectRange,
    marks, markIn: () => setMarks(value => ({ ...value, start: time })), markOut: () => setMarks(value => ({ ...value, end: time })),
    clearMarks: () => setMarks({ start: null, end: null }), canSplit: !!splitTarget };
}
