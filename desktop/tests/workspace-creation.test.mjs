import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const sidebar = await readFile(new URL('../src/components/Sidebar.tsx', import.meta.url), 'utf8');
const native = await readFile(new URL('../src-tauri/src/commands.rs', import.meta.url), 'utf8');
const main = await readFile(new URL('../src-tauri/src/main.rs', import.meta.url), 'utf8');

test('workspace creation is a separate named action with parent selection and explicit submit', () => {
  assert.match(sidebar, /aria-label="New workspace"/);
  assert.match(sidebar, /Browse parent folder…/);
  assert.match(sidebar, /createWorkspace\(pathInput, workspaceName\)/);
  assert.match(sidebar, /creatingWorkspace && !workspaceName.trim\(\)/);
  assert.match(sidebar, /No packages, scripts or Git setup run automatically/);
});

test('native creation is origin checked and uses non-overwriting directory creation', () => {
  assert.match(main, /commands::create_workspace/);
  assert.match(native, /crate::terminal::local_window\(&window\)\?/);
  assert.match(native, /fs::create_dir\(&directory\)/);
  assert.doesNotMatch(native, /create_dir_all|Command::new/);
});
