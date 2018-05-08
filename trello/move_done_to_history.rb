# frozen_string_literal: true

require 'trello'
require 'dotenv'
Dotenv.load

Trello.configure do |config|
  config.developer_public_key = ENV['TRELLO_DEVELOPER_PUBLIC_KEY']
  config.member_token = ENV['TRELLO_MEMBER_TOKEN']
end

def client
  return @client if @client
  credentials = {
    developer_public_key: ENV['TRELLO_DEVELOPER_PUBLIC_KEY'],
    member_token: ENV['TRELLO_MEMBER_TOKEN']
  }
  @client = Trello::Client.new(credentials)
end

# Increase the timeout, so the operation can actually complete
# rubocop:disable Style/Documentation
module Trello
  class TInternet
    class << self
      def execute_core(request)
        RestClient.proxy = ENV['HTTP_PROXY'] if ENV['HTTP_PROXY']
        RestClient::Request.execute(
          method: request.verb,
          url: request.uri.to_s,
          headers: request.headers,
          payload: request.body,
          timeout: 120
        )
      end
    end
  end
end
# rubocop:enable Style/Documentation

board_ids = {
  backlog: 'NwUJAqdJ',
  wip:     'pwRFfOZj',
  history: 'JmHJwCF0'
}

wip = Trello::Board.find(board_ids[:wip])
history = Trello::Board.find(board_ids[:history])

target_lists = wip.lists.select { |l| l.name =~ /sprint/i }.reverse

puts "There are #{target_lists.size} lists to move."

target_lists.each do |list|
  puts "Moving #{list.name}"
  attrs = {
    'closed' => list.closed,
    'idBoard' => history.id,
    'pos' => 'bottom'
  }
  client.put("/lists/#{list.id}", attrs)
end

puts 'DONE'
