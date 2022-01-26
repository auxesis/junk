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
    mapping[sku][:quantity] += 1
  end
  @items = mapping.map { |k, v| { sku: k }.merge(v) }
end

def main
  stores = {}
  by_sku = ScraperWiki.select("* from data").group_by { |r| r["sku"] }

  items.each do |item|
    most = by_sku[item[:sku]].sort_by { |stock| stock["quantity"] }.last
    stores[most["store"]] ||= []
    stores[most["store"]] << item
    if most["quantity"].to_i < item[:quantity].to_i
      puts "WARNING: #{most["store"]} does not have enough stock (#{most["quantity"]} / #{item[:quantity]}) for #{item[:sku]}"
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
