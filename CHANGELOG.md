# Changelog

All notable user-facing changes go here. The repository uses
`RELEASE_v*.md` files for full per-release notes; this file collects
incremental fixes between releases under `## Unreleased`.

## Unreleased

### Fixed

- **TUI / final-response strip mode:** Markdown rendering no longer eats
  `*` characters inside fenced code blocks or inline code spans. Lines
  like `uint8_t* base = (uint8_t*)0x20000000;` and snippets such as
  `` `uint8_t*` `` are now emitted verbatim, so C/C++ pointer syntax,
  glob arguments, and regex literals stay readable. Emphasis stripping
  in surrounding prose is unchanged. Both the full-text path
  (`_render_final_assistant_content(..., mode="strip")`) and the
  per-delta streaming path (`_emit_stream_text` →
  `_strip_markdown_line_streaming`) carry fence state correctly across
  lines and across streaming chunks. (#20084)
