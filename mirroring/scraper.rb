# frozen_string_literal: true

require 'scraperwiki'
require 'pry'
require 'dotenv'
require 'octokit'
Dotenv.load

def existing_record_ids(table: 'data', id: 'id')
  @cached ||= {}
  return @cached[table] if @cached[table]
  @cached[table] = ScraperWiki.select("#{id} from #{table}").map { |r| r[id] }
rescue SqliteMagic::NoSuchTable
  []
end

def actions_from_cards(cards)
  cards.map do |card|
    a = JSON.parse(Trello::Card.find(card[:id]).actions.to_json)
    a.map do |attr|
      {
        'id'      => attr['id'],
        'card_id' => card[:id],
        'json'    => attr.merge('card_id' => card[:id]).to_json
      }
    end
  end.flatten!
end

def board_id
  'pwRFfOZj' # WIP
end

def board
  Trello::Board.find(board_id)
end

def cards
  @cards ||= board.cards.map do |c|
    {
      'id': c.id,
      'list_id': c.list_id,
      'json': c.to_json
    }
  end
end

def lists
  @lists ||= board.lists.map { |l| JSON.parse(l.to_json) }
end

def filter_to_new(records, key: 'id', table:)
  records.reject { |r| existing_record_ids(table: table).include?(r[key]) }
end

def existing_record_count(table:)
  existing_record_ids(table: table).size
end

def snapshot_lists
  puts "[info] There are #{existing_record_count(table: 'lists')} existing list records"
  puts "[info] Saving #{lists.size} list records"
  lists.each { |l| l['closed'] = l['closed'] ? 1 : 0 } # Make data sqlite friendly
  ScraperWiki.save_sqlite(%w[id], lists, 'lists')
end

def snapshot_cards_and_actions
  puts "[info] There are #{existing_record_count(table: 'cards')} existing card records"
  puts "[info] Saving #{cards.size} card records"
  ScraperWiki.save_sqlite(%i[id], cards, 'cards')

  actions = actions_from_cards(cards)
  puts "[info] There are #{existing_record_count(table: 'actions')} existing action records"
  puts "[info] Saving #{actions.size} action records"
  ScraperWiki.save_sqlite(%w[id], actions, 'actions')
end

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
    puts "[info] Fetching Pull Requests for #{repo}"
    prs = pull_requests(repo: repo, since: since)
    records = prs.map do |pr|
      { 'id' => pr[:number], 'repo' => repo, 'json' => pr.to_hash.to_json }
    end
    puts "[info] Saving #{records.size} Pull Requests on #{repo}"
    ScraperWiki.save_sqlite(%w[id repo], records, 'pull_requests')
  end
end

def scrape_pull_request_activity
  prs = ScraperWiki.select('id,repo FROM pull_requests ORDER BY repo,id')
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
  # scrape_pull_requests(repos: target_repos, since: target_since)
  scrape_pull_request_activity
end

main if $PROGRAM_NAME == __FILE__
