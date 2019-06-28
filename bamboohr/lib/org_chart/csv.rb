# frozen-string-literal: true

require 'fuzzy_match'

module OrgChartEngine
  # CSV is a org chart engine backed by the CSV output from BambooHR's graph view
  class CSV
    class << self
      def from(csv)
        reset!
        csv.each do |row|
          child = row['PersonID']
          parent = row['SupervisorID']
          tree << { parent: parent, child: child }
        end

        csv.each do |row|
          add_to_directory(row)
        end
      end

      def add_to_directory(attrs)
        id = attrs['PersonID']
        directory[id] = {
          name: attrs['Name'],
          id: id,
          job_title: attrs['Job Title'],
          direct_reports: tree.select { |r| r[:parent] == id }.any?
        }
      end

      def reset!
        @directory = nil
        @tree = nil
        @index = nil
      end

      def directory
        @directory ||= {}
      end

      def tree
        @tree ||= []
      end

      def index
        @index ||= FuzzyMatch.new(directory.values, read: ->(v) { v[:name] })
      end

      def bosses(person)
        relationships = find_parents(person[:id], []).reverse
        relationships.map { |id| directory[id] }
      end

      def find_parents(id, parents)
        parent = tree.find { |r| r[:child] == id }&.fetch(:parent)
        return parents unless parent

        parents << parent
        find_parents(parents.last, parents)
      end

      def find_children(id, children)
        childs = tree.select { |r| r[:parent] == id }.map { |r| r[:child] }
        Hash[directory[id], childs.map { |c| find_children(c, children) }.flatten]
      end

      def reports(person)
        relationships = tree.select { |r| r[:parent] == person[:id] }
        reports = relationships.map { |r| directory[r[:child]] }
        reports.sort_by { |r| r[:name] }
      end

      def lookup(name, threshold: 0.3)
        index.find_all_with_score(name, threshold: threshold).map do |r, score|
          r.merge(score: score)
        end
      end

      def orphans
        orphans = tree.reject { |r| r[:parent] }
        orphans.map { |orphan| directory[orphan[:child]] }
      end

      def to_hash
        {
          'tree' => find_children(find_parents(directory.keys.first, []).last, {}),
          'directory' => directory
        }
      end
    end
  end
end
