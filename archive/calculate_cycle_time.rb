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

lists = {
  start: List.find(name: 'Ready'),
  finish: List.find(name: 'DONE – Sprint 5')
}

cards = lists[:finish].cards
cards.select! { |c| c.attrs['name'] =~ /^\[[S|M|L|\d*XL]\]/ }
cards.each do |card|
  stream = card.labels.map { |l| l['name'] }.find { |name| name =~ /stream/i }
  estimate, title = card.name.split(' ', 2)
  estimate = estimate[1..-2]

  actions = card.actions.select { |a| a.type == 'updateCard' }

  cycle_start = actions.select do |a|
    a.data.dig('listBefore', 'id') == lists[:start].id
  end.sort_by(&:date).last
  cycle_end = actions.select do |a|
    a.data.dig('listAfter', 'id')  == lists[:finish].id
  end.sort_by(&:date).first

  entry = [card.id, stream, estimate, title]

  next unless cycle_start && cycle_end # skip cards created in Doing and Review

  cycle_seconds = cycle_end.date - cycle_start.date
  cycle_seconds -= 2.days.to_i if weekends?(cycle_start.date..cycle_end.date)
  entry << cycle_seconds
  puts entry.join("\t")
end
