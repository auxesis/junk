# frozen-string-literal: true

require 'bamboozled'
require 'configatron'
require 'dotenv'
require 'tree'
require 'pry'
require 'fuzzy_match'
require 'json'

Dotenv.load

configatron.bamboohr.subdomain = ENV['BAMBOOHR_SUBDOMAIN']
configatron.bamboohr.api_key = ENV['BAMBOOHR_API_KEY']

Node = Tree::TreeNode

def json
  JSON.parse(File.read('employees.json'))
end

def directory
  @directory ||= {}
end

def add_to_directory(attrs)
  name = attrs['name'].strip
  directory[name] = {
    id: attrs['id'],
    job_title: attrs.dig('data','jInfo','job_title'),
    direct_reports: attrs.dig('data', 'directReports') > 0
  }
  return name
end

def build_tree(parent, children)
  children.each do |attrs|
    name = attrs['name'].strip
    add_to_directory(attrs)
    node = Node.new(name)
    build_tree(node, attrs['children'])
    parent << node
  end
end

def dag
  return @root if @root
  @root = Node.new(json['name'])
  add_to_directory(json)
  build_tree(@root,json['children'])
  return @root
end

def bamboohr
  @client ||= Bamboozled.client(configatron.bamboohr.to_hash)
end

def index
  @index ||= (dag && FuzzyMatch.new(directory.keys))
end

def find_in_tree(name)
  dag.find { |n| n.name == name }
end

def parentage(name)
  find_in_tree(name).parentage&.map(&:name).reverse.map { |n|
    [n, directory[n]]
  } << [ name, directory[name] ]
end

def children(name)
  find_in_tree(name).children&.map(&:name).map { |n|
    [n, directory[n]]
  }
end

def lookup(name)
  index.find_all(name, threshold: 0.5).map { |n| [ n, directory[n] ] }
end

binding.pry
