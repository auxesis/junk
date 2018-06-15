# Groupmap tools

## `extract_actions_from_groupmap_page_source.rb`

Steps:

1. Open up the Groupmap in your browser
2. View the source of the page
3. Select and copy all selected text to your clipboard

Run with no arguments to read from stdin:

```
pbpaste | ruby extract_actions_from_groupmap_page_source.rb
```

Run with filename argument:

```
ruby extract_actions_from_groupmap_page_source.rb path/to/retro.html
```
