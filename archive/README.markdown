# The archive

Tools to report the Elements Trello board.

Remember, work flows through the boards like this:

```


    +-----------+      +----+----+      +-----------+
    |           |      |         |      |           |
    |  Backlog  +------+   WIP   +------+  History  |
    |           |      |         |      |           |
    +-----------+      +----+----+      +-----------+


```

## Setup

Clone and set up the repo:

```
git clone https://github.com/auxesis/junk.git
cd junk/archive
bundle
```

Add a `.env` with your Trello developer public key + member token:

``` bash
TRELLO_DEVELOPER_PUBLIC_KEY='b1946ac92492d2347c6235b4d2611184'
TRELLO_MEMBER_TOKEN='591785b794601e212b260e25925636fd'
```

Run any of the scripts in this repo:

```
bundle exec ruby snapshot_board.rb
```

This separates your credentials, and helps you debug more easily.

## `snapshot_board.rb`

✅ **This script DOES NOT modify the board.**

Scrapes all the lists, cards, and card actions on the WIP board.

Stores the scraped data in `data.sqlite`, for querying later with `calculate_cycle_time.rb`.

Takes 5-10 minutes to run.

## `calculate_cycle_time.rb`

✅ **This script DOES NOT modify the board.**

Calculates the cycle time for cards going from Ready -> DONE on the WIP board.

It expects cards to have a _Stream 0_ or _Stream 1_ label, and be named in this format:

```
[SIZE] Name
```

You can specify an alternate list to measure with the `--finish` option:

```
bundle exec ruby calculate_cycle_time.rb --finish 'DONE – Sprint 4'
```
