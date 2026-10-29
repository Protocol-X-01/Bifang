# Building from an empty folder

With the default isolated-workspace setting, folders without Git and Git repositories without a first commit use a private folder snapshot. Creating a project still creates only the original directory: it does not install packages, initialize Git, or make a commit there.

When a coding session starts, Bifang copies project files to private workspace storage. Agent edits remain there until you review the diff and choose **Apply to project**. The confirmation is bound to that exact patch. If the agent changes the patch or you change the original folder, Apply refuses the stale result. Starting a new session is the recovery path for a changed original folder; preserve any wanted draft separately first.

For **Isolated engineering**, leave existing source paths blank and list the new files under editable paths. In the TUI, use `[]` for existing source files and an explicit output array such as `["hello.py"]`. An empty selection is rejected. The implementer can write only those selected outputs, still requests write approval, and must pass your independent check before reviewed staging and the separate original-project Apply. A model claiming success is not a verification receipt.

Snapshots support file creation, modification, deletion, binary files and executable modes. They require Git for patch generation/application, but do not create Git metadata in the original folder. Existing committed repositories continue to use Git worktrees.

## Snapshot boundaries

- At most 5000 files and 128 MiB of file contents per snapshot.
- Symlinks and special files are rejected rather than followed.
- `.git`, `.bifang`, `.arca`, dependency/build caches, common credential directories and private `.env` variants are excluded. `.env.example`, `.env.sample` and `.env.template` remain available. This is not a general secret detector; keep credentials out of source files.
- An excluded file created inside the draft is not included in Apply. Install dependencies separately in the original project when appropriate.
- Empty directories, timestamps, ownership and arbitrary permission bits are not reproduced; file contents and executable status are supported.
- Folder snapshots belong to the live session. They are not currently resumable through `bifang boxes`; save a wanted draft before closing the session. Conversation history is separate from draft recovery.
- Explicit nonisolated mode (`BIFANG_WORKTREE=0`) retains direct-edit behavior; this is not the default.

Local regression tests exercise exact HTTP patch approval, source-change rejection, binary/text changes, no-commit repositories, path handling and snapshot cleanup. These are not a claim of native-window or hosted-model validation.
