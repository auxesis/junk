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

def ikeaify_sku(sku)
  "#{sku[0..2]}.#{sku[3..5]}.#{sku[6..7]}"
end

def main
  stores = {}
  by_sku = ScraperWiki.select("* from data").group_by { |r| r["sku"] }

  puts "Low stock for the following items:\n\n"
  items.each do |item|
    total = by_sku[item[:sku]].map { |stock| stock["quantity"] }.sum
    if (1..5).include?(total)
      available_stores = by_sku[item[:sku]].select { |s| s["quantity"] > 0 }.map { |s| s["store"] }
      puts "#{ikeaify_sku(item[:sku])} (#{item[:name]}): want #{item[:quantity]} but only #{total} available (at #{available_stores.join(", ")})"
    end
  end
end

main
