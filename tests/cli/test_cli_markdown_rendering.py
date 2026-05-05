from io import StringIO

from rich.console import Console
from rich.markdown import Markdown

from cli import _render_final_assistant_content


def _render_to_text(renderable) -> str:
    buf = StringIO()
    Console(file=buf, width=80, force_terminal=False, color_system=None).print(renderable)
    return buf.getvalue()


def test_final_assistant_content_uses_markdown_renderable():
    renderable = _render_final_assistant_content("# Title\n\n- one\n- two")

    assert isinstance(renderable, Markdown)
    output = _render_to_text(renderable)
    assert "Title" in output
    assert "one" in output
    assert "two" in output


def test_final_assistant_content_preserves_windows_hidden_dir_paths():
    renderable = _render_final_assistant_content(
        r"D:\Projects\SourceCode\hermes-agent\.ai\skills" + "\\"
    )

    output = _render_to_text(renderable)
    assert r"D:\Projects\SourceCode\hermes-agent\.ai\skills" + "\\" in output


def test_final_assistant_content_keeps_non_path_markdown_escapes():
    renderable = _render_final_assistant_content(r"1\. Not an ordered list")

    output = _render_to_text(renderable)
    assert "1. Not an ordered list" in output
    assert r"1\." not in output


def test_final_assistant_content_strips_ansi_before_markdown_rendering():
    renderable = _render_final_assistant_content("\x1b[31m# Title\x1b[0m")

    output = _render_to_text(renderable)
    assert "Title" in output
    assert "\x1b" not in output


def test_final_assistant_content_can_strip_markdown_syntax():
    renderable = _render_final_assistant_content(
        "***Bold italic***\n~~Strike~~\n- item\n# Title\n`code`",
        mode="strip",
    )

    output = _render_to_text(renderable)
    assert "Bold italic" in output
    assert "Strike" in output
    assert "item" in output
    assert "Title" in output
    assert "code" in output
    assert "***" not in output
    assert "~~" not in output
    assert "`" not in output


def test_strip_mode_preserves_lists():
    renderable = _render_final_assistant_content(
        "**Formatting**\n- Ran prettier\n- Files changed\n- Verified clean",
        mode="strip",
    )

    output = _render_to_text(renderable)
    assert "- Ran prettier" in output
    assert "- Files changed" in output
    assert "- Verified clean" in output
    assert "**" not in output


def test_strip_mode_preserves_ordered_lists():
    renderable = _render_final_assistant_content(
        "1. First item\n2. Second item\n3. Third item",
        mode="strip",
    )

    output = _render_to_text(renderable)
    assert "1. First" in output
    assert "2. Second" in output
    assert "3. Third" in output


def test_strip_mode_preserves_blockquotes():
    renderable = _render_final_assistant_content(
        "> This is quoted text\n> Another quoted line",
        mode="strip",
    )

    output = _render_to_text(renderable)
    assert "> This is quoted" in output
    assert "> Another quoted" in output


def test_strip_mode_preserves_checkboxes():
    renderable = _render_final_assistant_content(
        "- [ ] Todo item\n- [x] Done item",
        mode="strip",
    )

    output = _render_to_text(renderable)
    assert "- [ ] Todo" in output
    assert "- [x] Done" in output


def test_strip_mode_preserves_table_structure_while_cleaning_cell_markdown():
    renderable = _render_final_assistant_content(
        "| Syntax | Example |\n|---|---|\n| Bold | `**bold**` |\n| Strike | `~~strike~~` |",
        mode="strip",
    )

    output = _render_to_text(renderable)
    assert "| Syntax | Example |" in output
    assert "|---|---|" in output
    # Inline-code spans now preserve their content verbatim (backticks
    # dropped, body kept). This protects program text — e.g. C pointer
    # syntax `uint8_t*` — from having its asterisks eaten by the
    # emphasis regex pass. Inside a code span we no longer try to
    # strip emphasis markers because we cannot tell prose from program.
    assert "| Bold | **bold** |" in output
    assert "| Strike | ~~strike~~ |" in output
    assert "`" not in output


def test_final_assistant_content_can_leave_markdown_raw():
    renderable = _render_final_assistant_content("***Bold italic***", mode="raw")

    output = _render_to_text(renderable)
    assert "***Bold italic***" in output


def test_strip_mode_preserves_intraword_underscores_in_snake_case_identifiers():
    renderable = _render_final_assistant_content(
        "Let me look at test_case_with_underscores and SOME_CONST "
        "then /tmp/snake_case_dir/file_with_name.py",
        mode="strip",
    )

    output = _render_to_text(renderable)
    assert "test_case_with_underscores" in output
    assert "SOME_CONST" in output
    assert "snake_case_dir" in output
    assert "file_with_name" in output


def test_strip_mode_still_strips_boundary_underscore_emphasis():
    renderable = _render_final_assistant_content(
        "say _hi_ and __bold__ now",
        mode="strip",
    )

    output = _render_to_text(renderable)
    assert "say hi and bold now" in output


