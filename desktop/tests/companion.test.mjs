import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

test('companion reuses the native remote transport without local agent commands or plugins', async () => {
  const source = await readFile(new URL('../../companion/src-tauri/src/lib.rs', import.meta.url), 'utf8');
  assert.match(source, /desktop\/src-tauri\/src\/remote.rs/);
  for (const command of ['remote_connect', 'remote_disconnect', 'remote_operation']) assert.match(source, new RegExp(`remote::${command}`));
  assert.doesNotMatch(source, /spawn_server|get_file_tree|resolve_workspace_path|ShellExt|dotenv|\.plugin\(/);
  const configuration = JSON.parse(await readFile(new URL('../../companion/src-tauri/tauri.conf.json', import.meta.url), 'utf8'));
  assert.equal(configuration.bundle.externalBin, undefined);
  assert.doesNotMatch(configuration.app.security.csp, /\*|unsafe-eval|http:\/\/localhost:8000/);
  const capability = JSON.parse(await readFile(new URL('../../companion/src-tauri/capabilities/default.json', import.meta.url), 'utf8'));
  assert.deepEqual(capability.permissions, ['core:default']);
});

test('companion shares approval UI rather than forking state or persisting tokens', async () => {
  const source = await readFile(new URL('../../companion/src/main.tsx', import.meta.url), 'utf8');
  assert.match(source, /desktop\/src\/components\/RemoteWorkspace/);
  assert.doesNotMatch(source, /localStorage|sessionStorage|fetch\(|api_key|API_KEY/);
  const style = await readFile(new URL('../../companion/src/style.css', import.meta.url), 'utf8');
  assert.match(style, /safe-area-inset-top/);
  assert.match(style, /safe-area-inset-bottom/);
  assert.match(style, /min-height: 44px/);
  assert.match(style, /font-size: 16px/);
});
