# Answer an author's reply in its thread, even though posting stops being atomic

When the context filter keeps a finding because the code shows the author's answer is wrong, pr-review posts it as a reply in the author's thread, not as a new inline comment. GitHub's create-review call cannot reply to a thread, so a run now posts one review and then each reply with its own call. Posting is no longer all-or-nothing.

We accepted that because a reply beside the answer it disputes is where the author will read it; a new comment elsewhere in the diff splits one conversation in two. To contain the cost, the review posts first and no reply posts if it fails; a failed reply does not stop the others; the saved payload file keeps only the parts that did not post, and the retry hint prints one command for each, so a retry never posts twice. Replies have their own cap of 3, separate from the 8 inline comments.

GitHub only has threads for review comments. When the answer is an issue comment or a review body, there is nothing to reply to, so the finding is posted as a new inline comment that links to the answer.

## Considered options

- **Always a new inline comment that quotes and links the answer.** Kept posting atomic, but splits the conversation.
