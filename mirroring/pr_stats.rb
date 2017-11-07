# frozen_string_literal: true

require 'scraperwiki'
require 'json'
require 'pry'
require 'dotenv'
Dotenv.load

def target_streams
  if ENV['TARGET_STREAMS']
    ENV['TARGET_STREAMS'].split(',').map(&:to_i)
  else
    puts 'ERROR: The TARGET_STREAMS environment variable must be set'
    exit(1)
  end
end

def target_repos
  if ENV['TARGET_REPOS']
    ENV['TARGET_REPOS'].split(',')
  else
    puts 'ERROR: The TARGET_REPOS environment variable must be set'
    exit(1)
  end
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

def pull_requests_participation(repo:)
  pull_requests = ScraperWiki.select("* FROM pull_requests WHERE repo = '#{repo}'")
  pull_requests.map do |pr|
    pr = JSON.parse(pr['json'])
    owner = pr['user']['login']
    number = pr['number']

    comments = ScraperWiki.select("* FROM comments WHERE repo = '#{repo}' and pr_id = #{number}")
    participants = comments.map do |c|
      JSON.parse(c['json'])['user']['login']
    end.flatten.uniq - [owner]

    {
      repo: repo,
      number: number,
      owner: owner,
      participants: participants,
      week_of_year: Time.parse(pr['closed_at']).strftime('%W').to_i
    }
  end
end

def add_missing_weeks!(prs_by_week)
  min = prs_by_week.keys.sort.first
  max = prs_by_week.keys.sort.last
  (min..max).to_a.each { |week| prs_by_week[week] ||= [] }
end

def weekly_pr_counts(streams:, repos:)
  output = streams.map do |stream|
    repos.map do |repo|
      participations = pull_requests_participation(repo: repo)
      prs_by_week = participations.select do |part|
        usernames[part[:owner]] == stream
      end.group_by do |part|
        part[:week_of_year]
      end

      add_missing_weeks!(prs_by_week)

      prs_by_week.map do |week, parts|
        logins = parts.map { |c| c[:participants].uniq }.flatten.map { |u| usernames[u] }

        counts = logins.inject(0 => 0, 1 => 0, -1 => 0) do |summary, stream|
          summary[stream] += 1
          summary
        end.values

        [week, stream, counts].flatten
      end
    end
  end

  output.flatten(2).sort
end

if $PROGRAM_NAME == __FILE__
  report = weekly_pr_counts(streams: target_streams, repos: target_repos)
  puts report.map { |c| c.join("\t") }
end
