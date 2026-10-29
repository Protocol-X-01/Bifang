# Forge pulse

The local desktop Workbench includes **Forge pulse**: CPU, memory and the
selected workspace's filesystem readings. It collects host measurements using
the locked [psutil APIs](https://psutil.io/), without administrative elevation.

| Reading | Meaning |
| --- | --- |
| CPU | Host-wide utilization using a blocking sample with a 100 ms target interval, not a first-call placeholder or inference benchmark. OS scheduling can lengthen the interval. |
| Memory | Total minus available memory; the panel also shows available and total bytes. This is not simply total minus free RAM. |
| Workspace disk | Free/total space and the operating system's utilization percentage for the filesystem containing the selected workspace. Reserved filesystem space can make this percentage differ from used divided by total. |
| GPU | Explicitly unconfigured until a real GPU telemetry provider is connected. Local CPU readings are not Nebius GPU measurements. |

Successful samples refresh five seconds after the previous result while the
panel is open. Collection is serialized with other native workbench operations.
Closing the panel or changing projects discards late results and cancels future
polling. A collection failure stops polling until **Retry readings**; the last
sample is labelled as such rather than silently presented as current.

Each response includes a UTC sample timestamp and collection duration; the UI
shows the timestamp in local time. Collection duration excludes sidecar startup
and native IPC overhead and is not agent/model latency. Individual unsupported,
denied or invalid measurements are labelled unavailable, not replaced by zero.
In a container or VM these are OS-visible readings, not a promise of cgroup
quota accounting or physical-host visibility.

## Local data path

The existing main-window-origin-checked `workbench_request` command invokes
the fixed sidecar `--workbench` mode with action `metrics.sample`. It remains a
bounded single-request stdio exchange, without a metrics HTTP endpoint, model
tool or remote execution hook. Native child environment filtering and dotenv
opt-out also apply here. No process list, hostname, network interface details,
environment variables or provider credentials are returned. Readings stay in
the open panel's memory; they are not persisted or sent to tracing/model vendors.

For an interactive system monitor, open the separately confirmed **Local
terminal** and run `btop` where installed. This panel does not install or inject
terminal commands automatically.

## Evidence scope

Development version **0.2.1-dev.8** adds this source and locked dependency.
The retained dev.7 installer and its fresh-Ubuntu receipt predate these readings.
Unit tests cover real Linux sampling, partial OS failures, invalid readings,
memory semantics and polling cancellation. Native helper/transport acceptance
must use a new helper containing psutil and `metrics.sample`. Windows/macOS
runtime and actual native-window acceptance remain separate checks.
