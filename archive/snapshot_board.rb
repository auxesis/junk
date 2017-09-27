# frozen_string_literal: true

require 'scraperwiki'
require 'trello'
require 'pry'
require 'dotenv'
Dotenv.load

Trello.configure do |config|
  config.developer_public_key = ENV['TRELLO_DEVELOPER_PUBLIC_KEY']
  config.member_token = ENV['TRELLO_MEMBER_TOKEN']
end

def existing_record_ids(table: 'data', id: 'id')
  @cached ||= {}
  return @cached[table] if @cached[table]
  @cached[table] = ScraperWiki.select("#{id} from #{table}").map { |r| r[id] }
rescue SqliteMagic::NoSuchTable
  []
end

def actions_from_cards(cards)
  cards.map do |card|
    a = JSON.parse(Trello::Card.find(card[:id]).actions.to_json)
    a.map do |attr|
      {
        'id'      => attr['id'],
        'card_id' => card[:id],
        'json'    => attr.merge('card_id' => card[:id]).to_json
      }
    end
  end.flatten!
end

def board_id
  'pwRFfOZj' # WIP
end

def board
  Trello::Board.find(board_id)
end

def cards
  @cards ||= board.cards.map do |c|
    {
      'id': c.id,
      'list_id': c.list_id,
      'json': c.to_json
    }
  end
end

def lists
  board.lists.map { |l| JSON.parse(l.to_json) }
end

def filter_to_new(records, key: 'id', table:)
  records.reject { |r| existing_record_ids(table: table).include?(r[key]) }
end

def existing_record_count(table:)
  existing_record_ids(table: table).size
end

def snapshot_lists
  puts "[info] There are #{existing_record_count(table: 'lists')} existing list records"
  new_lists = filter_to_new(lists, table: 'lists')
  puts "[info] There are #{new_lists.size} new list records"
  new_lists.each { |l| l['closed'] = l['closed'] ? 1 : 0 } # Make data sqlite friendly
  ScraperWiki.save_sqlite(%w[id], new_lists, 'lists')
end

def snapshot_cards_and_actions
  puts "[info] There are #{existing_record_count(table: 'cards')} existing card records"
  puts "[info] Saving #{cards.size} card records"
  ScraperWiki.save_sqlite(%i[id], cards, 'cards')

  actions = actions_from_cards(cards)
  puts "[info] There are #{existing_record_count(table: 'actions')} existing action records"
  puts "[info] There are #{actions.size} action records"
  ScraperWiki.save_sqlite(%w[id], actions, 'actions')
end

def main
  snapshot_lists
  snapshot_cards_and_actions
end

main if $PROGRAM_NAME == __FILE__
