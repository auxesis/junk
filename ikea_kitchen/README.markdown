# IKEA Kitchen stock scraper

## Build a list of items to purchase

1. Use the IKEA Kitchen Planner to build desired kitchen.
1. Click "view item list" in bottom right corner.
1. Open up console, and run this:
   ``` javascript
   var skus = $$('td.table_item_sku').map((td) => { return td.innerHTML })
   var quantities = $$('td.table_item_quantity').map((td) => { return td.innerHTML })

   var items = skus.map((e,i) => { return { sku: e, quantity: quantities[i] } })
   copy(items)
   ```
1. Then run `pbpaste | tee items.json` to write items to `items.json`

## Scrape stock quantities

Ensure you've run a `bundle install`, then run:

``` bash
bundle exec ruby scrape-stock.rb
```

This scrapes and saves store stock quantities to `data.sqlite`.
