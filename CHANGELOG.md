# Changelog

All notable user-facing changes to Hermes Agent will be tracked here. The
project also publishes per-release notes as `RELEASE_v*.md` files at the
repo root; this file collects pending changes between releases.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## Unreleased

### Fixes

- **cron**: Cron jobs without an explicit `model`/`provider` now query the
  local inference server's `/v1/models` endpoint at run time when the
  resolved runtime targets a loopback URL (llama.cpp, Ollama, LM Studio).
  Previously the `model.default` from `config.yaml` was frozen at job
  creation time, so jobs failed silently with a generic "Connection error"
  whenever the local server had a different model loaded — or was down.
  Unreachable servers now surface a clear, actionable error instead.
  Cloud providers (OpenAI, Anthropic, OpenRouter, …) skip this path
  entirely — no extra HTTP roundtrip. ([#20125](https://github.com/NousResearch/hermes-agent/issues/20125))
