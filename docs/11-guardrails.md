# 11 Guardrails

How the principles in the project overview show up in the code on these pages. Use it as a checklist when you change something.

| Principle | Where it lives in code |
| --- | --- |
| Behavior, not opinions | The model labels posts only ([06](06-gemma-labels.md)); its prompt forbids judging the author. Signals ([09](09-signals.md)) read timing, age and duplicated text. No query joins `labels.stance` into flagging. |
| Test the hypothesis | Every chart has both series, all accounts and excluding flagged ([10](10-reports.md)). A small difference is a result. |
| Even-handed | One prompt and one set of thresholds for critical and supportive posts. Check errors in both directions when you hand-check labels. |
| Human review | `reviews` table ([04](04-storage.md)). Until it has rows, the excluded group is labeled "unreviewed". |
| Evidence over verdicts | `signals.evidence` stores what was observed, such as a count or an age in days. |
| Anonymization | `anon_id` and `export_public` ([10](10-reports.md)). |
| No harassment pathways | No export has one row per ordinary account. Agent tools return aggregates only ([07](07-gemma-tools.md)). |
| Transparency | `labels` records the model and prompt version. Publish both with your error rates. |
| Honest automation | `accounts.self_declared_bot`, shown as a separate series. |

## Two more rules

- **Honor deletions.** The loader removes deleted posts from every table, and landing files are removed after loading ([04](04-storage.md)).
- **Check Bluesky's developer terms** on bulk collection and redistribution before publishing any data, and note what you found alongside your methods.

## When reviewing accounts

Show the reviewer the evidence rows under an anonymous ID, not the handle. A behavioral call does not need to know who the person is, and knowing invites judging their politics.
