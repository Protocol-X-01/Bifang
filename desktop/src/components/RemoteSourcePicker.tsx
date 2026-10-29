import { useRef, useState } from 'react';
import { importCodingFiles, selectedCodingFiles } from '../api/remoteCoding';
import { Loader2, AlertTriangle, FileText, Plus, Trash2, Code2, Shield, Eye } from 'lucide-react';

interface Props {
  value: string;
  writable: string;
  disabled: boolean;
  onChange: (value: string) => void;
  onWritable: (value: string) => void;
  onReading: (value: boolean) => void;
}

export function RemoteSourcePicker({ value, writable, disabled, onChange, onWritable, onReading }: Props) {
  const picker = useRef<HTMLInputElement>(null);
  const [error, setError] = useState('');
  const [reading, setReading] = useState(false);
  let files: Record<string, string> = {};
  try { files = value === '{}' ? {} : selectedCodingFiles(value); } catch { }
  const paths = Object.keys(files);
  const outputs = writable.split('\n').filter(Boolean);
  const locked = disabled || reading;
  const inputClass = 'w-full rounded-lg border-bifang-border bg-bifang-panel px-3 py-2 text-sm focus:ring-2 focus:ring-bifang-brand-orange focus:ring-offset-2 focus:ring-offset-bifang-focus-offset';

  function update(entries: [string, string][]) {
    onChange(JSON.stringify(Object.fromEntries(entries), null, 2));
  }

  async function importFiles(selected: File[]) {
    if (locked) return;
    setReading(true);
    onReading(true);
    setError('');
    try { onChange(JSON.stringify(await importCodingFiles(selected, files), null, 2)); }
    catch (failure) { setError(failure instanceof Error ? failure.message : 'Source selection failed.'); }
    finally { setReading(false); onReading(false); if (picker.current) picker.current.value = ''; }
  }

  return (
    <fieldset className="space-y-3 rounded-xl border-bifang-border bg-bifang-panel p-4 animate-in panel-hover" disabled={locked}>
      <legend className="px-2 text-h5 text-bifang-text-primary">Selected source · {paths.length}/8 files</legend>
      <p className="text-caption text-bifang-text-muted">Choose individual UTF-8 files. They stay on this device until you confirm sharing and request a proposal. Imported files start read-only; enable only the paths the agent may change.</p>
      <div className="flex flex-wrap gap-2">
        <button type="button" className="btn-secondary" onClick={() => picker.current?.click()} disabled={locked || paths.length >= 8}>{reading ? <><Loader2 className="w-4 h-4 animate-spin mr-1.5" /> Reading source…</> : <><Plus className="w-4 h-4 mr-1.5" /> Choose source files</>}</button>
        <button type="button" className="btn-secondary" disabled={locked || paths.length >= 8} onClick={() => {
          let path = 'source.py';
          for (let index = 1; Object.prototype.hasOwnProperty.call(files, path); index++) path = `source-${index}.py`;
          update([...Object.entries(files), [path, '']]);
        }}><FileText className="w-4 h-4 mr-1.5" /> Add a source snippet</button>
        <input ref={picker} type="file" multiple className="sr-only" tabIndex={-1} aria-label="Import selected source files" disabled={locked} onChange={event => { if (event.target.files?.length) void importFiles(Array.from(event.target.files)); }} />
      </div>
      {error && <p role="alert" className="text-caption text-bifang-brand-red animate-in">{error}</p>}
      {paths.length === 0 && <p className="rounded-lg border-2 border-dashed border-bifang-border p-5 text-center text-caption text-bifang-text-muted">A focused task starts with a few carefully selected files.</p>}
      {Object.entries(files).map(([path, content]) => (
        <details key={path} className="rounded-lg border-bifang-border bg-bifang-surface p-3 animate-in">
          <summary className="cursor-pointer flex items-center justify-between text-body-sm">
            <span className="font-mono text-code text-bifang-brand-orange/90">{path}</span>
            <span className="text-caption text-bifang-text-muted ml-3">{new TextEncoder().encode(content).length.toLocaleString()} bytes · {outputs.includes(path) ? 'writable' : 'read-only'}</span>
          </summary>
          <div className="mt-3 space-y-3">
            <label className="block text-caption text-bifang-text-muted">Relative source path
              <input className={`${inputClass} font-mono`} defaultValue={path} disabled={locked} onBlur={event => {
                const target = event.target.value;
                if (target === path) return;
                try {
                  if (Object.prototype.hasOwnProperty.call(files, target)) throw new Error('That path is already selected.');
                  const entries = Object.entries(files).map(([name, body]): [string, string] => [name === path ? target : name, body]);
                  selectedCodingFiles(JSON.stringify(Object.fromEntries(entries)));
                  update(entries);
                  onWritable(outputs.map(name => name === path ? target : name).join('\n'));
                  setError('');
                } catch (failure) { event.target.value = path; setError(failure instanceof Error ? failure.message : 'Choose a safe relative path.'); }
              }} />
            </label>
            <label className="flex gap-2 text-body-sm"><input type="checkbox" checked={outputs.includes(path)} disabled={locked} onChange={event => onWritable((event.target.checked ? [...outputs, path] : outputs.filter(name => name !== path)).join('\n'))} className="w-4 h-4 rounded border-bifang-border bg-bifang-surface text-bifang-brand-orange focus:ring-bifang-brand-orange" />Allow the agent to change this file</label>
            <pre className="max-h-56 overflow-auto whitespace-pre-wrap rounded-lg border-bifang-border bg-bifang-canvas p-3 text-code text-bifang-text-secondary" aria-label={`Source preview ${path}`}>{content || '(empty file)'}</pre>
            <button type="button" className="btn-secondary btn-sm" disabled={locked} onClick={() => { update(Object.entries(files).filter(([name]) => name !== path)); onWritable(outputs.filter(name => name !== path).join('\n')); }}><Trash2 className="w-3.5 h-3.5 mr-1.5" /> Remove source file</button>
          </div>
        </details>
      ))}
      <details className="animate-in"><summary className="cursor-pointer text-caption text-bifang-text-muted">Advanced · edit source JSON</summary><label className="mt-2 block text-caption text-bifang-text-muted">Selected files · JSON path-to-content object<textarea className={`${inputClass} mt-2 h-40 font-mono`} value={value} onChange={event => onChange(event.target.value)} disabled={locked} spellCheck={false} /></label></details>
    </fieldset>
  );
}