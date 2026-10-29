export type ApprovalMode = 'manual' | 'auto' | 'full';

export function approvalRequest(mode: ApprovalMode) {
  if (!['manual', 'auto', 'full'].includes(mode)) throw new Error('Invalid approval mode');
  return { approval_mode: mode, full_access_confirmed: mode === 'full' };
}
