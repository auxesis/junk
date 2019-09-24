#!/usr/bin/env ruby

require "netrc"
require "octokit"

Octokit.auto_paginate = true
client = Octokit::Client.new(netrc: true)
client.login

if (org = ARGV.first) == nil
  puts "Usage: #{$PROGRAM_NAME} <github_org>"
  exit(1)
end

repos = client.repos(org)

puts "Target org '#{org}' has #{repos.size} repos\n"
sleep(1)

repos.each do |r|
  repo_name = r[:full_name]
  begin
    client.subscription(repo_name)
    puts "Ignoring #{repo_name}"
    client.update_subscription(repo_name, :ignored => true)
  rescue Octokit::NotFound
    puts "Skipping #{repo_name}"
  end
end
