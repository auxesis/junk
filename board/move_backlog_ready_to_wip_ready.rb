#!/usr/bin/env ruby

require 'trello'

Trello.configure do |config|
  config.developer_public_key = ENV['TRELLO_DEVELOPER_PUBLIC_KEY']
  config.member_token = ENV['TRELLO_MEMBER_TOKEN']
end

board_ids = {
  :backlog => 'NwUJAqdJ',
  :wip     => 'pwRFfOZj',
}

board = Trello::Board.find(board_ids[:backlog])
readies = board.lists.select {|list| list.name =~ /Ready$/}

wip_board = Trello::Board.find(board_ids[:wip])
wip_target = wip_board.lists.find {|list| list.name == 'Ready'}

readies.each do |list|
  list.cards.each_with_index do |card, index|
    puts "[info] Moving '#{card.name}' (#{card.id}) to '#{wip_target.name}' (#{wip_target.id}) on '#{wip_board.name}' (#{wip_board.id})"
    card.move_to_board(wip_board, wip_target)
    # Move the cards to the top of the board (may only want to do this for some streams, some of the time)
    #card.pos = 'top'
    #card.save
  end
end
