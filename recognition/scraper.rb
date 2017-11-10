#!/usr/bin/env ruby

require 'dotenv'
Dotenv.load
require 'scraperwiki'
require 'slack-ruby-client'
require 'fileutils'
require 'pry'

Slack.configure do |config|
  config.token = ENV['SLACK_API_TOKEN']
end

def client
  Slack::Web::Client.new
end

def names
  File.readlines('people.txt').reject do |l|
    l =~ /^#/ || l =~ /^\s*$/
  end.map(&:strip)
end

def lookup_user(name:)
  terms = [ name, name.gsub(/\s/,'.').downcase ]
  user = terms.detect do |term|
    response = client.users_search(user: term)
    break(response['members'].first) if response['ok'] && response['members'].size == 1
  end
  return user if user

  puts "#{users['members'].size} users matched search for #{name}"
  binding.pry
  raise
rescue Slack::Web::Api::Errors::TooManyRequestsError => e
  seconds = e.response.headers['retry-after'].to_i
  sleep(seconds)
  retry
end

def previously_scraped?(name)
  ScraperWiki.select("* FROM data WHERE name = '#{name}'").any?
rescue SqliteMagic::NoSuchTable
  false
end

def image_exists?(path)
  File.exists?(path)
end

def image_basedir
  'avatars'
end

def image_size
  'image_192'
end

def image_path(record)
  filetype = record[image_size].split('.').last
  basename = record['name'].downcase.split(' ').join('_')
  filename = [basename, filetype].join('.')
  FileUtils.mkdir_p(image_basedir)
  return File.join(image_basedir, filename)
end

names.each do |name|
  if previously_scraped?(name)
    puts "Skipping previously scraped person #{name}"
    next
  end

  user = lookup_user(name: name)
  images = user['profile'].select {|k,v| k =~ /^image_/}
  record = { name: name }.merge(images)
  puts "Scraped avatar URLs for #{name}"
  ScraperWiki.save([:name],record)
end

records = ScraperWiki.select('* FROM data')
records.each do |record|
  path = image_path(record)
  if image_exists?(path)
    puts "Skipping previously scraped avatar for #{record['name']}"
    next
  end
  image = open(record['image_192']).read
  File.open(path,'w') { |f| f << image }
  puts "Avatar written to #{path}"
end
