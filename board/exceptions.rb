#!/usr/bin/env ruby
#
# - without labels
# - without estimates
# - blocked

require 'slack-notifier'
require 'trello'
require 'rufus-scheduler'
require 'dotenv'
Dotenv.load

Trello.configure do |config|
  config.developer_public_key = ENV['TRELLO_DEVELOPER_PUBLIC_KEY']
  config.member_token = ENV['TRELLO_MEMBER_TOKEN']
end

def post(message, opts={})
  webhook_url = ENV['SLACK_WEBHOOK_URL']
  options = {
    channel: '#elements-cust-eng',
    username: 'Trello',
    icon_url: 'https://emoji.slack-edge.com/T0253B9P9/trello/f5e87fbfb84cba43.png'
  }.merge(opts)

  notifier = Slack::Notifier.new(webhook_url, options)
  notifier.ping(message)
end

def no_estimates(lists)
  lists.map(&:cards).map {|cards|
    cards.reject {|c|
      c.name =~ /^\[(XS|S|M|L|XL|2XL|EPIC)\]/
    }.reject {|c|
      c.name =~ /💥/ # Boom gates
    }.reject {|c|
      c.id == '58dc42fb4f07f4ca4059f807' # SLAB O' CHANGE
    }.reject {|c|
      c.id == '5934a926c6f8b682ebcceb5f' # Line of public 1% launch
    }.reject {|c|
      c.name =~ /^\[\?\]/ && c.list.name == 'Ready'
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

def format_cards(cards:, header:)
  message = [ header, '' ]
  cards.each do |card|
    message << ":trello: <#{card.url}|#{card.name}>"
  end
  message << ''
  message.join("\n")
end

def notify_problems!
  board_id = 'pwRFfOZj'
  board = Trello::Board.find(board_id)

  lists = board.lists[0..3]

  cards = no_estimates(lists)
  if cards.size > 0 then
    puts "[info] There are #{cards.size} cards with no estimates"
    header = ':warning::clock4: *Cards with no estimates*'
    message = format_cards(cards: cards, header: header)
    post(message)
  end

  cards = no_labels(lists)
  if cards.size > 0 then
    puts "[info] There are #{cards.size} cards with no labels"
    header = ':warning::label: *Cards with no labels*'
    message = format_cards(cards: cards, header: header)
    post(message)
  end

  cards = blocked(lists)
  if cards.size > 0 then
    puts "[info] There are #{cards.size} cards that are blocked"
    header = ':no_entry_sign::construction: *Cards that are blocked*'
    message = format_cards(cards: cards, header: header)
    post(message, :channel => '@lindsay')
  end
end

ENV['TZ'] = 'Australia/Sydney'

def main
  scheduler = Rufus::Scheduler.new
  #scheduler.cron '* * * * 1-5 Australia/Sydney' do
  scheduler.cron '0 10,13,15 * * 1-5 Australia/Sydney' do
    begin
      notify_problems!
    rescue => e
      p e
    end
  end
  scheduler.join
end

main()
