# frozen-string-literal: true

require 'json'
require 'pry'
require 'sequel'

DB = Sequel.sqlite('data.sqlite')

# Trello lists
class List < Sequel::Model
  set_primary_key :id
  one_to_many :cards
end

# Trello cards
class Card < Sequel::Model
  set_primary_key :id
  many_to_one :list
  one_to_many :actions
end

# Card actions
class Action < Sequel::Model
  set_primary_key :id
  many_to_one :card

  plugin :serialization, :json, :json
  alias attrs json
end
