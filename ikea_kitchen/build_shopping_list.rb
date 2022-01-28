require "scraperwiki"
require "json"
require "optparse"

def inventory(filename)
  file = File.read(filename)
  items_with_dupes = JSON.parse(file, symbolize_names: true)

  # de-dupe
  mapping = {}
  items_with_dupes.each do |item|
    sku = item[:sku]
    mapping[sku] ||= { quantity: 0, name: item[:name] }
    mapping[sku][:quantity] += item[:quantity].to_i
  end

  mapping.map { |k, v| { sku: k }.merge(v) }
end

def items
  return @items if @items
  items = inventory("items.json")
  purchased = inventory("purchased.json")

  purchased.each do |purchase|
    index = items.find_index { |item| item[:sku] == purchase[:sku] }
    items[index][:quantity] -= purchase[:quantity]
  end

  items.reject! { |item| item[:quantity] <= 0 }

  @items = items
end

def ikeaify_sku(sku)
  "#{sku[0..2]}.#{sku[3..5]}.#{sku[6..7]}"
end

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
  options = { allow_stores: [] }
  OptionParser.new do |opt|
    opt.on("--allow-stores COMMA,SEPARATED,STORES") { |o| options[:allow_stores] = o.split(",") }
  end.parse!

  stock = ScraperWiki.select("* FROM data")
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