# --- Issue #20084 regressions: code blocks must preserve `*` verbatim. -----


def test_strip_mode_preserves_asterisks_in_fenced_code_block():
    """C/C++ pointer syntax inside a fenced code block survives a round trip.

    Before the fix, the emphasis-stripping regex pass ran across the full
    rendered text after fence markers were dropped, so a line like
    ``uint8_t* base = (uint8_t*)0x20000000;`` lost its asterisks because
    ``\\*([^*]+)\\*`` matched ``* base = (uint8_t*`` and replaced it with
    its capture group. Code-block content must now be emitted verbatim.
    """
    code = "uint8_t* base = (uint8_t*)0x20000000;"
    src = "Pointer demo:\n\n```c\n" + code + "\n```\n"

    renderable = _render_final_assistant_content(src, mode="strip")
    output = _render_to_text(renderable)

    assert code in output
    assert "uint8_t base = (uint8_t)0x20000000;" not in output


def test_strip_mode_preserves_asterisks_in_tilde_fenced_block():
    """``~~~`` fenced blocks behave the same as ``\u0060\u0060\u0060`` blocks."""
    code = "int *p = &x; *p = 42;"
    src = "~~~\n" + code + "\n~~~\n"

    renderable = _render_final_assistant_content(src, mode="strip")
    output = _render_to_text(renderable)

    assert code in output


def test_strip_mode_preserves_underscores_in_fenced_code_block():
    """snake_case identifiers in code blocks must keep their underscores."""
    code = "def my_func(my_arg):\n    return my_arg * 2"
    src = "```python\n" + code + "\n```\n"

    renderable = _render_final_assistant_content(src, mode="strip")
    output = _render_to_text(renderable)

    assert "my_func" in output
    assert "my_arg" in output
    assert "my_arg * 2" in output


def test_strip_mode_preserves_inline_code_asterisks():
    """Inline code spans must also preserve ``*`` literally."""
    src = "Use `uint8_t*` for raw memory and call `*ptr` to deref."

    renderable = _render_final_assistant_content(src, mode="strip")
    output = _render_to_text(renderable)

    assert "uint8_t*" in output
    assert "*ptr" in output
    # Backticks themselves are still dropped (consistent with prior behaviour).
    assert "`" not in output


def test_strip_mode_still_strips_emphasis_outside_code_blocks():
    """The fix must not regress emphasis stripping in surrounding prose."""
    src = (
        "This is **bold** outside.\n\n"
        "```c\n"
        "int *p;\n"
        "```\n\n"
        "And this is *italic* after.\n"
    )

    renderable = _render_final_assistant_content(src, mode="strip")
    output = _render_to_text(renderable)

    assert "This is bold outside" in output
    assert "And this is italic after" in output
    assert "int *p;" in output
    assert "**bold**" not in output
    assert "*italic*" not in output


def test_strip_mode_handles_multiple_code_blocks_in_one_message():
    src = (
        "First **block**:\n\n"
        "```c\n"
        "a *b;\n"
        "```\n\n"
        "Then more *prose*.\n\n"
        "```c\n"
        "c *d;\n"
        "```\n"
    )

    renderable = _render_final_assistant_content(src, mode="strip")
    output = _render_to_text(renderable)

    assert "First block:" in output
    assert "a *b;" in output
    assert "Then more prose." in output
    assert "c *d;" in output
    assert "**" not in output


def test_streaming_line_strip_preserves_asterisks_inside_code_fence():
    """Per-line streaming strip tracks fence state across deltas.

    The streaming display calls ``_strip_markdown_line_streaming`` once
    per complete line as it arrives, long after the originating fence
    opener was emitted. The helper must therefore carry fence state on
    the streamer instance — otherwise a code-block line streamed in
    isolation looks like prose and has its asterisks eaten.
    """
    from types import SimpleNamespace

    from cli import HermesCLI

    streamer = SimpleNamespace(
        _stream_in_code_fence=False,
        _stream_code_fence_marker=None,
    )
    strip = HermesCLI._strip_markdown_line_streaming.__get__(streamer)

    # Stream a fenced C block one line at a time.
    assert strip("```c") == ""  # opener swallowed
    assert streamer._stream_in_code_fence is True
    assert strip("uint8_t* base = (uint8_t*)0x20000000;") == (
        "uint8_t* base = (uint8_t*)0x20000000;"
    )
    assert strip("int *p = &x;") == "int *p = &x;"
    assert strip("```") == ""  # closer swallowed
    assert streamer._stream_in_code_fence is False

    # Outside the fence, emphasis is still stripped.
    assert strip("This is **bold** prose.") == "This is bold prose."


def test_streaming_line_strip_preserves_inline_code_spans():
    from types import SimpleNamespace

    from cli import HermesCLI

    streamer = SimpleNamespace(
        _stream_in_code_fence=False,
        _stream_code_fence_marker=None,
    )
    strip = HermesCLI._strip_markdown_line_streaming.__get__(streamer)

    assert strip("Call `*ptr` to **deref** the pointer.") == (
        "Call *ptr to deref the pointer."
    )
