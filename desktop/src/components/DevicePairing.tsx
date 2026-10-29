import { useEffect, useRef, useState } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { Loader2, AlertTriangle, CheckCircle, X, Phone, Shield, Key, RefreshCw, Globe, Check } from 'lucide-react';

type Challenge = { attempt: string; user_code: string; expires_in: number; interval: number };
type RequestState = { cancelled: boolean; attempt?: string; wake?: () => void };

export function DevicePairing({ endpoint, disabled, onBusy, onConnected }: {
  endpoint: string; disabled: boolean; onBusy: (busy: boolean) => void; onConnected: () => Promise<void>;
}) {
  const [label, setLabel] = useState('My phone');
  const [challenge, setChallenge] = useState<Challenge | null>(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState('');
  const request = useRef<RequestState | null>(null);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      const current = request.current;
      if (current) {
        current.cancelled = true;
        current.wake?.();
        if (current.attempt) void invoke('remote_pair_cancel', { attempt: current.attempt })
          .catch((e) => console.error('[DevicePairing] Failed to cancel pairing:', e));
      }
    };
  }, []);

  async function cancel() {
    const current = request.current;
    if (!current) return;
    current.cancelled = true;
    current.wake?.();
    if (current.attempt) {
      try { await invoke('remote_pair_cancel', { attempt: current.attempt }); }
      catch { if (mounted.current) setError('Pairing stopped locally. Service cancellation could not be confirmed; requests expire after five minutes.'); }
    }
  }

  async function begin() {
    if (disabled || request.current || !endpoint.trim()) return;
    const current: RequestState = { cancelled: false };
    request.current = current;
    setStarting(true);
    setError('');
    onBusy(true);
    try {
      const started = await invoke<Challenge>('remote_pair_begin', { endpoint: endpoint.trim(), label: label.trim() });
      current.attempt = started.attempt;
      if (current.cancelled) {
        await invoke('remote_pair_cancel', { attempt: started.attempt });
        return;
      }
      setChallenge(started);
      const deadline = Date.now() + started.expires_in * 1000;
      let delay = started.interval;
      while (!current.cancelled) {
        await new Promise<void>(resolve => {
          const timer = setTimeout(resolve, delay * 1000);
          current.wake = () => { clearTimeout(timer); resolve(); };
        });
        if (current.cancelled) return;
        if (Date.now() >= deadline) throw new Error('Pairing expired. Start again to get a new code.');
        const result = await invoke<{ status: string; retry_after?: number }>('remote_pair_poll', { attempt: started.attempt });
        if (current.cancelled) {
          await invoke('remote_pair_cancel', { attempt: started.attempt });
          return;
        }
        if (result.status === 'connected') {
          request.current = null;
          current.attempt = undefined;
          await onConnected();
          return;
        }
        if (result.status !== 'pending' || !Number.isInteger(result.retry_after) || result.retry_after! < 1 || result.retry_after! > 30) throw new Error('Invalid pairing response.');
        delay = result.retry_after!;
      }
    } catch (failure) {
      if (current.attempt) {
        try { await invoke('remote_pair_cancel', { attempt: current.attempt }); }
        catch { if (mounted.current) setError('Connection interrupted. Service cancellation could not be confirmed; use desktop device controls to revoke any issued session.'); }
      }
      if (mounted.current && !current.cancelled) setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      if (request.current === current) request.current = null;
      if (mounted.current) { setStarting(false); setChallenge(null); onBusy(false); }
    }
  }

  return (
    <div className="rounded-xl border-bifang-brand-orange/30 bg-bifang-panel p-5 space-y-4 animate-in" aria-label="Pair this device">
      <h3 className="text-h5 text-bifang-text-primary flex items-center gap-2"><Phone className="w-5 h-5 text-bifang-brand-orange" /> Pair with your desktop</h3>
      <p className="text-body-sm text-bifang-text-secondary">Enter the HTTPS origin above, then approve this phone from an already-connected desktop using your Authenticator code. Your phone receives its own access automatically; leave manual token sign-in unused.</p>
      {error && <p role="alert" className="text-body-sm text-bifang-brand-red animate-in">{error}</p>}
      {!starting ? (
        <>
          <label className="block">
            <span className="text-caption text-bifang-text-muted">Device name</span>
            <input className="input mt-1" value={label} maxLength={64} pattern="[A-Za-z0-9 ._-]+" onChange={event => setLabel(event.target.value)} disabled={disabled} />
          </label>
          <button type="button" className="btn-primary w-full" disabled={disabled || !endpoint.trim() || !/^[A-Za-z0-9 ._-]{1,64}$/.test(label.trim())} onClick={() => void begin()}>
            <Globe className="w-4 h-4 mr-1.5" /> Get pairing code
          </button>
        </>
      ) : (
        <>
          {challenge ? (
            <>
              <p className="text-4xl font-mono tracking-widest text-bifang-text-primary font-display animate-in" aria-label="Phone pairing code">{challenge.user_code}</p>
              <p className="text-body-sm text-bifang-text-secondary">Waiting for desktop approval · code expires in {Math.ceil(challenge.expires_in / 60)} minutes.</p>
              <p className="text-caption text-bifang-text-muted">On desktop, open Paired devices. Compare this code before approving. Keep Authenticator codes on the desktop.</p>
            </>
          ) : (
            <p className="text-body-sm text-bifang-text-muted flex items-center gap-2"><Loader2 className="w-4 h-4 animate-spin text-bifang-brand-orange" />Starting secure pairing…</p>
          )}
          <button type="button" className="btn-secondary w-full" onClick={() => void cancel()}><X className="w-4 h-4 mr-1.5" /> Cancel pairing</button>
        </>
      )}
    </div>
  );
}

