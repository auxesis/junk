#!/usr/bin/env ruby

require 'trello'
require 'pry'
require 'dotenv'
Dotenv.load

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

lists = {
  :start  => board.lists.find {|l| l.name =~ /^ready$/i},
  :finish => board.lists.find {|l| l.name =~ /^done$/i},
}

cards = lists[:finish].cards
cards.select! {|c| c.name =~ /^\[[S|M|L|\d*XL]\]/ }
cards.each do |card|
  stream = card.labels.map(&:name).find{|name| name =~ /stream/i}
  estimate, title = card.name.split(' ', 2)
  estimate = estimate[1..-2]

  actions = Trello::Action.from_response(Trello.client.get("/cards/#{card.id}/actions", filter: 'updateCard:idList'))

  cycle_start = actions.select {|a| a.data['listBefore']['id'] == lists[:start].id}.sort_by(&:date).last
  cycle_end   = actions.select {|a| a.data['listAfter']['id']  == lists[:finish].id}.sort_by(&:date).first

  entry = [ card.id, stream, estimate, title ]

  if cycle_start && cycle_end # cards created in Doing and Review
    cycle_seconds = cycle_end.date - cycle_start.date
    cycle_seconds -= 2.days.to_i if has_weekends?(cycle_start.date..cycle_end.date)
    cycle_hours = cycle_seconds / 3600
    entry << cycle_seconds
    puts entry.join("\t")
  end
end
