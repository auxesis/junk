# frozen_string_literal: true

require 'octokit'
require 'pry'
require 'vcr'
require 'webmock'
require 'dotenv'
Dotenv.load

VCR.configure do |config|
  config.cassette_library_dir = 'fixtures'
  config.hook_into :webmock
end

Octokit.auto_paginate = true

def repo
  'envato/elements-backend'
end

def short_repo
  repo.split('/').last
end

def client
  @client ||= Octokit::Client.new(access_token: ENV['GITHUB_TOKEN'])
end

def usernames
  return @usernames if @usernames
  streams = {
    0 => %w[asellitt auxesis kellec khayman lparry rabidcarrot staceyjdouglas vesu],
    1 => %w[MJIO damienadermann gbakernet gstamp madlep patpaev ppj]
  }
  @usernames = {}
  @usernames.default = -1
  streams.each do |id, usernames|
    usernames.each do |username|
      @usernames[username] = id
    end
  end
end

# rubocop:disable Security/MarshalLoad
def prs
  if ENV['FAST']
    records = Marshal.load(File.read("marshal-#{short_repo}.bin"))
  else
    VCR.use_cassette("#{short_repo}-pull-requests", record: :new_episodes) do
      all_pull_requests = client.pull_requests(repo, state: 'closed')
      pull_requests = all_pull_requests.select { |pr| pr[:created_at] > Date.parse('2017-02-13').to_time }
      records = pull_requests.map do |pr|
        STDERR.puts "Fetching activity for #{repo}##{pr[:number]}"
        [
          pr,
          client.issue_comments(repo, pr[:number]),
          client.pull_request_comments(repo, pr[:number]),
          client.pull_request_reviews(repo, pr[:number])
        ]
      end
    end

    File.open("marshal-#{short_repo}.bin", 'w') { |f| f << Marshal.dump(records) }
  end

  records
end
# rubocop:enable Security/MarshalLoad

def contributions
  prs.map do |pr, issue_comments, pr_comments, pr_reviews|
    owner = pr[:user][:login]
    participants = [
      issue_comments.map { |c| c[:user][:login] },
      pr_comments.map { |c| c[:user][:login] },
      pr_reviews.map { |c| c[:user][:login] }
    ].flatten.uniq - [owner]

    {
      repo: repo,
      number: pr[:number],
      owner: owner,
      participants: participants,
      week_of_year: pr[:closed_at].strftime('%W').to_i
    }
  end
end

def stream_prs(stream:)
  contributions.select { |contrib| usernames[contrib[:owner]] == stream }
end

def add_missing_weeks!(prs_by_week)
  min = prs_by_week.keys.sort.first
  max = prs_by_week.keys.sort.last
  missing_weeks = (min..max).to_a - prs_by_week.keys
  missing_weeks.each { |week| prs_by_week[week] = [] }
end

prs_by_week = stream_prs(stream: 1).group_by { |c| c[:week_of_year] }
add_missing_weeks!(prs_by_week)

pr_counts_by_week = prs_by_week.map do |week, contribs|
  logins = contribs.map { |c| c[:participants].uniq }.flatten.map { |u| usernames[u] }

  counts = logins.inject(0 => 0, 1 => 0, -1 => 0) do |summary, stream|
    summary[stream] += 1
    summary
  end.values

  [week, counts].flatten
end

puts pr_counts_by_week.sort.map { |c| c.join("\t") }
