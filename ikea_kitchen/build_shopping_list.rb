require "scraperwiki"
require "json"

def items
  return @items if @items
  file = File.read("items.json")
  items_with_dupes = JSON.parse(file, symbolize_names: true)

  # de-dupe
  mapping = {}
  items_with_dupes.each do |item|
    sku = item[:sku]
    mapping[sku] ||= { quantity: 0, name: item[:name] }
    mapping[sku][:quantity] += item[:quantity].to_i
  end
  @items = mapping.map { |k, v| { sku: k }.merge(v) }
end

def main
  stores = {}
  by_sku = ScraperWiki.select("* from data").group_by { |r| r["sku"] }

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

  stores.each do |name, items|
    puts "### #{name} ###\n\n"
    items.sort_by { |item| item[:quantity] }.reverse.each do |item|
      puts "#{item[:quantity]}x #{item[:sku][0..2]}.#{item[:sku][3..5]}.#{item[:sku][6..7]} — #{item[:name]}"
    end
    puts
  end
end

main
