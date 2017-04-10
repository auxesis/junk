# board

Tools to manage the Elements Trello board.

Remember, work flows through the boards like this:

```


    +-----------+      +----+----+      +-----------+
    |           |      |         |      |           |
    |  Backlog  +------+   WIP   +------+  History  |
    |           |      |         |      |           |
    +-----------+      +----+----+      +-----------+


```

## Setup

`git clone` this repo, and run a `bundle install` to pull down the dependencies.

Then add a `run.sh` wrapper script with your Trello developer public key, and member token:

``` bash
# run.sh
export TRELLO_DEVELOPER_PUBLIC_KEY='b1946ac92492d2347c6235b4d2611184'
export TRELLO_MEMBER_TOKEN='591785b794601e212b260e25925636fd'

bundle exec ruby -rpry $@
```

Now you can run any of these helper scripts in this repo:

```
sh -x run.sh move_backlog_ready_to_wip_ready.rb
```

This separates your credentials, and helps you debug more easily.

## `move_backlog_ready_to_wip_ready.rb`

**This script DOES modify the board.**

On the backlog board, there are three columns per stream:

 - _Inbox_ is new work that hasn't been triaged, defined, and sized
 - _Planning_ is new work that we are in the process of triaging, defining, and sizing
 - _Ready_ is new work that has been triaged, defined, and sized for the next sprint

New work lands in _Inbox_ throughout the sprint. Work is pulled into _Planning_ during fortnightly backlog grooming. Work is pulled into _Ready_ during fortnightly sprint planning.

This script moves any cards from the _Ready_ columns for each stream on the backlog board, into _Ready_ column on the WIP board.

## `snapshot_board_status.rb`

**This script DOES NOT modify the board.**

Prints a summary of the _Ready_ and _DONE_ columns on the WIP board.

It expects cards to be consistently named on the board in this format:

```
[STREAM] [SIZE] Name
```

For example:

```
[BAU] [S] New transactional mailing list
```

Running this script filters down to cards matching this format, and outputs them in a tab separated value format suitable to feeding into Google Sheets.

```
<Stream>  <T-shirt size>  <Name>
```

For example:

```
Media   EPIC    Item page
BAU     S       New transactional mailing list
BAU     S       Rework content in existing transactional mailings
```

## `snapshot_history_status.rb`

**This script DOES NOT modify the board.**

Prints a summary of all the DONE lists matching `/sprint/i` on the History board (it should only return lists since we started the new way of working).

Useful for feeding into broader analysis spreadsheets.
