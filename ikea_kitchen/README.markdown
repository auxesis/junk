# IKEA Kitchen stock scraper

## Build a list of items to purchase

1. Use the IKEA Kitchen Planner to build desired kitchen.
1. Click "view item list" in bottom right corner.
1. Open up console, and run this:
   ``` javascript
   var skus = $$('td.table_item_sku').map((td) => { return td.innerHTML })
   var quantities = $$('td.table_item_quantity').map((td) => { return td.innerHTML })
   var names = $$('td.table_item_longname').map((td) => { return td.innerText.replace(/\n/g, ', ') })

   var items = skus.map((e,i) => { return { sku: e, quantity: quantities[i], name: names[i] } })
   copy(items)
   ```
1. Then run `pbpaste | tee items.json` to write items to `items.json`

## Scrape stock quantities

Ensure you've run a `bundle install`, then run:

``` bash
bundle exec ruby scrape-stock.rb
```

This scrapes and saves store stock quantities to `data.sqlite`.

## Build a shopping list

To output a shopping list based on stock levels and your desired kitchen design, run:

``` bash
bundle exec ruby build_shopping_list.rb
```

When building a shopping list, it will:

- Prefer store locations that have the most of an item in stock
- Split items across multiple stores if the required item quantity can't be fulfilled at a single store
- Print a warning if it's unable to find enough stock of an item
- Only use store locations for New South Wales

## Find items about to go out of stock

To see what items you want to buy that have low stock, run:

``` bash
bundle exec ruby find_urgent_items.rb
```

This will print out:

- Any items with < 5 stock within NSW
- What stores you can find them at
