# Plain language: rewrite only blocking problems, and post the rest

Every comment is checked for plain language (ISO 24495-1, with sentence rules from ASD-STE100) by a word-and-shape check in code and by a model reader test. Only a blocking problem triggers a rewrite, there is one rewrite pass, and a comment that still has problems after it is posted with those problems listed on stderr.

A spike over 60 posted comments (2026-09-24) found that 59 failed the code check and the reader flagged at least one phrase in all 60. One rewrite halved the flags, but only 7 comments came back with none. Blocking the post on any flag would stop almost every review; rewriting on minor flags would send nearly every comment for rewrite, and the spike's rewrite made comments 23% longer. The same spike showed the problem starts in the reviewer prompts, so the writing rules go into every review-type and synthesis prompt first, and this check is the safety net behind them.

## Considered options

- **Rules in the prompt only.** Rejected: in an earlier project, writing rules stopped being followed once only a prompt enforced them.
- **Block posting until clean.** Rejected: on the spike's data, nearly nothing would post.
- **Rewrite on every problem.** Rejected: most minor flags survived a rewrite anyway.
