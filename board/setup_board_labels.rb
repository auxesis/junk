#!/usr/bin/env ruby

require 'trello'

Trello.configure do |config|
  config.developer_public_key = ENV['TRELLO_DEVELOPER_PUBLIC_KEY']
  config.member_token = ENV['TRELLO_MEMBER_TOKEN']
end

def default_labels
  [
    {:name=>'Stream 0 / BAU', :color=>'black'},
    {:name=>'Stream 1 / Photos',:color=>'green'},
    {:name=>'Stream 2 / Subscriptions',:color=>'yellow'},
    {:name=>'Stream 3 / Payments calculator',:color=>'orange'}
  ]
end

def setup_labels!(board)
  # Create the labels that don't exist
  default_labels.each do |label|
    existing = board.labels.find {|b| b.name == label[:name]}
    if not existing
      Trello::Label.create(label.merge(:board_id => board.id))
    end
  end

  # Shove them into the shorthand reference structure
  shorthands = %w(stream0 stream1 stream2 stream3)
  zipped = shorthands.zip(default_labels.map{|l| l[:name]})
  labels = zipped.map {|short,full|
    [short, board.labels.find {|l| l.name == full}]
  }
  @labels = Hash[labels]
end

def labels
  @labels ? (return @labels) : (raise 'setup_labels! not called')
end

board_ids = ARGV
if board_ids.empty?
  puts "Usage: #{$PROGRAM_NAME} <trello_board_id> [<trello_board_id> ...]"
  exit(1)
end

board_ids.each do |id|
  board = Trello::Board.find(id)
  puts "Setting up #{board.name} (#{id})"
  setup_labels!(board)
end

