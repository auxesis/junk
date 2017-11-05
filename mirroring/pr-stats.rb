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

repo = 'envato/elements-backend'
client = Octokit::Client.new(:access_token => ENV['GITHUB_TOKEN'])
#client.ensure_api_media_type(:reviews, accept: 'application/vnd.github.black-cat-preview')

def usernames
  return @usernames if @usernames
  @usernames = {}
  @usernames.default = 2
  @usernames.merge!({
    'MJIO' => 1,
    'asellitt' => 0,
    # 'auxesis' => 0,
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

VCR.use_cassette('elements-backend-pull-requests', record: :new_episodes) do
  @all_pull_requests = client.pull_requests(repo, state: 'closed')
  @pull_requests = @all_pull_requests.select { |pr| pr[:created_at] > Date.parse('2017-02-13').to_time }
  @prs = @pull_requests.map do |pr|
    STDERR.puts "Fetching activity for #{repo}##{pr[:number]}"
    [
      pr,
      client.pull_request_comments(repo, pr[:number]),
      client.pull_request_reviews(repo, pr[:number])
    ]
  end
end

contributions = @prs.map do |pr, comments, reviews|
  owner = pr[:user][:login]
  {
    repo: repo,
    number: pr[:number],
    owner: owner,
    commenters: comments.map {|c| c[:user][:login]}.uniq - [ owner ],
    reviewers: reviews.map {|c| c[:user][:login]}.uniq - [ owner ],
  }
end

counts = contributions.map do |contrib|
  logins = [
    usernames[contrib[:owner]],
    contrib[:commenters].map { |u| usernames[u] },
    contrib[:reviewers].map { |u| usernames[u] }
  ].flatten
  # 0 => stream 0
  # 1 => stream 1
  # 2 => outside Elements
  counts = logins.inject({0 => 0, 1 => 0, 2 => 0}) { |summary, stream|
    summary[stream] += 1
    summary
  }.values

  [ contrib[:number], counts ].flatten
end

puts counts.sort_by {|c| [ c[1], c[2], c[3] ]}.map {|c| c.join("\t")}

#binding.pry

exit

contributions.each do |contrib|
  logins = [
    usernames[contrib[:owner]],
    contrib[:commenters].map { |u| usernames[u] },
    contrib[:reviewers].map { |u| usernames[u] }
  ]
  # 0 => stream 0
  # 1 => stream 1
  # 2 => outside Elements
  counts = logins.flatten.inject({0 => 0, 1 => 0, 2 => 0}) { |summary, stream|
    summary[stream] += 1
    summary
  }.values

  puts [
    contrib[:number],
    counts
  ].join("\t")
end
