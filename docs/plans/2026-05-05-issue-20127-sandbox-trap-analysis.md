# Issue #20127 — "Sandbox Trap" analysis

> Background context for maintainers reviewing the disclosure fix shipped on
> branch `fix/issue-20127`. Not user documentation; lives here so the fix's
> *why* survives without bloating the user docs.

## What was reported

> Using `terminal` with `background=true` (especially when running tools
> like `npx live-server` or `npm`-based servers) triggers an automatic
> transition to the Docker sandbox. Once the session enters the sandbox,
> all subsequent `write_file` calls return "Success" in the logs, but the
> changes are written to a virtual mirror and do not reflect on the host
> filesystem.

The reporter named this the **"Sandbox Trap"**: a session that *appears*
local but, after a single background-process call, silently behaves as a
sandbox session — losing host filesystem writes and the ability to manage
host PIDs.

## What actually happens in the code

There is **no mid-session backend transition** in `tools/terminal_tool.py`.
The active backend is read once per call from
`os.getenv("TERMINAL_ENV", "local")` (see `_get_env_config()` and
`_create_environment()`); it is never overwritten by the tool itself. The
RL/benchmark environments under `environments/` *can* set
`os.environ["TERMINAL_ENV"]` at startup (see
`environments/hermes_base_env.py` and the `terminalbench_2` env), but those
are entered explicitly from a benchmark config, not from a CLI session
calling `terminal(background=True)`.

The `background=true` codepath itself just routes on the *already-selected*
`env_type`:

```python
if env_type == "local":
    proc_session = process_registry.spawn_local(...)
else:
    proc_session = process_registry.spawn_via_env(env=env, ...)
```

So: **the process landed in Docker because the session was already on
`TERMINAL_ENV=docker`**, not because `background=true` flipped a switch.
Most likely paths to that pre-existing state on the reporter's machine:

* `hermes setup` previously selected `docker` (the wizard offers it for
  isolation on macOS).
* `~/.hermes/.env` carries `TERMINAL_ENV=docker` from an earlier session.
* The CLI was started with a profile / `cli-config.yaml` whose
  `terminal.backend: docker` value was bridged into the env at boot
  (`cli.py:_apply_terminal_config`).
* A shell `export TERMINAL_ENV=docker` in the user's rc files.

## Why this looked like an "automatic transition"

Before this fix, the JSON returned by `terminal()` for a successful
`background=true` spawn never named the backend:

```json
{
  "output": "Background process started",
  "session_id": "proc_abc...",
  "pid": 1234,
  "exit_code": 0,
  "error": null
}
```

Foreground commands also do not advertise the backend in their result.
Combined with the fact that `write_file` and `terminal` *both* operate
inside the same sandbox (so foreground writes early in the session looked
fine because nothing on the host had been disturbed yet), users only
noticed something was off the first time they:

1. started a background server, then
2. expected `kill <pid>` from a *new* foreground call to reach a host PID,
   or
3. expected `write_file` to land on `~/Desktop` after the sandbox had
   actually been instantiated as a side effect of the background spawn.

In other words: the bug is a **discoverability / disclosure failure**, not
a backend-selection failure. The session has been on Docker the entire
time; the first long-lived background process is just when the cracks
become visible.

## What the fix does

`tools/terminal_tool.py` now includes the active backend in the JSON
returned from `terminal(background=True)`:

```json
{
  "output": "Background process started",
  "session_id": "proc_abc...",
  "pid": 1234,
  "exit_code": 0,
  "error": null,
  "backend": "docker",
  "backend_note": "This background process runs INSIDE the docker sandbox, not on the host. ..."
}
```

* `backend` is always present (`"local"`, `"docker"`, `"modal"`,
  `"singularity"`, `"daytona"`, `"vercel_sandbox"`, `"ssh"`).
* `backend_note` is added only for non-local backends and spells out:
  * the spawned PID is sandbox-local; host `ps`/`kill` will not see it,
  * `write_file` from the same task lands inside the sandbox unless a host
    bind mount is configured,
  * how to switch back to local (`TERMINAL_ENV=local` or re-running
    `hermes setup`).
* A matching `logger.info(...)` line lets operators see the same signal
  in stderr, so it shows up in `hermes doctor` / log scrapes too.

This is intentionally the smallest fix that resolves #20127 without
changing semantics. Backend selection itself is unchanged: callers who
configured Docker still get Docker — they just get told.

## What the fix deliberately does NOT do

* It does not auto-fall-back to local when Docker is unavailable. That
  would be a real backend transition and is out of scope for this issue.
* It does not change the foreground response shape. Foreground commands
  hit the same backend, but the cross-tool filesystem confusion is mostly
  a long-lived-process problem, and adding a `backend` field to every
  foreground response is a much larger schema change with downstream
  impact on log compression and trajectory storage.
* It does not surface the backend in the `file_tools` response.
  `_get_file_ops()` already shares the same `_active_environments` cache
  as `terminal_tool`, so once the user knows the terminal backend they
  know the file-ops backend too. A future enhancement could mirror this
  disclosure into `write_file`/`read_file` results, but that is
  user-facing schema growth that warrants its own RFC.

## Testing

`tests/tools/test_terminal_background_backend_disclosure.py` pins the new
contract: six tests covering local / docker / modal disclosure, the
warning-note content, the spawn-routing regression, and the unchanged
session_id / pid / exit_code shape.

## Future work (out of scope here)

* Wire the same `backend` field into the foreground `terminal()` result.
* Wire it into `write_file` / `read_file` / `apply_patch` so the model
  cannot mistake a sandbox write for a host write.
* Add a `hermes doctor` warning when `TERMINAL_ENV=docker` is set but the
  user has *not* configured any host bind mounts (the most common shape
  of #20127 in the wild).
* Consider a session-start banner in CLI / TUI that announces the active
  backend the first time `terminal()` is invoked.
