#!/usr/bin/env ruby

require 'trello'

Trello.configure do |config|
  config.developer_public_key = ENV['TRELLO_DEVELOPER_PUBLIC_KEY']
  config.member_token = ENV['TRELLO_MEMBER_TOKEN']
end

board_id = 'NwUJAqdJ'
board = Trello::Board.find(board_id)

cards = board.lists.last.cards
cards.each do |card|
  stream = card.labels.map(&:name).find{|name| name =~ /stream/i}
  estimate, title = card.name.split(' ', 2)

  puts [ stream, estimate[1..-2], title ].join("\t")
end
