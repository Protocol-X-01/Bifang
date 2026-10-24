export async function chatErrorMessage(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (body && typeof body === 'object' && 'detail' in body &&
        typeof body.detail === 'string' && body.detail.trim()) {
      return body.detail;
    }
  } catch {
    return `Chat request failed (HTTP ${response.status}).`;
  }
  return `Chat request failed (HTTP ${response.status}).`;
}
