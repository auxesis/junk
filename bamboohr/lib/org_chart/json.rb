# frozen-string-literal: true

require 'fuzzy_match'
require 'tree'

module OrgChartEngine
  # JSON is an engine backed by the now-deprecated JSON structure used BambooHR's graph view
  class JSON
    class << self
      attr_accessor :tree

      def bosses(person)
        id = person[:id]
        results = find_in_tree(id)&.parentage
        return [] unless results

        results.map(&:name).reverse.map do |name|
          directory[name]
        end
      end

      def reports(person)
        reports = find_in_tree(person[:id]).children
        return [] if reports.empty?

        reports.map!(&:name).map! { |name| directory[name] }
        reports.sort_by { |report| report[:name] }
      end

      def lookup(name, threshold: 0.3)
        index.find_all_with_score(name, threshold: threshold).map do |r, score|
          r.merge(score: score)
        end
      end

      def directory
        @directory ||= {}
      end

      def from(hash)
        @directory&.clear
        @index = nil
        @tree = build_node(hash)
      end

      def to_hash
        { 'tree' => children(@tree.first), 'directory' => directory }
      end

      def reset!
        @directory&.clear
        @index = nil
        @tree = nil
      end

      def orphans
        [{ name: 'Not supported', id: 0, job_title: '', direct_reports: false }]
      end

      private

      def children(node)
        Hash[directory[node.name], node.children.map { |c| children(c) }.flatten]
      end

      def add_to_directory(attrs)
        id = attrs['id'].to_s
        directory[id] = {
          name: attrs['name'].strip,
          id: id,
          job_title: attrs.dig('data', 'jInfo', 'job_title'),
          direct_reports: attrs.dig('data', 'directReports').positive?
        }
      end

      def index
        @index ||= FuzzyMatch.new(directory.values, read: ->(v) { v[:name] })
      end

      def find_in_tree(id)
        tree.find { |n| n.name == id }
      end

      def build_node(attrs)
        id = attrs['id'].to_s
        add_to_directory(attrs)
        node = Tree::TreeNode.new(id)
        build_tree(node, attrs['children'])
        node
      end

      def build_tree(parent, children)
        children.each { |attrs| parent << build_node(attrs) }
      end
    end
  end
end
