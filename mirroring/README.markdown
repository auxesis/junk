A collection of scripts to test the hypothesis that:

> _PRs get feedback from people in the same stream as the PR creator._

[Spreadsheet scratch pad](https://docs.google.com/spreadsheets/d/1LfRzc4AJ1hSdnsGoIq0ymgeMK6YWfV3JHq0c_E9onTw/edit#gid=0)

## Setup

Clone and set up the repo:

```
git clone https://github.com/auxesis/junk.git
cd junk/mirroring
bundle
```

Add a `.env` with a GitHub Personal Access Token:

``` bash
GITHUB_TOKEN=b1946ac92492d2347c6235b4d2611184b1946ac9
```

This separates your credentials, and helps you debug more easily.

## Usage

Run the `pr_stats.rb` script to scrape and print a report:

```
bundle exec ruby pr_stats.rb
```
