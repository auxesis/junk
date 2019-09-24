#!/usr/bin/env ruby

require "netrc"
require "octokit"

Octokit.auto_paginate = true
client = Octokit::Client.new(netrc: true)
client.login

org = ARGV[0]
username = ARGV[1]
level = "maintain"

unless (org && username)
  puts "Usage: #{$PROGRAM_NAME} <github_org> <username>"
  exit(1)
end

repos = client.repos(org)

puts "Target org '#{org}' has #{repos.size} repos\n"
sleep(1)

repos.each do |r|
  repo_name = r[:full_name]
  print "Granting #{username} the #{level} permission on #{repo_name} ..."
  response = client.add_collaborator(repo_name, username, permission: level)
  puts (response ? "OK" : "FAILED")
end
