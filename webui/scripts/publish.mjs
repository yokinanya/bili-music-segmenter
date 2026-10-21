// Copy the Next static export into the directory the Python WebUI serves.
import { cp, mkdir, rm } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const source = join(here, '..', 'out');
const target = join(here, '..', '..', 'segment', 'webui_dist');

await rm(target, { recursive: true, force: true });
await mkdir(target, { recursive: true });
await cp(source, target, { recursive: true });
console.log(`published ${source} -> ${target}`);
