$: << "./"
require "lib/common"
require "json"
require "optparse"

def subtract(purchased:, current:)
  purchased.each do |purchase|
    index = current.find_index { |item| item[:sku] == purchase[:sku] }
    next unless index
    current[index][:quantity] -= purchase[:quantity]
  end

  current.reject! { |item| item[:quantity] <= 0 }
end

def main
  options = {}
  OptionParser.new do |opt|
    opt.on("--from PATH_TO_ITEMS_JSON") { |o|
      if !File.exist?(o)
        puts "--from file not found: #{o}"
        exit(1)
      end
      options[:from_path] = o
    }
    opt.on("--purchased PATH_TO_ITEMS_JSON") { |o|
      if !File.exist?(o)
        puts "--purchased file not found: #{o}"
        exit(1)
      end
      options[:purchased_path] = o
    }
  end.parse!

  if !(options[:from_path] && options[:purchased_path])
    puts "Error: you need to provide --from and --purchased!"
    exit(1)
  end

  items = read_items(options[:from_path])
  purchased = read_items(options[:purchased_path])
  result = subtract(:purchased => purchased, current: items)

  puts JSON.pretty_generate(result)
end

main
