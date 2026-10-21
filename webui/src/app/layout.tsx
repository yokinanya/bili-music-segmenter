import type { Metadata, Viewport } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: '自动歌切 · Bili Music Segmenter',
  description: '从直播录像中提取演唱片段',
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  colorScheme: 'light dark',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <head>
        {/* Apply the stored theme before paint so the first frame never flashes the wrong colors. */}
        <script
          dangerouslySetInnerHTML={{
            __html:
              "(function(){try{var t=localStorage.getItem('bms-theme');var m=window.matchMedia('(prefers-color-scheme: dark)').matches;if(t==='dark'||(!t||t==='system')&&m){document.documentElement.dataset.theme='dark';}}catch(e){}})();",
          }}
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
