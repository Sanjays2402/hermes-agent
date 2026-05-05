"""Regression tests for issue #20127 ("Sandbox Trap").

When `terminal(background=True)` is invoked, the JSON result must surface
the active terminal backend so callers can see whether the spawned process
landed on the host or inside a sandbox. For non-local backends an explicit
``backend_note`` warning is included that explains the lifecycle/filesystem
implications (host `kill`/`ps` will not see the PID, file writes from this
task land inside the sandbox, etc.).

Background:
  Issue #20127 reports that with TERMINAL_ENV=docker (the user's pre-existing
  setup, not a mid-session transition), starting a background process and
  then writing files looks "successful" but the writes never reach the host
  filesystem. The terminal_tool's own JSON response never advertised which
  backend it was using, so the agent had no chance to notice. These tests
  pin the new disclosure contract.
"""
import json
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------
def _make_env_config(**overrides):
    """Return a minimal _get_env_config()-shaped dict with optional overrides."""
    config = {
        "env_type": "local",
        "timeout": 180,
        "cwd": "/tmp",
        "host_cwd": None,
        "modal_mode": "auto",
        "docker_image": "",
        "singularity_image": "",
        "modal_image": "",
        "daytona_image": "",
    }
    config.update(overrides)
    return config


def _make_proc_session(sid="proc_test_bg", pid=4242):
    """Return a stand-in for the ProcessSession returned by the registry."""
    proc = MagicMock()
    proc.id = sid
    proc.pid = pid
    # Tests don't drive the watcher metadata path — leave it falsy.
    proc.watcher_platform = ""
    return proc


def _run_background_terminal(env_type: str, *, command: str = "python3 -m http.server 8001"):
    """Invoke terminal_tool with background=True under a stubbed environment.

    Returns the parsed JSON result. The registry spawn calls and environment
    creation are mocked so the test never touches subprocess / Docker.
    """
    from tools.terminal_tool import terminal_tool

    fake_env = MagicMock()
    fake_env.env = {}

    fake_registry = MagicMock()
    fake_registry.spawn_local.return_value = _make_proc_session()
    fake_registry.spawn_via_env.return_value = _make_proc_session()
    fake_registry.pending_watchers = []

    with patch(
        "tools.terminal_tool._get_env_config",
        return_value=_make_env_config(env_type=env_type),
    ), patch("tools.terminal_tool._start_cleanup_thread"), patch(
        "tools.terminal_tool._active_environments", {"default": fake_env}
    ), patch(
        "tools.terminal_tool._last_activity", {"default": 0}
    ), patch(
        "tools.terminal_tool._check_all_guards", return_value={"approved": True}
    ), patch(
        "tools.process_registry.process_registry", fake_registry
    ):
        return json.loads(
            terminal_tool(command=command, background=True, timeout=10)
        )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestBackgroundBackendDisclosure:
    """terminal(background=True) must reveal which backend handled the spawn."""

    def test_local_backend_is_disclosed_without_warning(self):
        """Local backend: backend field present, no warning note attached."""
        result = _run_background_terminal("local")

        assert result["error"] is None
        assert result["backend"] == "local"
        # No scary warning when we're running on the host as advertised.
        assert "backend_note" not in result

    def test_docker_backend_is_disclosed_with_warning(self):
        """Docker backend: backend field present and warning note is attached."""
        result = _run_background_terminal("docker")

        assert result["error"] is None
        assert result["backend"] == "docker"
        note = result.get("backend_note", "")
        assert note, "non-local backend must emit a backend_note"
        # The note must mention the sandbox, host visibility, and the
        # filesystem caveat — those are the three things #20127 was
        # tripping over.
        assert "docker" in note.lower()
        assert "sandbox" in note.lower()
        assert "host" in note.lower()
        # Filesystem warning is the headline symptom of the bug report.
        assert "write_file" in note.lower() or "filesystem" in note.lower() or "sandbox" in note.lower()

    def test_modal_backend_is_disclosed_with_warning(self):
        """Modal backend behaves like docker: backend revealed + warning."""
        result = _run_background_terminal("modal")

        assert result["error"] is None
        assert result["backend"] == "modal"
        assert "modal" in result.get("backend_note", "").lower()

    def test_session_id_and_pid_still_returned(self):
        """The disclosure does not regress the existing session_id / pid contract."""
        result = _run_background_terminal("docker")

        assert result["session_id"] == "proc_test_bg"
        assert result["pid"] == 4242
        assert result["exit_code"] == 0
        assert result["output"] == "Background process started"

    def test_local_backend_uses_spawn_local(self):
        """Local path still goes through spawn_local (regression guard)."""
        from tools.terminal_tool import terminal_tool

        fake_env = MagicMock()
        fake_env.env = {}
        fake_registry = MagicMock()
        fake_registry.spawn_local.return_value = _make_proc_session()
        fake_registry.spawn_via_env.return_value = _make_proc_session()
        fake_registry.pending_watchers = []

        with patch(
            "tools.terminal_tool._get_env_config",
            return_value=_make_env_config(env_type="local"),
        ), patch("tools.terminal_tool._start_cleanup_thread"), patch(
            "tools.terminal_tool._active_environments", {"default": fake_env}
        ), patch(
            "tools.terminal_tool._last_activity", {"default": 0}
        ), patch(
            "tools.terminal_tool._check_all_guards", return_value={"approved": True}
        ), patch(
            "tools.process_registry.process_registry", fake_registry
        ):
            json.loads(
                terminal_tool(command="echo hi", background=True, timeout=10)
            )

        assert fake_registry.spawn_local.called
        assert not fake_registry.spawn_via_env.called

    def test_non_local_backend_uses_spawn_via_env(self):
        """Non-local path still goes through spawn_via_env (regression guard)."""
        from tools.terminal_tool import terminal_tool

        fake_env = MagicMock()
        fake_env.env = {}
        fake_registry = MagicMock()
        fake_registry.spawn_local.return_value = _make_proc_session()
        fake_registry.spawn_via_env.return_value = _make_proc_session()
        fake_registry.pending_watchers = []

        with patch(
            "tools.terminal_tool._get_env_config",
            return_value=_make_env_config(env_type="docker"),
        ), patch("tools.terminal_tool._start_cleanup_thread"), patch(
            "tools.terminal_tool._active_environments", {"default": fake_env}
        ), patch(
            "tools.terminal_tool._last_activity", {"default": 0}
        ), patch(
            "tools.terminal_tool._check_all_guards", return_value={"approved": True}
        ), patch(
            "tools.process_registry.process_registry", fake_registry
        ):
            json.loads(
                terminal_tool(command="echo hi", background=True, timeout=10)
            )

        assert fake_registry.spawn_via_env.called
        assert not fake_registry.spawn_local.called
