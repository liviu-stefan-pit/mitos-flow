"""Cursor CLI adapter services (Phase 21+)."""

from mitos_api.services.cursor.command_builder import (
    BuiltCursorCommand,
    CursorCommandBuildError,
    assemble_prompt,
    build_cursor_command,
    check_workspace_boundary,
    dry_run_cursor_command,
    preview_built_command,
    quote_windows_arg,
    quote_windows_command,
    redact_argv,
)
from mitos_api.services.cursor.executor import (
    CursorExecutionError,
    CursorProcessResult,
    parse_usage_metadata,
    spawn_cursor_command,
)
from mitos_api.services.cursor.probe import (
    MINIMUM_CURSOR_CLI_VERSION,
    get_cursor_capability,
    probe_cursor_capability,
    set_cursor_probe_override,
)

__all__ = [
    "BuiltCursorCommand",
    "CursorCommandBuildError",
    "CursorExecutionError",
    "CursorProcessResult",
    "MINIMUM_CURSOR_CLI_VERSION",
    "assemble_prompt",
    "build_cursor_command",
    "check_workspace_boundary",
    "dry_run_cursor_command",
    "get_cursor_capability",
    "parse_usage_metadata",
    "preview_built_command",
    "probe_cursor_capability",
    "quote_windows_arg",
    "quote_windows_command",
    "redact_argv",
    "set_cursor_probe_override",
    "spawn_cursor_command",
]
