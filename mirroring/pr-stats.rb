require 'octokit'
require 'pry'
require 'vcr'
require 'webmock'
require 'dotenv'
Dotenv.load

VCR.configure do |config|
  config.cassette_library_dir = "fixtures"
  config.hook_into :webmock
end

Octokit.auto_paginate = true

def repo
  'envato/elements-backend'
end

def client
  @client ||= Octokit::Client.new(:access_token => ENV['GITHUB_TOKEN'])
  #@client.ensure_api_media_type(:reviews, accept: 'application/vnd.github.black-cat-preview')
end

def usernames
  return @usernames if @usernames
  @usernames = {}
  @usernames.default = -1
  @usernames.merge!({
    'MJIO' => 1,
    'asellitt' => 0,
    'auxesis' => 0,
    'damienadermann' => 1,
    'gbakernet' => 1,
    'gstamp' => 1,
    'kellec' => 0,
    'khayman' => 0,
    'lparry' => 0,
    'madlep' => 1,
    'patpaev' => 1,
    'ppj' => 1,
    'rabidcarrot' => 0,
    'staceyjdouglas' => 0,
    'vesu' => 0
  })
end

def prs
  if ENV['FAST']
    #File.open('marshal.bin', 'w') { |f| f << Marshal::dump(@prs) }
    #WebMock.allow_net_connect!
    #VCR.turn_off!
    records = Marshal::load(File.read('marshal.bin'))
  else
    VCR.use_cassette('elements-backend-pull-requests', record: :new_episodes) do
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

    File.open('marshal.bin', 'w') { |f| f << Marshal::dump(records) }
  end

  return records
end

def contributions
  prs.map do |pr, issue_comments, pr_comments, pr_reviews|
    owner = pr[:user][:login]
    participants = [
      issue_comments.map {|c| c[:user][:login]},
      pr_comments.map {|c| c[:user][:login]},
      pr_reviews.map {|c| c[:user][:login]}
    ].flatten.uniq - [ owner ]

    {
      repo: repo,
      number: pr[:number],
      owner: owner,
      participants: participants,
      week_of_year: pr[:closed_at].strftime('%W').to_i,
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

  counts = logins.inject({0 => 0, 1 => 0, -1 => 0}) { |summary, stream|
    summary[stream] += 1
    summary
  }.values

  [ week, counts ].flatten
end

puts pr_counts_by_week.sort.map { |c| c.join("\t") }
