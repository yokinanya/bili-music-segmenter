#!/usr/bin/env node
// Browser measurement harness for the icon set. Each path is rendered at 20x the design
// size with the production stroke settings; the alpha bounds prove that every icon is
// optically centered inside the same drawable box. Uses a locally installed Chrome or
// Edge over the DevTools protocol, so no browser download is required.
import { writeFileSync, rmSync, existsSync, mkdtempSync } from "node:fs";
import { spawn } from "node:child_process";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { icons } from "../src/lib/iconGeometries.ts";

const SCALE = 20;
const TOLERANCE = 0.6;
const DRAWN = 20.5;
const TARGET_AXIS = 12;
const LOCAL_BROWSERS = [
  process.env.ICON_CHROME,
  join(process.env.LOCALAPPDATA ?? "", "Google/Chrome/Application/chrome.exe"),
  join(process.env.PROGRAMFILES ?? "", "Google/Chrome/Application/chrome.exe"),
  join(process.env["PROGRAMFILES(X86)"] ?? "", "Google/Chrome/Application/chrome.exe"),
  join(process.env.PROGRAMFILES ?? "", "Microsoft/Edge/Application/msedge.exe"),
  join(process.env["PROGRAMFILES(X86)"] ?? "", "Microsoft/Edge/Application/msedge.exe"),
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  "/usr/bin/google-chrome",
  "/usr/bin/chromium",
].filter(Boolean);

export const measureHtml = entries => `<!doctype html><meta charset="utf-8"><canvas id="c"></canvas><script>
const icons = ${JSON.stringify(entries)};
const ns = "http://www.w3.org/2000/svg";
const raster = (path, filled) => new Promise(resolve => {
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("width", 480); svg.setAttribute("height", 480); svg.setAttribute("viewBox", "0 0 24 24");
  const node = document.createElementNS(ns, "path");
  node.setAttribute("d", path); node.setAttribute("fill", filled ? "black" : "none");
  node.setAttribute("stroke", "black"); node.setAttribute("stroke-width", "1.5");
  node.setAttribute("stroke-linecap", "round"); node.setAttribute("stroke-linejoin", "round");
  svg.appendChild(node);
  const image = new Image();
  image.onload = () => {
    const canvas = document.getElementById("c"); canvas.width = 480; canvas.height = 480;
    const context = canvas.getContext("2d"); context.drawImage(image, 0, 0);
    const data = context.getImageData(0, 0, 480, 480).data;
    let left = 480, top = 480, right = -1, bottom = -1;
    for (let y = 0; y < 480; y++) for (let x = 0; x < 480; x++) if (data[(y * 480 + x) * 4 + 3] > 8) {
      left = Math.min(left, x); right = Math.max(right, x); top = Math.min(top, y); bottom = Math.max(bottom, y);
    }
    resolve([left / ${SCALE}, (right + 1) / ${SCALE}, top / ${SCALE}, (bottom + 1) / ${SCALE}]);
  };
  image.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(new XMLSerializer().serializeToString(svg));
});
window.__audit = async () => {
  const rows = [];
  for (const icon of icons) {
    const [left, right, top, bottom] = await raster(icon.path, icon.filled);
    rows.push({ name: icon.name, width: right - left, height: bottom - top, offsetX: (left + right) / 2 - ${TARGET_AXIS}, offsetY: (top + bottom) / 2 - ${TARGET_AXIS} });
  }
  return rows;
};
</script>`;

function waitFor(port, timeoutMs = 15000) {
  const deadline = Date.now() + timeoutMs;
  return new Promise((resolve, reject) => {
    const attempt = async () => {
      try {
        const response = await fetch(`http://127.0.0.1:${port}/json/version`);
        resolve(await response.json());
      } catch (error) {
        if (Date.now() > deadline) reject(new Error(`browser did not open its debugging port: ${error.message}`));
        else setTimeout(attempt, 150);
      }
    };
    attempt();
  });
}

function evaluate(port, expression) {
  return new Promise((resolve, reject) => {
    fetch(`http://127.0.0.1:${port}/json/list`).then(async response => {
      const targets = await response.json();
      const page = targets.find(target => target.type === "page");
      if (!page) throw new Error("no page target in the audit browser");
      const socket = new WebSocket(page.webSocketDebuggerUrl);
      socket.onopen = () => socket.send(JSON.stringify({ id: 1, method: "Runtime.evaluate", params: { expression, awaitPromise: true, returnByValue: true } }));
      socket.onerror = () => reject(new Error("devtools socket failed"));
      socket.onmessage = event => {
        const message = JSON.parse(event.data);
        if (message.id !== 1) return;
        socket.close();
        if (message.error) reject(new Error(message.error.message));
        else if (message.result?.exceptionDetails) reject(new Error(message.result.exceptionDetails.text));
        else resolve(message.result.result.value);
      };
    }).catch(reject);
  });
}

export async function measure(entries) {
  const browser = LOCAL_BROWSERS.find(candidate => existsSync(candidate));
  if (!browser) throw new Error(`no local Chrome or Edge found; set ICON_CHROME=${LOCAL_BROWSERS[1]}`);
  const port = 9300 + process.pid % 400;
  const profile = mkdtempSync(join(tmpdir(), "icon-audit-"));
  const file = join(tmpdir(), `icon-measure-${process.pid}.html`);
  writeFileSync(file, measureHtml(entries), "utf8");
  const child = spawn(browser, [`--headless=new`, "--disable-gpu", `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`, "about:blank"], { stdio: "ignore" });
  try {
    await waitFor(port);
    await fetch(`http://127.0.0.1:${port}/json/new?${encodeURIComponent(pathToFileURL(file).href)}`, { method: "PUT" });
    await new Promise(resolve => setTimeout(resolve, 300));
    return await evaluate(port, "(async () => { await new Promise(r => setTimeout(r, 200)); return window.__audit(); })()");
  } finally {
    const exited = new Promise(resolve => child.once("exit", resolve));
    child.kill();
    await exited;
    rmSync(file, { force: true });
    // Chrome releases its profile lock shortly after exit; cleanup is best effort.
    for (let attempt = 0; attempt < 20; attempt++) {
      try { rmSync(profile, { recursive: true, force: true }); break; } catch { await new Promise(resolve => setTimeout(resolve, 100)); }
    }
  }
}

export function failures(rows) {
  return rows
    .filter(row => Math.max(Math.abs(row.offsetX), Math.abs(row.offsetY)) > TOLERANCE || row.width > DRAWN || row.height > DRAWN)
    .map(row => `${row.name}: ${row.width.toFixed(2)}x${row.height.toFixed(2)} offset (${row.offsetX.toFixed(2)}, ${row.offsetY.toFixed(2)})`);
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  const rows = await measure(Object.entries(icons).map(([name, icon]) => ({ name, path: icon.path, filled: !!icon.filled })));
  console.table(rows.map(row => ({ name: row.name, size: `${row.width.toFixed(2)}x${row.height.toFixed(2)}`, x: row.offsetX.toFixed(2), y: row.offsetY.toFixed(2) })));
  const bad = failures(rows);
  console.log(bad.length ? bad.join("\n") : `all ${rows.length} icons centered within ${TOLERANCE}px`);
  if (bad.length) process.exitCode = 1;
}
