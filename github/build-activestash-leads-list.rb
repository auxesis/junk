#!/usr/bin/env ruby

require "scraperwiki"
require "pry"
require "netrc"
require "octokit"

Octokit.auto_paginate = true
client = Octokit::Client.new(netrc: true)
client.login

search = ARGV.first # "language:ruby location:australia type:user"

unless search
  puts "Usage: #{$PROGRAM_NAME} '<user search query>'"
  exit(1)
end

user_results = client.search_users(search)

puts "Found #{user_results.items.size} results"
sleep(2)

user_results.items.each_with_index do |result, index|
  puts "Scraping metadata for: #{result.login}"
  user = client.user(result.login).to_hash
  user.select { |k, v| !!v == v }.each { |k, v| user[k] = v.to_s }
  ScraperWiki.save_sqlite(%i[id], user, "users")
end
