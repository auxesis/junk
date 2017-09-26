#!/usr/bin/env ruby

require 'scraperwiki'
require 'trello'
require 'pry'
require 'dotenv'
Dotenv.load

def existing_record_ids(table: 'data', id: 'id')
  @cached ||= {}
  if @cached[table]
    return @cached[table]
  else
    @cached[table] = ScraperWiki.select("#{id} from #{table}").map {|r| r[id]}
  end
rescue SqliteMagic::NoSuchTable
  []
end

Trello.configure do |config|
  config.developer_public_key = ENV['TRELLO_DEVELOPER_PUBLIC_KEY']
  config.member_token = ENV['TRELLO_MEMBER_TOKEN']
end

def cards_and_actions
  board_id = 'pwRFfOZj' # WIP
  board = Trello::Board.find(board_id)

  cards = board.cards

  actions = cards.map { |card|
    a = JSON.parse(card.actions.to_json)
    a.map {|a|
      {
        'id'      => a['id'],
        'card_id' => card.id,
        'json'    => a.merge('card_id' => card.id).to_json
      }
    }
  }.flatten!
  cards.map! {|c| {'id' => c.id, 'json' => c.to_json } }

  return cards, actions
end

def main
  cards, actions = cards_and_actions

  puts "[info] There are #{existing_record_ids(table: 'cards').size} existing card records"
  new_cards = cards.select {|c| !existing_record_ids(table: 'cards').include?(c['id']) }
  puts "[info] There are #{new_cards.size} new card records"
  ScraperWiki.save_sqlite(%w(id), new_cards, 'cards')

  puts "[info] There are #{existing_record_ids(table: 'actions').size} existing action records"
  new_actions = actions.select {|a| !existing_record_ids(table: 'actions').include?(a['id']) }
  puts "[info] There are #{new_actions.size} new actions records"
  ScraperWiki.save_sqlite(%w(id), new_actions, 'actions')
end

main()
