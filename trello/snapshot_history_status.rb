#!/usr/bin/env ruby

require 'trello'

Trello.configure do |config|
  config.developer_public_key = ENV['TRELLO_DEVELOPER_PUBLIC_KEY']
  config.member_token = ENV['TRELLO_MEMBER_TOKEN']
end

board_id = 'JmHJwCF0'
board = Trello::Board.find(board_id)

sprints = board.lists.select {|list| list.name =~ /sprint/i}

sprints.each do |sprint|
  puts "# #{sprint.name}"
  names = sprint.cards.map(&:name)
  names.select! {|n| n =~ / \[.*[A-Z]\]/ }
  names.each do |name|
    stream, estimate, title = name.split(' ', 3)
    puts [ stream[1..-2], estimate[1..-2], title ].join("\t")
  end
  puts
end
