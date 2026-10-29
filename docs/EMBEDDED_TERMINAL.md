# Local terminal

The desktop workbench now has a native PTY terminal in Bifang's Ember palette.
Open **Local terminal**, then **Open local terminal**, review the directory and
choose **Start local shell**. Merely opening a workspace or showing the panel
does not start a process. Cancel is the initially focused confirmation action.

This is **your local shell**, separate from the agent's
[offline execution sandbox](NETWORK_ISOLATION.md). It can change host files and
access the network. Its input and output do not enter model requests, chat
history or a new terminal transcript. Manually sourcing a project or running a
program still grants that program your user privileges.

## Behavior

- Native PTY input, resize and byte-exact output, rendered with bundled xterm.js.
  The terminal renderer is loaded on demand rather than in the initial chat bundle.
- Unix uses system Bash with `--noprofile --norc -i`, or interactive system `sh`
  with startup-hook variables cleared. Windows source uses system PowerShell
  `-NoLogo -NoProfile` through portable-pty; actual Windows runtime proof is pending.
- Environment is rebuilt from a small OS/locale/home allowlist and a fixed
  system PATH. Provider keys, cloud credentials, `BASH_ENV`, `ENV`, `PYTHONPATH`
  and other project startup hooks are not copied from the application environment.
  Shell history persistence is disabled for Unix. Files remain accessible with your normal
  user permissions; an environment allowlist does not hide secrets on disk.
- One local session at a time. The displayed directory is the actual opened
  directory, and does not silently follow later workspace selection changes.
- Hide preserves the session and the navigation button retains a running label.
  **Close shell**, component cleanup and desktop-window close request cleanup.
  Natural exit reports its status. Stale IDs cannot close or write a newer shell.
- Native output queue is capped at 256 KiB, frames and input chunks at 16 KiB;
  rendering acknowledgment precedes another output read. Large output applies
  backpressure instead of an unbounded webview event queue. Scrollback is bounded.
- Terminal escape sequences cannot invoke the model or agent tools. OSC 52
  clipboard escape handling is suppressed and automatic link activation is
  disabled. These are explicit renderer choices, not a claim that host shell
  programs are confined or safe.

Only the main bundled desktop origin (or the exact configured development
origin in debug builds) can invoke these commands. There are no terminal HTTP
routes or model tool registrations. The mobile companion does not import them.
As with any native IPC, a compromised trusted application frontend is outside
this origin check's protection.

## System monitoring

If already installed, type `btop` in the shell to use its real interactive
system monitor. No package or elevated sensor component is installed
automatically. The actual Linux acceptance test opens `/usr/bin/btop` in the
same PTY engine and confirms its alternate-screen behavior without retaining
the process list or raw hardware display. This is not yet a custom metrics
dashboard or proof of Windows/macOS sensor support.

See [btop](https://github.com/aristocratos/btop) and its separate
[Windows port](https://github.com/aristocratos/btop4win). A future monitor launch
button should start an explicitly selected program rather than appending text
to an unknown, partly typed shell command.

## Verification boundary

Rust tests exercise actual PTYs for ANSI output, input, resize, exit code,
stale-session rejection, filtered synthetic environment variables, output
backpressure, prompt close and ordinary background-job termination. The btop
test is explicitly opt-in because it requires an installed binary. Frontend
transport tests cover consent, late-start cleanup, bounded/serialized UTF-8
input, render backpressure, exact exit sequencing and concurrent close.

Those are source/runtime-component checks, not an installed native-window
walkthrough. Visual/native-window verification, accessibility review, packaged
application cleanup and Windows/macOS runs remain required. The local
development version is `0.2.1-dev.7`; published Preview 6 is unchanged. Do not
attribute the new terminal to that older installer or the terminal-only wheel.

Implementation uses [portable-pty](https://docs.rs/portable-pty/0.9.0/portable_pty/)
and [xterm.js](https://xtermjs.org/docs/api/terminal/classes/terminal/), not a
read-only command-output pane presented as an interactive terminal.
