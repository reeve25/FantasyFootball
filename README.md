# Fantasy Football

The shared local system is `C:\Users\reeve\Documents\FantasyFootball`.
Production starts at **ff.py**. Both assistants read **BRIEF.md** and
**STATUS.md**; no conversation history is the database.

Open this folder in a local Codex task or grant it to a Claude local session.
The installed Codex fantasy skill points here. CLAUDE.md is ready for Claude
Code; a Claude desktop/Cowork session still needs this folder selected/granted.
That desktop connection has not been verified. A chat without local file/tool
access needs the compact evidence packet attached; it cannot refresh this folder
merely because the folder exists.

Ask normally: “Compare London and Rice,” “Check this trade,” or “Find realistic
trade targets.” The assistant runs these commands for you:

```
python ff.py status
python ff.py packet "Compare Drake London and Rashee Rice"
python ff.py trade --give "Drake London" --get "Rashee Rice"
python ff.py lineup
python ff.py discover
python ff.py refresh --rebuild
python ff.py selftest
```

Options: `--offline` uses saved evidence and flags its limitations. `--market`
adds focused sportsbook evidence; `--deep` adds the configured metered odds
check. Global `--timeout 60` goes before the command. Normal engine calls are
capped at 45 seconds, refresh at 120. This bounds the engine, not the assistant's
separate research or reasoning time. Refresh is explicit, shared, and protected
against simultaneous refreshes. Normal advice never rebuilds the full season.

Full evidence and diagnostics stay in ignored `outputs/<run>/`; the chat sees a
compact packet. `outputs/latest.json` points to the last completed run. The
snapshot and short live cache are shared by both assistants. Source age remains
visible, including after failed refreshes. External news and the Flock browser
verdict still require observation; the program never fabricates them.

Internal runtime modules retain the tested legacy projection adapter. Its old
automatic trades, betting probes, and uncalibrated confidence/simulation paths
are not called by ff.py. The newer downloaded v6.3.2 was reviewed, not blindly
promoted. Historical originals stay in Downloads and the mirrored project.

Python 3.12 with requests, pandas, numpy and scipy is installed and used here.
`requirements.txt` records the tested environment. API keys remain in the
existing private `.codex/secrets/reeve-fantasy-advisor.env`, outside Git; no
language-model API is required. An alternate key file can be selected with
REEVE_FANTASY_SECRETS_FILE. The Git repository is local; no remote is configured
and nothing has been published.

For maintenance: inspect `git status`, have one assistant implement, run the
self-test, inspect the diff, and commit. Hand the other assistant the same
revision for review. Do not copy engines between chats or upload stale engine
files as the new production version.
