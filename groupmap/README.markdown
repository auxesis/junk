# Groupmap tools

## `extract_actions_from_csv.rb`

Steps:

1. Open up the Groupmap in your browser
1. Click to the _Results_ tab
1. Click the _View Reports_ button
1. Click to the _Action tab_
1. Export the actions as CSV

Run with no arguments to read from stdin:

```
cat ~/path/to/actions.csv | bundle exec ruby extract_actions_from_groupmap_csv.rb
```

Run with filename argument:

```
ruby extract_actions_from_groupmap_csv.rb path/to/actions.csv
```

## `extract_actions_from_groupmap_page_source.rb`

Steps:

1. Open up the Groupmap in your browser
2. View the source of the page
3. Select and copy all selected text to your clipboard

Run with no arguments to read from stdin:

```
pbpaste | bundle exec ruby extract_actions_from_groupmap_page_source.rb
```

Run with filename argument:

```
ruby extract_actions_from_groupmap_page_source.rb path/to/retro.html
```
