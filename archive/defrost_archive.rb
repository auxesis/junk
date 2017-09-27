# frozen-string-literal: true

require_relative('lib/data')

binding.pry

updates = Action.all.select {|a| a.attrs['type'] == 'updateCard' }
