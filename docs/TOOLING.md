# TOOLING.md — dev tooling for this repo

How Claude Code and Codex are equipped to work on this project. Setup state as
of 2026-09-13. This is about *building* the advisor; `BRIEF.md` governs *using*
it.

Four tools, chosen for this repo specifically. Three are MCP servers in
`.mcp.json`; one is a Claude Code plugin.

---

## Status

| Tool | What it's for | State |
|---|---|---|
| `.mcp.json` | project MCP config, committed so both assistants share it | **written** |
| `CONTEXT7_API_KEY` | user env var, keeps the key out of the tracked file | **set — verify it isn't the placeholder** |
| Serena | symbol-level code nav over `advisor.py` (98KB) etc. | pending first launch |
| Context7 | version-pinned docs for pandas 3.0 / numpy 2.4 / scipy 1.17 | pending first launch |
| Playwright | the Flock **Fair Trade!** browser check `BRIEF.md` requires | pending first launch |
| Ponytail | anti-over-engineering ruleset | **not installed** |

---

## Remaining steps

### 1. Verify the Context7 key

```powershell
[Environment]::GetEnvironmentVariable('CONTEXT7_API_KEY','User')
```

If it prints `ctx7sk-your-key-here`, the placeholder was never replaced:

```powershell
[Environment]::SetEnvironmentVariable('CONTEXT7_API_KEY','<real key>','User')
```

Restart PowerShell after any change — env vars don't apply to the open shell.

### 2. Write `.mcp.json`

Only if it's missing or lacks the `headers` line. Run from the repo root; the
`@' ... '@` here-string is literal, so nothing gets mangled by PowerShell.

```powershell
@'
{
  "mcpServers": {
    "serena": {
      "command": "uvx",
      "args": [
        "--from", "git+https://github.com/oraios/serena",
        "serena", "start-mcp-server",
        "--context", "ide-assistant",
        "--project", "C:\\Users\\reeve\\Documents\\FantasyFootball"
      ]
    },
    "context7": {
      "type": "http",
      "url": "https://mcp.context7.com/mcp",
      "headers": { "Authorization": "Bearer ${CONTEXT7_API_KEY}" }
    },
    "playwright": {
      "command": "npx",
      "args": ["-y", "@playwright/mcp@latest"]
    }
  }
}
'@ | Set-Content -Path .mcp.json -Encoding utf8
```

### 3. Launch and approve

```powershell
claude
```

Approve the three servers when prompted, then `/mcp` to confirm all three read
**connected**. First launch is slow — `uvx` pulls and builds Serena from git.
That's a build, not a hang.

### 4. Install Ponytail

Inside `claude`:

```
/plugin marketplace add DietrichGebert/ponytail
/plugin install ponytail@ponytail
```

Then `/ponytail lite` — **not `ultra`**. See gotchas.

Worth running once installed: `/ponytail-audit`. This repo shipped T2a, T2c,
T2d, T2e and T2f as separate tickets stacked on a T2b that is still deferred.
That is the exact pattern ponytail is built to flag.

### 5. Commit

```powershell
git add .mcp.json docs/TOOLING.md
git commit -m "Add project MCP config and tooling doc"
```

`.mcp.json` is not in `.gitignore` and should be committed — it references
`${CONTEXT7_API_KEY}`, never the secret itself. Committing it is what keeps the
Claude-side and Codex-side configs from drifting apart again.

---

## Gotchas

- **`claude mcp add` breaks in PowerShell.** The `--` separator doesn't survive
  to Claude Code's argument parser, so it reads `--from` as its own flag and
  errors with `unknown option '--from'`. Write `.mcp.json` directly instead.
  This will bite again for any future stdio server — use the here-string.
- **`--context ide-assistant` is load-bearing.** It disables Serena's own
  file-read and edit tools so they don't duplicate Claude Code's built-ins.
  Without it Serena roughly doubles the tool budget and costs more context than
  it saves.
- **Claude Code must be ≥ v1.0.52** (`claude --version`). Earlier builds don't
  read MCP server system prompts at startup and Serena silently underperforms.
- **A missing env var fails quietly.** Claude Code loads the config anyway and
  sends the literal string `${CONTEXT7_API_KEY}` as the bearer token.
  `claude mcp list` shows a missing-variable warning — check there first if
  Context7 starts 401ing.
- **Context7 cut its free tier ~92%** and has an open rate-limit bug. The key
  matters; without it you'll throttle mid-session.
- **Don't run ponytail in `ultra`.** Its documented weak spot is mature repos
  with established conventions, and it's benchmarked against a bare FastAPI
  template. This repo has strong conventions (`BRIEF.md`, `docs/TRAPS.md`, the
  one-ticket-per-session rule) that ultra mode will fight. `lite` or `full`.
- **Ponytail is an instruction layer, not a guarantee.** It needs a frontier
  model and doesn't replace review.
- **Cowork can't run any of this.** The isolated Linux workspace on
  `sigma-laptop` has failed to start since 2026-09-11, so a Cowork session can
  read and write files here but cannot execute `python ff.py` or install
  anything. Claude Code in PowerShell is the working path; Codex is the other.

---

## Deliberately not installed

Each of these gets recommended constantly and is dead weight here. Every MCP
server costs context in every session just from its tool definitions, so four is
about the ceiling before it eats the budget it's meant to save.

- **GitHub MCP** — this repo is local with no remote configured.
- **Filesystem MCP** — Claude Code already has file tools.
- **Postgres MCP** — no database.
- **sequential-thinking** — noise on a frontier model.

---

## Open item

(none — CLAUDE.md points at BRIEF.md, which carries the dev conventions.
 Verified 2026-09-12: ordinary-advice, one-editor-at-a-time, selftest, and
 no-version-suffix rules all present at BRIEF.md:6, 84, 86-87.)
