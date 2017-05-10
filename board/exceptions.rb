#!/usr/bin/env ruby
#
# - without labels
# - without estimates
# - blocked

require 'trello'

Trello.configure do |config|
  config.developer_public_key = ENV['TRELLO_DEVELOPER_PUBLIC_KEY']
  config.member_token = ENV['TRELLO_MEMBER_TOKEN']
end

board_id = 'pwRFfOZj'
board = Trello::Board.find(board_id)

def no_estimates(lists)
  lists.map(&:cards).map {|cards|
    cards.reject {|c|
      c.name =~ /^\[(S|M|L|XL|2XL|EPIC)\]/
    }.reject {|c|
      c.name =~ /💥/ # Boom gates
    }.reject {|c|
      c.id == '58dc42fb4f07f4ca4059f807' # SLAB O' CHANGE
    }
  }.flatten
end

def no_labels(lists)
  lists.map(&:cards).map {|cards|
    cards.select {|c| c.labels.size == 0}
  }.flatten
end

def blocked(lists)
  lists.map(&:cards).map {|cards|
    cards.select {|c|
      c.labels.detect {|l| l.name == 'BLOCKED'}
    }
  }.flatten
end

lists = board.lists[0..3]

cards = no_estimates(lists)
if cards.size > 0 then
  puts
  puts "[info] There are #{cards.size} cards with no estimates"
  puts
  cards.each do |card|
    puts [ card.name, card.url ].join("\t")
  end
end

cards = no_labels(lists)
if cards.size > 0 then
  puts
  puts "[info] There are #{cards.size} cards with no labels"
  puts
  cards.each do |card|
    puts [ card.name, card.url ].join("\t")
  end
end

cards = blocked(lists)
if cards.size > 0 then
  puts
  puts "[info] There are #{cards.size} cards that are blocked"
  puts
  cards.each do |card|
    puts [ card.name, card.url ].join("\t")
  end
end


