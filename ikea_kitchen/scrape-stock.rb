require "scraperwiki"
require "faraday"
require "json"

def fetch(sku)
  url = "https://api.ingka.ikea.com/cia/availabilities/ru/au?itemNos=#{sku}&expand=StoresList,Restocks,SalesLocations"
  params = nil
  headers = { "x-client-id" => "b6c117e5-ae61-4ef5-b4cc-e0b1e37f0631" }
  response = Faraday.get(url, params, headers)
  return JSON.parse(response.body, symbolize_names: true)
end

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

def filter_to_stores(json)
  json[:data].select { |d| STORES.keys.include?(d[:classUnitKey][:classUnitCode]) }
end

def extract_store_quantity(store)
  {
    sku: store[:itemKey][:itemNo],
    quantity: store[:availableStocks].find { |s| s[:type] == "CASHCARRY" }[:quantity],
    store: STORES[store[:classUnitKey][:classUnitCode]],
  }
end

STORES = {
  "377" => "Marsden Park",
  "385" => "Rhodes",
  "446" => "Tempe",
}

def main
  stocks = []

  items.each_with_index do |item, index|
    puts "Scraping #{item[:sku]}..."
    json = fetch(item[:sku])
    nearby = filter_to_stores(json)
    nearby.each do |store|
      stocks << extract_store_quantity(store).merge({ name: item[:name] })
    end
  end

  puts "Saving #{stocks.size} stock records..."
  ScraperWiki.save_sqlite([:sku, :store], stocks)

  puts "DONE"
end

main()
