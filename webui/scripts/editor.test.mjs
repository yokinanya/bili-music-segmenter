import test from 'node:test';
import assert from 'node:assert/strict';
import { splitClip, mergeClips, timeAt, editHistory, removeProject, updateSongTitle } from '../src/lib/editor.ts';
import { timelineTickAlignment, timelineTickTranslation } from '../src/lib/timelineLayout.ts';
const project = (id) => ({ id, source_name: `${id}.mkv`, duration: 60, revision: 1, clips: [], analysis: null, upload_id: id, created_at: '2026-01-01T00:00:00+08:00', updated_at: '2026-01-01T00:00:00+08:00' });

const clip = { id: 'one', start_seconds: 10, end_seconds: 50, title: 'Song', artist: '', name: 'Song.mp4' };
test('split preserves source positions and refuses endpoints', () => {
  const parts = splitClip(clip, 25, 'two');
  assert.deepEqual(parts.map(c => [c.id, c.start_seconds, c.end_seconds]), [['one', 10, 25], ['two', 25, 50]]);
  assert.throws(() => splitClip(clip, 10, 'two'));
  assert.equal(clip.end_seconds, 50);
});
test('merge includes the gap without moving the source content', () => {
  const merged = mergeClips([clip, { ...clip, id: 'two', start_seconds: 70, end_seconds: 90 }]);
  assert.equal(merged.start_seconds, 10);
  assert.equal(merged.end_seconds, 90);
});
test('renaming a song updates its safe export filename', () => {
  assert.deepEqual(updateSongTitle(clip, '稻香 / Live'), { ...clip, title: '稻香 / Live', name: '稻香 Live.mp4' });
  assert.deepEqual(updateSongTitle(clip, '  '), { ...clip, title: '  ', name: 'song.mp4' });
  assert.equal(updateSongTitle(clip, 'CON').name, '_CON.mp4');
});
test('ruler endpoints align inside the timeline instead of overflowing', () => {
  assert.equal(timelineTickAlignment(0, 11), 'start');
  assert.equal(timelineTickAlignment(5, 11), 'center');
  assert.equal(timelineTickAlignment(10, 11), 'end');
  assert.equal(timelineTickTranslation(10, 11), '-100%');
});
test('timeline maps scrolled coordinates and history restores edits', () => {
  assert.equal(timeAt({ x: 200, left: 100, scroll: 300, pixelsPerSecond: 20, duration: 60 }), 20);
  const initial = { past: [], present: [clip], future: [] };
  const edited = editHistory(initial, { type: 'replace', clips: splitClip(clip, 25, 'two') });
  const undone = editHistory(edited, { type: 'undo' });
  assert.deepEqual(undone.present, [clip]);
  assert.deepEqual(editHistory(undone, { type: 'redo' }).present, edited.present);
  assert.deepEqual(editHistory(edited, { type: 'open', clips: [] }), { past: [], present: [], future: [] });
});

test('removing a project drops it from the list and clears the open draft', () => {
  const projects = [project('a'), project('b')];
  const next = removeProject(projects, 'a', 'a');
  assert.deepEqual(next.projects.map((value) => value.id), ['b']);
  assert.equal(next.openId, 'b');
});

test('removing a project that is not open keeps the current draft', () => {
  const next = removeProject([project('a'), project('b')], 'b', 'a');
  assert.deepEqual(next.projects.map((value) => value.id), ['a']);
  assert.equal(next.openId, 'a');
});

test('removing the last project leaves no open draft', () => {
  const next = removeProject([project('a')], 'a', 'a');
  assert.deepEqual(next.projects, []);
  assert.equal(next.openId, null);
});
