# frozen-string-literal: true

require 'fuzzy_match'
require 'tree'

# Organisation tree and directory of people
class OrgChart
  class << self
    attr_accessor :tree

    def bosses(id)
      results = find_in_tree(id)&.parentage
      return [] unless results

      results.map(&:name).reverse.map do |name|
        directory[name].merge(name: name)
      end
    end

    def reports(id)
      reports = find_in_tree(id).children
      return [] if reports.empty?

      reports.map!(&:name).map! { |name| directory[name].merge(name: name) }
      reports.sort_by { |person| person[:name] }
    end

    def lookup(name, threshold: 0.3)
      index.find_all_with_score(name, threshold: threshold).map do |id, score|
        directory[id].merge(name: id, score: score)
      end
    end

    def directory
      @directory ||= {}
    end

    def format(person:)
      base = [person[:name], person[:job_title]].join(' – ')
      base += ' :small_blue_diamond:' if person[:direct_reports]
      base
    end

    def build_tree_from_hash(hash)
      @directory&.clear
      @index = nil
      @tree = build_node(hash)
    end

    def to_hash
      children(@tree.first)
    end

    private

    def children(node)
      Hash[node.name, node.children.map { |c| children(c) }.flatten]
    end

    def add_to_directory(attrs)
      name = attrs['name'].strip
      directory[name] = {
        id: attrs['id'],
        job_title: attrs.dig('data', 'jInfo', 'job_title'),
        direct_reports: attrs.dig('data', 'directReports').positive?
      }
    end

    def index
      @index ||= FuzzyMatch.new(directory.keys)
    end

    def find_in_tree(id)
      tree.find { |n| n.name == id }
    end

    def build_node(attrs)
      name = attrs['name'].strip
      add_to_directory(attrs)
      node = Tree::TreeNode.new(name)
      build_tree(node, attrs['children'])
      node
    end

    def build_tree(parent, children)
      children.each { |attrs| parent << build_node(attrs) }
    end
  end
end
