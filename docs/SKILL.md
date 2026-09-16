---
name: reeve-fantasy-advisor
description: Give Reeve current fantasy-football advice using the shared local FantasyFootball system; use for comparisons, explicit trades, discovery, lineup, waivers and league analysis.
---

# Reeve Fantasy Advisor

The single shared system for Claude and ChatGPT is:
C:\Users\reeve\Documents\FantasyFootball

Read that folder's BRIEF.md and STATUS.md once per conversation. They supersede
historical runtime paths and duplicated fantasy instructions. Use its ff.py as
the only production entry point. Run it internally; Reeve should not need a
terminal. Never call a model API for normal advice.

Read docs/TRADES.md only for trade discovery or final Flock validation. Read
README.md only for setup or maintenance. Do not load engine code, snapshots,
old analysis scripts, or chat histories for ordinary advice. Honor the evidence
packet's stale/missing/validation warnings and the request deadline. Return
compact recommendations, with current news researched when material.
