# IKEA Kitchen stock scraper and shopping list builder

You want to buy an IKEA kitchen, but you can't buy all the parts from a single store?

Don't spend your nights trying to build a shopping list based on opaque stock levels on the IKEA website.

Use these tools to build a shopping list for all the IKEA stores in your area, based on available stock levels.

## Build a list of items to purchase

1. Use the IKEA Kitchen Planner to build desired kitchen.
1. Click "view item list" in bottom right corner.
1. Open up console, and run this:
   ``` javascript
   var skus = $$('div.selenium-itemList-articleNumber-value').map((div) => { return div.innerHTML.replaceAll(".", "") })
   var quantities = $$('div.selenium-itemList-quantity-value').map((div) => { return parseInt(div.innerText) })
   var prices = $$('div.selenium-itemList-listPrice-value').map((div) => { return div.innerText })
   var names = $$('div.selenium-item-info').map((div) => { return div.innerText })

   var items = skus.map((e,i) => { return { sku: e, quantity: quantities[i], name: names[i], price: prices[i] } })
   copy(items)
   ```
1. Then run `pbpaste | tee items.json` to write items to `items.json`

The JSON should look like this:

```
[
    {
        "sku": "10270893",
        "quantity": "1",
        "name": "METOD base cabinet frame, white, 80x60x80 cm"
    },
    {
        "sku": "50397574",
        "quantity": "2",
        "name": "VOXTORP drawer front, high-gloss white, 80x10 cm"
    },
    ...
]
```

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

You can specify stores to shop at with the `--allow-stores` option:

``` bash
bundle exec ruby build_shopping_list.rb --stores="Marsden Park,Tempe"
```

By default, it will build a shopping list for all stores in Sydney.

## Find items about to go out of stock

To see what items you want to buy that have low stock, run:

``` bash
bundle exec ruby find_urgent_items.rb
```

This will print out:

- Any items with < 5 stock within NSW
- What stores you can find them at

## Updating the shopping list after you've made a purchase

Sometimes you need to update the shopping list after you've purchased some of the items.

There's a helper tool for that:

```
bundle exec subtract_purchased_from_desired_items.rb --from items.json --purchased purchased.json
```

This will output a new JSON data structure with purchased quantities subtracted from the original items.

Save it by piping it to `items.json`.
