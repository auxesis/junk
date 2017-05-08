#!/usr/bin/env ruby

require 'trello'
require 'pry'

def has_weekends?(range)
  range = (range.first.to_date..range.last.to_date) if range.first.is_a?(Time)
  range.select { |d| !(1..5).include?(d.wday) }.size > 0
end

Trello.configure do |config|
  config.developer_public_key = ENV['TRELLO_DEVELOPER_PUBLIC_KEY']
  config.member_token = ENV['TRELLO_MEMBER_TOKEN']
end

board_id = 'pwRFfOZj'
board = Trello::Board.find(board_id)

puts
puts "DONE"
cards = board.lists.last.cards
cards.select! {|c| c.name =~ / \[.*[A-Z]\]/ }
cards.each do |card|
  stream, estimate, title = card.name.split(' ', 3)

  actions = Trello::Action.from_response(Trello.client.get("/cards/#{card.id}/actions", filter: 'updateCard:idList'))
  cycle_start = actions.select {|a| a.data['listBefore']['id'] == board.lists.first.id}.sort_by(&:date).last
  cycle_end   = actions.select {|a| a.data['listAfter']['id']  == board.lists.last.id}.sort_by(&:date).first

  entry = [ stream[1..-2], estimate[1..-2], title ]

  if cycle_start && cycle_end # cards created in Doing and Review
    cycle_seconds = cycle_end.date - cycle_start.date
    cycle_seconds -= 2.days.to_i if has_weekends?(cycle_start.date..cycle_end.date)
    cycle_hours = cycle_seconds / 3600
    entry << cycle_seconds
  end

  puts entry.join("\t")
end

