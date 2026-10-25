import { useRef, useState } from 'react';
import { importCodingFiles, selectedCodingFiles } from '../api/remoteCoding';

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
  const inputClass = 'w-full rounded-lg border border-border bg-background px-3 py-2 text-sm focus:ring-2 focus:ring-brand-primary';

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

  return <fieldset className="space-y-3 rounded-xl border border-border p-4" disabled={locked}>
    <legend className="px-2 text-sm font-medium">Selected source · {paths.length}/8 files</legend>
    <p className="text-xs text-muted-foreground">Choose individual UTF-8 files. They stay on this device until you confirm sharing and request a proposal. Imported files start read-only; enable only the paths the agent may change.</p>
    <div className="flex flex-wrap gap-2">
      <button type="button" className="btn-secondary" onClick={() => picker.current?.click()} disabled={locked || paths.length >= 8}>{reading ? 'Reading source…' : 'Choose source files'}</button>
      <button type="button" className="btn-secondary" disabled={locked || paths.length >= 8} onClick={() => {
        let path = 'source.py';
        for (let index = 1; Object.prototype.hasOwnProperty.call(files, path); index++) path = `source-${index}.py`;
        update([...Object.entries(files), [path, '']]);
      }}>Add a source snippet</button>
      <input ref={picker} type="file" multiple className="sr-only" tabIndex={-1} aria-label="Import selected source files" disabled={locked} onChange={event => { if (event.target.files?.length) void importFiles(Array.from(event.target.files)); }} />
    </div>
    {error && <p role="alert" className="text-sm text-red-300">{error}</p>}
    {paths.length === 0 && <p className="rounded-lg border border-dashed border-border p-5 text-center text-sm text-muted-foreground">A focused task starts with a few carefully selected files.</p>}
    {Object.entries(files).map(([path, content]) => <details key={path} className="rounded-lg border border-border bg-background p-3">
      <summary className="cursor-pointer text-sm"><span className="font-mono">{path}</span><span className="ml-3 text-xs text-muted-foreground">{new TextEncoder().encode(content).length.toLocaleString()} bytes · {outputs.includes(path) ? 'writable' : 'read-only'}</span></summary>
      <div className="mt-3 space-y-3">
        <label className="block text-xs">Relative source path<input className={`${inputClass} font-mono`} defaultValue={path} disabled={locked} onBlur={event => {
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
        }} /></label>
        <label className="flex gap-2 text-sm"><input type="checkbox" checked={outputs.includes(path)} disabled={locked} onChange={event => onWritable((event.target.checked ? [...outputs, path] : outputs.filter(name => name !== path)).join('\n'))} />Allow the agent to change this file</label>
        <pre className="max-h-56 overflow-auto whitespace-pre-wrap rounded-lg border border-border p-3 text-xs" aria-label={`Source preview ${path}`}>{content || '(empty file)'}</pre>
        <button type="button" className="btn-secondary text-xs" disabled={locked} onClick={() => { update(Object.entries(files).filter(([name]) => name !== path)); onWritable(outputs.filter(name => name !== path).join('\n')); }}>Remove source file</button>
      </div>
    </details>)}
    <details><summary className="cursor-pointer text-xs text-muted-foreground">Advanced · edit source JSON</summary><label className="mt-2 block text-sm">Selected files · JSON path-to-content object<textarea className={`${inputClass} mt-2 h-40 font-mono`} value={value} onChange={event => onChange(event.target.value)} disabled={locked} spellCheck={false} /></label></details>
  </fieldset>;
}
