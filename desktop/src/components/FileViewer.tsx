import { useState, useEffect, useRef } from 'react';
import { X, File as FileIcon, Copy, Check } from 'lucide-react';
import type { WorkspaceFile } from '../api/workspaces';

interface FileViewerProps {
  file: WorkspaceFile;
  onClose: () => void;
}

const truncate = (line: string) => (line.length > 400 ? `${line.slice(0, 400)}…` : line);

export function FileViewer({ file, onClose }: FileViewerProps) {
  const [copied, setCopied] = useState(false);
  const lines = file.content.split('\n');
  const gutter = String(lines.length).length;
  const scrollRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onClose]);
  return (
    <section className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-bifang-panel" aria-label={`File preview: ${file.path}`}>
      <header className="flex shrink-0 items-center gap-2 border-b border-bifang-border px-3 py-2">
        <FileIcon className="w-4 h-4 text-bifang-text-muted" />
        <h4 className="truncate font-medium text-body-sm text-bifang-text-primary" title={file.path}>{file.path}</h4>
        <button
          className="rounded p-1 transition-colors hover:bg-bifang-surface"
          title="Copy contents"
          aria-label="Copy contents"
          onClick={() => {
            navigator.clipboard?.writeText(file.content);
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
          }}
        >
          {copied ? <Check className="w-4 h-4 text-bifang-success" /> : <Copy className="w-4 h-4 text-bifang-text-secondary" />}
        </button>
        <button
          className="rounded p-1 transition-colors hover:bg-bifang-surface"
          title="Close preview"
          aria-label="Close file preview"
          onClick={onClose}
        >
          <X className="w-4 h-4 text-bifang-text-secondary" />
        </button>
      </header>
      <div ref={scrollRef} className="min-h-0 flex-1 overflow-auto scrollbar-thin">
        <div className="flex min-w-max font-mono text-[12px] leading-5">
          <span className="border-r border-bifang-border bg-bifang-surface px-2 py-2 text-right text-bifang-text-muted select-none">
            {lines.map((_, i) => <div key={i}>{i + 1}</div>)}
          </span>
          <code className="px-3 py-2 text-bifang-text-primary">
            {lines.map((line, i) => <div key={i} className="whitespace-pre">{truncate(line) || ' '}</div>)}
          </code>
        </div>
      </div>
    </section>
  );
}