type Device = { id: string; label: string; expires: number; revoked: number };

export function PairedDevices() {
  const [operator, setOperator] = useState(false);
  const [devices, setDevices] = useState<Device[]>([]);
  const [code, setCode] = useState('');
  const [otp, setOtp] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const mounted = useRef(true);
  const operation = (value: Record<string, unknown>) => invoke<unknown>('remote_operation', { operation: value });

  async function refresh() {
    const reply = await operation({ operation: 'paired_devices' }) as { devices?: Device[] };
    if (!Array.isArray(reply.devices) || reply.devices.length > 64 || reply.devices.some(device => !/^[a-f0-9]{32}$/.test(device.id) || typeof device.label !== 'string' || device.label.length > 64 || !Number.isFinite(device.expires) || ![0, 1].includes(device.revoked))) throw new Error('Invalid paired device list.');
    if (mounted.current) setDevices(reply.devices.filter(device => device.revoked === 0));
  }

  useEffect(() => {
    mounted.current = true;
    void operation({ operation: 'auth_session' }).then(async value => {
      if ((value as { authentication?: string }).authentication === 'operator' && mounted.current) { setOperator(true); await refresh(); }
    }).catch((e) => console.error('[DevicePairing] Pairing failed:', e));
    return () => { mounted.current = false; };
  }, []);

  async function perform(task: () => Promise<void>) {
    if (busy) return;
    setBusy(true);
    setMessage('');
    try { await task(); }
    catch (failure) { if (mounted.current) setMessage(failure instanceof Error ? failure.message : String(failure)); }
    finally { if (mounted.current) { setBusy(false); setOtp(''); } }
  }

  async function decide(approved: boolean) {
    await operation({ operation: 'approve_device', payload: { user_code: code, authenticator_code: otp, approved } });
    if (mounted.current) { setMessage(approved ? 'Approved. The phone will connect shortly; refresh devices after it connects.' : 'Pairing declined.'); setCode(''); }
    await refresh();
  }

  if (!operator) return null;
  return (
    <details className="rounded-xl border-bifang-border bg-bifang-panel p-5 animate-in">
      <summary className="cursor-pointer text-h5 text-bifang-text-primary flex items-center gap-2"><Shield className="w-5 h-5 text-bifang-brand-orange" /> Paired devices · approve a phone</summary>
      <div className="mt-4 space-y-3">
        <p className="text-body-sm text-bifang-text-muted">Only approve a code shown on your own phone. Authenticator must already be enrolled by the service operator.</p>
        {message && <p role="status" className="text-body-sm text-bifang-brand-orange">{message}</p>}
        <label className="block">
          <span className="text-caption text-bifang-text-muted">Phone pairing code</span>
          <input className="input mt-1" value={code} placeholder="ABCD-EFGH" maxLength={9} autoComplete="off" disabled={busy} onChange={event => { const compact = event.target.value.toUpperCase().replace(/[^A-Z2-9]/g, '').slice(0, 8); setCode(compact.length > 4 ? `${compact.slice(0, 4)}-${compact.slice(4)}` : compact); }} />
        </label>
        <label className="block">
          <span className="text-caption text-bifang-text-muted">Authenticator code</span>
          <input className="input mt-1" type="password" inputMode="numeric" autoComplete="off" maxLength={8} value={otp} disabled={busy} onChange={event => setOtp(event.target.value.replace(/\D/g, ''))} />
        </label>
        <div className="flex flex-wrap gap-2">
          {[true, false].map(approved => <button key={String(approved)} className={approved ? 'btn-primary' : 'btn-secondary'} disabled={busy || !/^[A-HJ-NP-Z2-9]{4}-[A-HJ-NP-Z2-9]{4}$/.test(code) || !/^(?:[0-9]{6}|[0-9]{8})$/.test(otp)} onClick={() => void perform(() => decide(approved))}>{approved ? 'Approve phone' : 'Decline pairing'}</button>)}
          <button type="button" className="btn-secondary" disabled={busy} onClick={() => void perform(refresh)}><RefreshCw className="w-4 h-4 mr-1.5" /> Refresh devices</button>
        </div>
        <p className="text-caption text-bifang-text-muted">Paired access lasts one hour and stays in native memory. Disconnect revokes that session.</p>
        <ul className="space-y-2">
          {devices.map(device => (
            <li key={device.id} className="flex flex-wrap items-center gap-3 text-body-sm animate-in">
              <span className="flex items-center gap-2"><Check className="w-4 h-4 text-bifang-success" /> {device.label} · expires {new Date(device.expires * 1000).toLocaleTimeString()}</span>
              <button type="button" className="btn-secondary" disabled={busy} onClick={() => void perform(async () => { await operation({ operation: 'revoke_device', id: device.id }); await refresh(); })}><X className="w-4 h-4 mr-1.5" /> Revoke session</button>
            </li>
          ))}
        </ul>
      </div>
    </details>
  );
}