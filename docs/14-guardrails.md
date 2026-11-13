# 14 Guardrails

How the project's principles show up in the code on these pages. Use it as a checklist when you change something, and when you add a topic.

| Principle | Where it lives in code |
| --- | --- |
| Behavior, not opinions | Models label posts only ([07](07-classify.md)); the base instruction forbids judging the author, and it is in code, so no topic file can drop it. Signals ([10](10-signals.md)) read timing, age and duplicated text. Nothing in the signals service or the `flagged` view reads `labels`. |
| Test the hypothesis | Every chart has both series, all accounts and excluding flagged ([13](13-reports.md)). A small difference is a result. |
| Even-handed | One instruction and one threshold for every value of a dimension, including the tier 0 threshold ([08](08-escalating-labels.md)). Check errors in both directions when you hand-check labels. |
| Human review | The review service ([11](11-review.md)). Until accounts are reviewed, the excluded group is labeled "unreviewed". A person's label outranks every model's. |
| Evidence over verdicts | `signals.evidence` stores what was observed, such as a count or an age in days. |
| Anonymization | `anon_id` and `export_public` ([13](13-reports.md)). Reviewers see accounts under anonymous IDs ([11](11-review.md)). |
| No harassment pathways | No export has one row per ordinary account. Agent tools return aggregates only ([12](12-agent.md)). |
| Transparency | `labels` records the model, the topic's scheme version and the tier. Publish them with your error rates, and use pinned model names rather than `-latest` aliases ([16](16-choosing-models.md)). |
| Honest automation | `accounts.self_declared_bot`, shown as a separate series. |
| Data leaving the PC | Models receive post text and a position number only, never URIs, DIDs or handles ([07](07-classify.md)). Check each provider's data terms ([16](16-choosing-models.md)). |
| Honor deletions | One call, `store.delete_record`, removes a deleted post from every table, its vector included ([05](05-storage.md)). Landing files are removed after loading. |

## When you add a topic

A topic file decides what is collected and what a model is asked. These checks belong to it:

- **Does the label scheme describe posts, not people?** A dimension such as "is the author sincere" or "is this a bot" asks the model for something it has no evidence for. Do not add one.
- **Are the values even-handed?** If a dimension has a value for criticism, it needs one for support, and a neutral one. Give it an `unsure` value so the model has an honest way out.
- **Does the instruction take a side?** Read it as someone who disagrees with you would.
- **Who is in `accounts`?** Listing an account captures every reply to it and every quote of it. List public figures and outlets, not private individuals.
- **Change `labels.version`** whenever the instruction or the values change, so labels from two schemes are never mixed.

## Two more rules

- **Deletes at scale.** Removing a row is not always removing the bytes. [17](17-choosing-storage.md) says what each storage option does with a deleted post.
- **Check Bluesky's developer terms** on bulk collection and redistribution before publishing any data, and note what you found alongside your methods. Start with the [developer guidelines](https://bsky.network/docs/developer-guidelines), which require a way to delete content when a user asks, and the [terms of service](https://blueskyweb.xyz/support/tos) and [privacy policy](https://blueskyweb.xyz/support/privacy-policy) they point to.

## When reviewing accounts

Show the reviewer the evidence rows under an anonymous ID, not the handle. A behavioral call does not need to know who the person is, and knowing invites judging their politics. `pending_accounts` on [11](11-review.md) does this.
