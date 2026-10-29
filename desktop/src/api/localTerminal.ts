export interface TerminalOpened { id: number; directory: string; program: string }
export interface TerminalFrame { data: number[]; exited: boolean; exit_code: number | null }
export type TerminalInvoke = <Result>(command: string, args: Record<string, unknown>) => Promise<Result>;

export function parseTerminalFrame(value: unknown): TerminalFrame {
  const frame = value as TerminalFrame;
  if (!frame || !Array.isArray(frame.data) || frame.data.length > 16384 ||
      !frame.data.every(byte => Number.isInteger(byte) && byte >= 0 && byte <= 255) ||
      typeof frame.exited !== 'boolean' || !(frame.exit_code === null ||
        Number.isInteger(frame.exit_code) && frame.exit_code >= 0 && frame.exit_code <= 0xffffffff)) {
    throw new Error('Invalid local terminal response');
  }
  return frame;
}

export class LocalTerminal {
  private id: number | null = null;
  private closed = false;
  private opening = false;
  private closing: Promise<void> | null = null;
  private input: Promise<void> = Promise.resolve();
  constructor(private invoke: TerminalInvoke, private output: (bytes: Uint8Array) => Promise<void>,
              private ended: (code: number | null) => void, private failed: (error: unknown) => void) {}

  async start(path: string, rows: number, cols: number, confirmed: boolean): Promise<TerminalOpened | null> {
    if (!confirmed || this.closed || this.opening || this.id !== null) throw new Error('Explicit terminal start is required');
    this.opening = true;
    try {
      const opened = await this.invoke<TerminalOpened>('terminal_open', { path, rows, cols, confirmed });
      if (!Number.isInteger(opened?.id) || opened.id < 1 || opened.id > 0xffffffff ||
          typeof opened.directory !== 'string' || typeof opened.program !== 'string') throw new Error('Invalid terminal session');
      if (this.closed) {
        await this.invoke('terminal_close', { id: opened.id });
        return null;
      }
      this.id = opened.id;
      void this.pump();
      return opened;
    } finally {
      this.opening = false;
    }
  }

  private async pump() {
    try {
      while (!this.closed && this.id !== null) {
        const frame = parseTerminalFrame(await this.invoke('terminal_read', { id: this.id }));
        if (this.closed) return;
        if (frame.data.length) await this.output(Uint8Array.from(frame.data));
        if (frame.exited) {
          try { await this.close(); } catch (error) { this.failed(error); return; }
          this.ended(frame.exit_code);
          return;
        }
        await new Promise(resolve => setTimeout(resolve, frame.data.length ? 0 : 40));
      }
    } catch (error) {
      if (!this.closed) {
        this.failed(error);
        try { await this.close(); } catch (closeError) { this.failed(closeError); }
      }
    }
  }

  send(text: string): Promise<void> {
    const bytes = new TextEncoder().encode(text);
    if (!bytes.length || bytes.length > 1_048_576) return Promise.reject(new Error('Paste at most 1 MiB at a time'));
    const identity = this.id;
    this.input = this.input.catch(() => undefined).then(async () => {
      if (identity === null || this.closed || identity !== this.id) return;
      for (let offset = 0; offset < bytes.length; offset += 16384) {
        if (this.closed) return;
        await this.invoke('terminal_write', { id: identity, data: Array.from(bytes.subarray(offset, offset + 16384)) });
      }
    });
    return this.input;
  }

  async resize(rows: number, cols: number) {
    if (!Number.isInteger(rows) || !Number.isInteger(cols)) throw new Error('Use whole terminal dimensions');
    if (this.closed || this.id === null || rows < 1 || cols < 1) return;
    await this.invoke('terminal_resize', { id: this.id, rows: Math.min(300, rows), cols: Math.min(500, cols) });
  }

  async close() {
    this.closed = true;
    if (this.closing) return this.closing;
    if (this.id !== null) {
      const identity = this.id;
      this.closing = this.invoke('terminal_close', { id: identity }).then(() => {
        if (this.id === identity) this.id = null;
      }).finally(() => { this.closing = null; });
      return this.closing;
    }
  }
}
