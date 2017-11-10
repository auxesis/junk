# frozen_string_literal: true

require 'scraperwiki'
require 'pry'
require 'dotenv'
require 'octokit'
Dotenv.load

def github_token
  return ENV['GITHUB_TOKEN'] if ENV['GITHUB_TOKEN']
  puts '[info] The GITHUB_TOKEN environment variable must be set'
  exit(1)
end

def target_repos
  return ENV['TARGET_REPOS'].split(',') if ENV['TARGET_REPOS']
  puts '[info] The TARGET_REPOS environment variable must be set'
  exit(1)
end

def target_since
  return Date.parse(ENV['TARGET_SINCE']).to_time if ENV['TARGET_SINCE']
  puts '[info] The TARGET_SINCE environment variable must be set'
  exit(1)
end

def target_state
  'closed'
end

Octokit.auto_paginate = true

def client
  @client ||= Octokit::Client.new(access_token: github_token)
end

def pull_requests(repo:, since:)
  client.pull_requests(repo, state: target_state).select do |pr|
    pr[:created_at] > since
  end
end

def scrape_pull_requests(repos:, since:)
  repos.each do |repo|
    puts "[info] #{repo} fetching Pull Requests"
    prs = pull_requests(repo: repo, since: since)
    records = prs.map do |pr|
      { 'id' => pr[:number], 'repo' => repo, 'json' => pr.to_hash.to_json }
    end
    puts "[info] #{repo} saving #{records.size} Pull Requests"
    ScraperWiki.save_sqlite(%w[id repo], records, 'pull_requests')
  end
end

def scrape_pull_request_activity(repos:)
  repos_query = 'AND pull_requests.repo IN (' + repos.map {|r| "'#{r}'"}.join(',') + ')'
  prs = ScraperWiki.select("pull_requests.id AS id,pull_requests.repo AS repo FROM pull_requests LEFT JOIN comments ON pull_requests.id = comments.pr_id WHERE comments.pr_id IS NULL #{repos_query} ORDER BY pull_requests.repo,pull_requests.id")
  prs.each do |pr|
    number = pr['id']
    repo = pr['repo']
    puts "[info] #{repo}##{number} fetching activity"
    scrape_issue_comments(number: number, repo: repo)
    scrape_pull_request_comments(number: number, repo: repo)
    scrape_pull_request_reviews(number: number, repo: repo)
  end
end

def scrape_issue_comments(number:, repo:)
  comments = client.issue_comments(repo, number)
  records = comments.map do |comment|
    {
      'id' => comment[:id], 'pr_id' => number, 'repo' => repo,
      'type' => 'issue', 'json' => comment.to_hash.to_json
    }
  end
  puts "[info] #{repo}##{number} saving #{records.size} issue comments"
  ScraperWiki.save_sqlite(%w[id pr_id repo type], records, 'comments')
end

def scrape_pull_request_comments(number:, repo:)
  comments = client.pull_request_comments(repo, number)
  records = comments.map do |comment|
    {
      'id' => comment[:id], 'pr_id' => number, 'repo' => repo,
      'type' => 'pull_request', 'json' => comment.to_hash.to_json
    }
  end
  puts "[info] #{repo}##{number} saving #{records.size} pull request comments"
  ScraperWiki.save_sqlite(%w[id pr_id repo type], records, 'comments')
end

def scrape_pull_request_reviews(number:, repo:)
  media_type = 'application/vnd.github.thor-preview+json'
  reviews = client.pull_request_reviews(repo, number, accept: media_type)
  records = reviews.map do |review|
    {
      'id' => review[:id], 'pr_id' => number, 'repo' => repo,
      'type' => 'review', 'json' => review.to_hash.to_json
    }
  end
  puts "[info] #{repo}##{number} saving #{records.size} pull request reviews"
  ScraperWiki.save_sqlite(%w[id pr_id repo type], records, 'comments')
end

def main
  scrape_pull_requests(repos: target_repos, since: target_since)
  scrape_pull_request_activity(repos: target_repos)
end

main if $PROGRAM_NAME == __FILE__
