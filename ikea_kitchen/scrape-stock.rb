$: << "./"
require "lib/common"
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

def filter_to_stores(json)
  json[:data].select { |d| STORES.keys.include?(d[:classUnitKey][:classUnitCode]) }
end

def extract_store_quantity(store)
  {
    sku: store[:itemKey][:itemNo],
    quantity: store[:isInCashAndCarryRange] ? store[:availableStocks].find { |s| s[:type] == "CASHCARRY" }[:quantity] : 0,
    store: STORES[store[:classUnitKey][:classUnitCode]],
  }
end

STORES = {
  "451" => "Canberra",
  "919" => "Logan",
  "556" => "Perth",
  "557" => "Adelaide",
  "377" => "Marsden Park",
  "385" => "Rhodes",
  "446" => "Tempe",
  "460" => "North Lakes",
  "384" => "Richmond",
  "006" => "Springvale",
}

def main
  stocks = []

  items_path = ARGV.first || "items.json"

  items = read_items(items_path)

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
