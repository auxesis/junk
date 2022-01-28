$: << "./"
require "lib/common"
require "scraperwiki"
require "json"

def main
  stores = {}
  by_sku = ScraperWiki.select("* from data").group_by { |r| r["sku"] }
  items = read_items("items.json")

  puts "Low stock for the following items:\n\n"
  items.each do |item|
    total = by_sku[item[:sku]].map { |stock| stock["quantity"] }.sum
    if (1..10).include?(total)
      available_stores = by_sku[item[:sku]].select { |s| s["quantity"] > 0 }.map { |s| s["store"] }
      puts "#{ikeaify_sku(item[:sku])} (#{item[:name]}): want #{item[:quantity]} but only #{total} available (at #{available_stores.join(", ")})"
    end
  end
end

main
