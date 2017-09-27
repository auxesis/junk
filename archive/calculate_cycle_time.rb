# frozen-string-literal: true

require_relative('lib/data')
require 'active_support'
require 'active_support/core_ext/numeric'
require 'dotenv'
Dotenv.load

def weekends?(range)
  range = (range.first.to_date..range.last.to_date) if range.first.is_a?(Time)
  range.reject { |d| (1..5).cover?(d.wday) }.size.positive?
end

def lists
  {
    start: List.find(name: 'Ready'),
    finish: List.find(name: Options.finish_list_name)
  }
end

def extract_card_estimates(card)
  stream = card.labels.map { |l| l['name'] }.find { |name| name =~ /stream/i }
  estimate, title = card.name.split(' ', 2)
  estimate = estimate[1..-2]
  [stream, estimate, title]
end

def find_cycle_start(actions)
  actions.select do |a|
    a.data.dig('listBefore', 'id') == lists[:start].id
  end.sort_by(&:date).last
end

def find_cycle_end(actions)
  actions.select do |a|
    a.data.dig('listAfter', 'id') == lists[:finish].id
  end.sort_by(&:date).first
end

def print_cycle_time(record:, cycle_start:, cycle_end:)
  return unless cycle_start && cycle_end
  cycle_seconds = cycle_end.date - cycle_start.date
  cycle_seconds -= 2.days.to_i if weekends?(cycle_start.date..cycle_end.date)
  record << cycle_seconds
  puts record.join("\t")
end

def calculate_and_print_cycle_time(card)
  stream, estimate, title = extract_card_estimates(card)

  actions = card.actions.select { |a| a.type == 'updateCard' }
  cycle_start = find_cycle_start(actions)
  cycle_end = find_cycle_end(actions)

  record = [card.id, stream, estimate, title]
  # skip cards created in Doing and Review
  print_cycle_time(record: record, cycle_start: cycle_start, cycle_end: cycle_end)
end

Options = OpenStruct.new(finish_list_name: 'DONE')

# rubocop:disable Metrics/MethodLength
def parse_options!
  require 'optparse'
  OptionParser.new do |opts|
    opts.banner = "Usage: #{$PROGRAM_NAME} [options]"
    opts.on('-f', '--finish=NAME', 'Name of finish column') do |name|
      Options.finish_list_name = name
      raise ArgumentError, "Error: --finish - Unknown list: #{name}" unless lists[:finish]
    end
  end.parse!
rescue ArgumentError => e
  puts e.message
  exit(1)
end
# rubocop:enable Metrics/MethodLength

def main
  parse_options!
  cards = lists[:finish].cards.select { |c| c.attrs['name'] =~ /^\[[S|M|L|\d*XL]\]/ }
  cards.each { |card| calculate_and_print_cycle_time(card) }
end

main if $PROGRAM_NAME == __FILE__
