#!/usr/bin/env ruby

require 'trello'
require 'pry'

Trello.configure do |config|
  config.developer_public_key = ENV['TRELLO_DEVELOPER_PUBLIC_KEY']
  config.member_token = ENV['TRELLO_MEMBER_TOKEN']
end

board_ids = {
  :honeybadgers => 'ShQ7cdAi',
  :backlog => 'NwUJAqdJ',
}

board = Trello::Board.find(board_ids[:honeybadgers])
incoming = board.lists.find {|list| list.name =~ /Elements Work/}

backlog_board = Trello::Board.find(board_ids[:backlog])
backlog_target = backlog_board.lists.find {|list| list.name == 'Stream 0 (BAU) - Planning'}

incoming.cards.reverse.each do |card|
  puts "[info] Moving '#{card.name}' (#{card.id}) to '#{backlog_target.name}' (#{backlog_target.id}) on '#{backlog_board.name}' (#{backlog_board.id})"
  card.move_to_board(backlog_board, backlog_target)
end
