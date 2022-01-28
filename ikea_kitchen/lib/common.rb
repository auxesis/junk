require "json"

def dedup_items(items_with_dupes)
  mapping = {}
  items_with_dupes.each do |item|
    sku = item[:sku]
    mapping[sku] ||= { quantity: 0, name: item[:name] }
    mapping[sku][:quantity] += item[:quantity].to_i
  end

  mapping.map { |k, v| { sku: k }.merge(v) }
end

def read_items(filename)
  file = File.read(filename)
  items_with_dupes = JSON.parse(file, symbolize_names: true)
  dedup_items(items_with_dupes)
end

def ikeaify_sku(sku)
  "#{sku[0..2]}.#{sku[3..5]}.#{sku[6..7]}"
end
