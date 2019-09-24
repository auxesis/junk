# GitHub automation

Small tools for doing repetitive tasks on GitHub.

## Setup

```
git clone https://github.com/auxesis/junk
cd junk/github
bundle
alias be="bundle exec"
```

## Tools

### `ignore-github-org.rb`

Ignore all notifications for a specified GitHub organisation:

```
be ruby ignore-github-org.rb ausdto
```

### `grant-maintainer-access-to-github-repos.rb`

Grant the `maintain` [level of access](https://help.github.com/en/articles/repository-permission-levels-for-an-organization#repository-access-for-each-permission-level) to an org's GitHub repos.

```
be ruby grant-maintainer-access-to-github-repos.rb section-io auxesis
```
