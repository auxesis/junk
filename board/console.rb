#!/usr/bin/env ruby

require 'trello'
require 'pry'
require 'dotenv'
Dotenv.load

Trello.configure do |config|
  config.developer_public_key = ENV['TRELLO_DEVELOPER_PUBLIC_KEY']
  config.member_token = ENV['TRELLO_MEMBER_TOKEN']
end

board_ids = {
  backlog: 'NwUJAqdJ',
  wip: 'pwRFfOZj',
}

Pry.config.prompt_name = 'trello'
Pry.config.should_load_rc = false
Pry.config.history.should_save = true
Pry.config.history.should_load = true

backlog = Trello::Board.find(board_ids[:backlog])
wip = Trello::Board.find(board_ids[:wip])

puts "Two boards available: backlog + wip"

binding.pry quiet: true
