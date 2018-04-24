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
  history: 'JmHJwCF0',
}

wip = Trello::Board.find(board_ids[:wip])

people = {}

last_sprint = wip.lists.select { |l| l.name =~ /DONE/ }[1]
last_sprint.cards.each do |card|
  card.members.each do |member|
    name = member.full_name
    people[name] ||= []
    people[name] << card
  end
end

people = Hash[people.sort_by {|name, cards| name }]

people.each do |name, cards|
  cards.sort_by(&:name).each do |card|
    puts [name,card.name].join("\t")
  end
end
