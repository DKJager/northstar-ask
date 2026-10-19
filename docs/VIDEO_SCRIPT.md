# Northstar Ask: Demo Video Script (target 2 min 35 s, under the 3-minute limit)

Record the simulator in `SAMPLE_MODE` (see the README quickstart). Type the
questions exactly as written: sample mode matches recorded questions by
wording. Every spoken reply starts "Recorded sample:", and the script says so.
All data is fictional. No third-party logos or music.

## 0:00-0:20 Hook

*(Screen: simulator home with the Echo Show-style frame.)*

VOICEOVER: "Meet Northstar Ask, a voice business analyst you can talk to
like a colleague. It is a self-hosted MCP server for Alexa+, and what you
see now replays recorded sample answers over a fictional outdoor-gear
retailer."

*(Type: "Which region sold the most tents this year?" The reply plays and a
card appears.)*

## 0:20-0:55 Multi-turn

VOICEOVER: "It is not a single-turn bot. Follow-ups ride on the
conversation's session."

*(Type: "And last quarter?" A card for the earlier quarter appears.)*
*(Type: "Break that down by sales channel." A channel card appears.)*

VOICEOVER: "Three turns, one session. The server hands each turn to the
answering service with the same session id."

## 0:55-1:25 Weekly brief

*(Click "Weekly brief".)*

VOICEOVER: "One request, no further input from me: the service chains
several analysis steps and returns a spoken summary with multiple cards."

*(The summary plays; the cards appear in order.)*

## 1:25-1:55 Correct me

*(Click "Correct me" and type: "Sleeping bags: Mountain led, not Pacific.")*

VOICEOVER: "If it gets something wrong, I tell it. The correction goes to the
service as feedback on that answer."

*(Type: "Which region sold the most sleeping bags last quarter?" The reply
begins "Improved from your feedback" and the card shows Mountain.)*

VOICEOVER: "In this recorded demo that improved reply is a recording. The
live service is where it learns."

## 1:55-2:15 Low confidence

*(Type: "Are returns hurting our margins in the Central region?")*

VOICEOVER: "And when the data cannot support an answer, it says so: a
low-confidence card, flagged as directional."

## 2:15-2:35 Close

*(Screen: README quickstart, then the end card.)*

VOICEOVER: "The repository has setup and run steps, tests for the MCP
transport, the Lambda entry point and the simulator, and an AWS SAM
template. Northstar Ask, by 3Dogs Nexus: ask your numbers out loud."

*(End card: project name, track Alexa+, mini challenge AWS Builder.)*
