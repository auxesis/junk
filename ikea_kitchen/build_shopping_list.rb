$: << "./"
require "lib/common"
require "scraperwiki"
require "json"
require "optparse"

def select_stock(stock:, items:, allow_stores:)
  stores = {}
  stock.select! { |stock| allow_stores.include?(stock["store"]) }
  by_sku = stock.group_by { |r| r["sku"] }

  if by_sku.size.zero?
    puts "No available stock at #{allow_stores.size} stores"
    exit(1)
  end

  items.each do |item|
    total = by_sku[item[:sku]].map { |stock| stock["quantity"] }.sum
    most = by_sku[item[:sku]].sort_by { |stock| stock["quantity"] }.last
    required = item[:quantity].to_i
    stores[most["store"]] ||= []

    case
    when total == 0 # No stock at all
      puts "WARNING: There is no stock available for #{item[:sku]} (#{item[:name]})"
    when total < required # Insufficient total stock
      puts "WARNING: There is insufficient stock available (#{total} / #{item[:quantity]}) for #{item[:sku]} (#{item[:name]})"
    when most["quantity"] < required && total >= required # Stock spread across multiple locations
      acquired = 0
      by_sku[item[:sku]].sort_by { |stock| stock["quantity"] }.each { |stock|
        if acquired + stock["quantity"] > required # So we don't add more than needed at a store
          sub_quantity = required - acquired
          stores[stock["store"]] << item.merge({ quantity: sub_quantity })
          acquired += sub_quantity
        else # Or just add the exact amount
          stores[stock["store"]] << item.merge({ quantity: stock["quantity"] })
          acquired += stock["quantity"]
        end
        break if acquired >= required
      }
    else # All required stock available at single store
      stores[most["store"]] << item
    end
  end
  puts

  return stores
end

def main
  options = {
    allow_stores: ["Marsden Park", "Rhodes", "Tempe"],
    items_path: "items.json",
  }
  OptionParser.new do |opt|
    opt.on("--stores COMMA,SEPARATED,STORES") { |o| options[:allow_stores] = o.split(",") }
    opt.on("--items PATH_TO_ITEMS_JSON") { |o|
      if !File.exists?(o)
        puts "File not found: #{o}"
        exit(1)
      end
      options[:items_path] = o
    }
  end.parse!

  stock = ScraperWiki.select("* FROM data")
  items = read_items(options[:items_path])
  shopping_list = select_stock(stock: stock, items: items, allow_stores: options[:allow_stores])

  shopping_list.each do |store_name, items|
    puts "### #{store_name} ###\n\n"
    items.sort_by { |item| item[:quantity] }.reverse.each do |item|
      puts ikeaify_sku(item[:sku])
      puts item[:name]
      puts "Need #{item[:quantity]}"
      puts
    end
  end
end

main
