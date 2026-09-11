# Using your fantasy advisor

## One shared home

Your working system lives in **C:\Users\reeve\Documents\FantasyFootball**. Codex and Claude Desktop Cowork should use this same folder. You do not need to use a terminal, copy engines between chats, or manage separate versions.

The Codex fantasy skill points here. Claude's local instructions are prepared. **Claude Desktop Cowork folder access and its ability to run the advisor are pending verification.** Prepared instructions alone do not prove a desktop connection works.

In Codex, use a local task with this folder available. In Claude Desktop, use Cowork and select/grant this folder when prompted. For the first request in either assistant, say:

> Use my shared FantasyFootball folder. Read BRIEF.md and STATUS.md, check the advisor's status, and tell me whether you can run a focused question here.

The assistant should report actual access and source ages. If a chat cannot access local files or run the advisor, use a fresh compact evidence packet produced by the connected assistant. Attaching instructions alone does not enable refreshes.

## Ask normally

- “Compare Drake London and Rashee Rice for my team.”
- “Check this trade: I give [players] and get [players]. Include any forced drop.”
- “Set out my best legal lineup for this week, accounting for locked games.”
- “Find up to three realistic trade targets that help both teams.”
- “Who should I prioritize on waivers, and who would I drop?”
- “Refresh the shared projections, then reassess this offer.”

The assistant uses current ownership and league settings, produces focused evidence, and researches news that could change the decision. You should receive a recommendation, the decisive reasons, and what could change it. A lineup recommendation or trade analysis does not submit changes to Sleeper; ask explicitly if you want an action taken.

## Freshness and trade recommendations

Both assistants share saved projections and a short live cache. Ordinary questions use a focused operation; they do not rebuild the season each time. A full refresh is explicit and may take about two minutes. The assistant should refresh once when stale future-week projections matter, then retry the focused question. A failed refresh preserves the last good data and must be disclosed.

“Fetched recently” does not mean the provider published a new forecast. Ask “How old is the evidence?” when timing matters. Offline advice can use saved evidence, with its limitations stated.

Trade discovery produces **research targets**. Before presenting a finalist as validated, the assistant must check material current news, supported lineup improvement, and Flock's complete, stable **Fair Trade!** verdict for the current-year PPR Redraft setting. Until those checks are observed, the trade stays research-only. Engine scores do not establish fairness or the other manager's willingness to accept.

## Switching assistants

Start the other assistant in the same folder and say:

> Continue using BRIEF.md and STATUS.md. Use the latest shared evidence if it answers this question and is still current. Check source ages before refreshing.

Conversation history is not the database. Ask the assistant to record a material negotiation or unresolved fact in STATUS.md with its date and sources before switching. A new offer still needs your exact give/get terms and current ownership.

## Keep usage low

Ask one focused question with the players and decision included. Request a short answer. Reuse current evidence; avoid repeated full-league discovery or refreshes for a two-player comparison. Save deep market checks for decisions they could change. If an operation fails, have the assistant explain the missing evidence instead of repeatedly retrying it.

## Files and maintenance

- **USER_GUIDE.md:** this practical guide.
- **BRIEF.md:** standing instructions and league context; read at each new conversation.
- **STATUS.md:** verified setup status, limitations, and material handoff facts.
- **README.md:** operational reference for the assistant.
- **ff.py:** the single production entry point; the assistant runs it for you.

For ordinary advice, never load engine source, full snapshots, old chats, or audit bundles into the conversation. Keep API keys private. Historical Downloads and the mirrored ChatGPT project are references, not the working system.

For maintenance, request a specific fix. Have **one assistant edit at a time** and let the other review the same changes. The editing assistant should preserve unrelated work, run the relevant checks, and commit the finished change. Ordinary advice should not change code.
