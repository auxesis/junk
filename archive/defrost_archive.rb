#!/usr/bin/env ruby

require 'scraperwiki'
require 'pry'
require 'json'

def main
  cards = ScraperWiki.select('* from cards').map {|c| JSON.parse(c['json'])}
  actions = ScraperWiki.select('* from actions').map {|c| JSON.parse(c['json'])}

  cards.each do |card|
    card_actions = actions.select {|a| a['card_id'] == card['id']}
    card['actions'] = card_actions
  end

  binding.pry
end

main()
