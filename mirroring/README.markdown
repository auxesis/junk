# Mirroring

A collection of scripts to test the hypothesis that:

> _PRs get feedback from people in the same stream as the PR creator._

## Setup

Clone and set up the repo:

```
git clone https://github.com/auxesis/junk.git
cd junk/mirroring
bundle
```

Add a `.env` with a GitHub Personal Access Token:

``` bash
# Your GitHub Personal Access Token that grants you access to the repos
GITHUB_TOKEN=b1946ac92492d2347c6235b4d2611184b1946ac9
# The repos you want to scrape the PRs from
TARGET_REPOS=org/repo,org/repo2
# The date you want to scrape PRs from
TARGET_SINCE=2017-01-01
```

This separates your credentials from the app, and helps you debug more easily.

## Usage

Scrape the target repos by running:

```
time bundle exec ruby scraper.rb
```

Run the `pr_stats.rb` script to print a report:

```
bundle exec ruby pr_stats.rb
```

This is pastable into [the spreadsheet](https://docs.google.com/spreadsheets/d/1LfRzc4AJ1hSdnsGoIq0ymgeMK6YWfV3JHq0c_E9onTw/edit#gid=0) to see visualisations.
