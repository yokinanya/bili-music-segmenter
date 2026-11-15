import assert from 'node:assert/strict';
import test from 'node:test';
import { matchesExport } from '../src/lib/exportSnapshot.ts';

const clip = {id:'a',name:'歌.mp4',start_seconds:1,end_seconds:20};
test('export is reusable after saving identical content but not after editing boundaries or names', () => {
  const task = {revision:1,clips:[{...clip,path:'saved.mp4'}]};
  assert.equal(matchesExport(task,[clip]),true);
  assert.equal(matchesExport(task,[{...clip,end_seconds:21}]),false);
  assert.equal(matchesExport(task,[{...clip,name:'new.mp4'}]),false);
  assert.equal(matchesExport(task,[]),false);
});

test('matching includes the suffix and keeps legacy exports reusable without suffix', () => {
  const task = {filename_suffix:'-小葵',clips:[{...clip,name:'歌-小葵.mp4'}]};
  assert.equal(matchesExport(task,[clip],'-小葵'),true);
  assert.equal(matchesExport(task,[clip],''),false);
});
