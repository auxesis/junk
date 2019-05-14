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

_history = Trello::Board.find(board_ids[:history])

@people = {}

def add_to_tally(who:, card:)
  @people[who] ||= []
  @people[who] << card
end

target_sprint = _history.lists.reverse.select { |l| l.name =~ /Sprint 13$/}.first
target_sprint.cards.each do |card|
  if card.members.any?
    card.members.each do |member|
      name = member.full_name
      add_to_tally(who: name, card: card)
    end
  else
    actions = card.actions.select { |a| a.attributes[:type] == 'addMemberToCard' }
    actions.each do |action|
      name = action.member_participant['fullName']
      add_to_tally(who: name, card: card)
    end
  end
end

people = Hash[@people.sort_by {|name, cards| name }]

if false
m = Marshal.dump(people)
File.open('people.marshal', 'w') { |f| f << m }
end

class Work
  def self.parse(name)
    m = name.match(/\[(?<tshirt>[XS|S|M|L|XL|EPIC])\] (\[(?<initiative>[^\[]+)\] )?(?<title>.+)/)
    new(m.named_captures) if m
  end

  attr_reader :tshirt, :initiative, :title

  def initialize(attrs)
    @tshirt = attrs['tshirt'] if attrs['tshirt']
    @initiative = attrs['initiative'] if attrs['initiative']
    @title = attrs['title'] if attrs['title']
  end

  def score
    scores[tshirt]
  end

  def scores
    { 'XS' => 0.5, 'S' => 1, 'M' => 2, 'L' => 4, 'XL' => 8 }
  end
end

#people = Marshal.load(File.read('people.marshal'))

people.each do |name, cards|
  work = cards.map { |c| Work.parse(c.name) }.compact
  initiatives = work.group_by { |w| w.initiative }
  scores = initiatives.map { |initiative, work| [ initiative, work.map { |w| w.score }.sum ] }.to_h

  scores.sort_by { |k, _v| k.to_s }.each do |initiative, score|
    initiative ||= 'BAU'
    percentage = (score / scores.values.sum.to_f * 90)

    puts [name, initiative, percentage].join("\t")
  end
end
