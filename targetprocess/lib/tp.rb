require "pry"
require "httparty"
require "aruba/api"

class TargetProcess
  include HTTParty
  include Aruba::Api

  base_uri "https://section.tpondemand.com/api/v1"
  #debug_output $stdout

  def initialize(token:)
    @access_token = token
    setup_aruba
  end

  def user_stories(opts = {})
    options = { query: { access_token: @access_token }.merge(opts) }
    self.class.get("/UserStories/", options)["UserStories"]["UserStory"]
  end

  def user_story(id, options = {})
    options.merge!(query: { access_token: @access_token })
    self.class.get("/UserStories/#{id}", options)
  end

  def user_story_simple_history(id, options = {})
    options.merge!(query: { access_token: @access_token })
    self.class.get("/UserStories/#{id}/History", options)
  end

  def user_story_full_history(id, options = {})
    options.merge!(query: { access_token: @access_token })
    self.class.get("/UserStories/#{id}/History", options)
  end

  def user_story_audit_history(id, options = {})
    body = { entityID: id, start: 0, limit: 100, entityType: "userStory" }
    options.merge!(headers: headers, query: body)
    url = "/AuditHistoryService.asmx/GetDetailedAuditRecordsLimitedForEntityType"
    self.class.post(url, options)
  end

  def audit_history_request_command(action:, body:)
    command = <<-GOODBYE
    curl 'https://section.tpondemand.com/Services/AuditHistoryService.asmx/#{action}' \
      -H 'Connection: keep-alive' \
      -H 'Pragma: no-cache' \
      -H 'Cache-Control: no-cache' \
      -H 'Accept: */*' \
      -H 'X-App-Version: 3.13.15.48243' \
      -H 'X-Requested-With: XMLHttpRequest' \
      -H 'Content-Type: application/json' \
      -H 'User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4044.129 Safari/537.36' \
      -H 'X-User-Id: 50' \
      -H 'X-Page-Id: userstory/8869' \
      -H 'Origin: https://section.tpondemand.com' \
      -H 'Sec-Fetch-Site: same-origin' \
      -H 'Sec-Fetch-Mode: cors' \
      -H 'Sec-Fetch-Dest: empty' \
      -H 'Referer: https://section.tpondemand.com/restui/board.aspx?' \
      -H 'Accept-Language: en-US,en;q=0.9' \
      -H '***REMOVED***
      --data-binary '#{body}' \
      --compressed
    GOODBYE
  end

  def user_story_audit_history_changes(entity_id:)
    action = "GetDetailedAuditRecordsLimitedForEntityType"
    body = {
      "entityID": entity_id,
      "start": 0,
      "limit": 100,
      "entityType": "userStory",
    }.to_json
    command = audit_history_request_command(action: action, body: body)
    run_command(command)
    last_command_started.wait
    JSON.parse(last_command_started.stdout)["d"]
  end

  def user_story_audit_history_change_details(entity_id:, history_id:)
    action = "GetChangeGroupsForEntityType"
    body = {
      "entityID": entity_id,
      "keys": [
        { "historyId": history_id, "entityTypeName": "UserStory" },
      ],
      "entityType": "userStory",
    }.to_json
    command = audit_history_request_command(action: action, body: body)
    run_command(command)
    last_command_started.wait
    JSON.parse(last_command_started.stdout)["d"]
  end

  def last_work_category_change(id:)
    changes = user_story_audit_history_changes(entity_id: id)
    filtered = changes.map { |c| c.select { |key, _| %w[EntityID ID Description Date].include?(key) } }
    filtered.map! { |c| c["Date"] = Time.at(c["Date"][/Date\((\d+)\)/, 1].to_i / 1000.0); c }
    category = nil
    filtered.each { |c|
      details = user_story_audit_history_change_details(entity_id: c["EntityID"], history_id: c["ID"])
      changes = details.first["Changes"].map { |deets| deets.merge(c) }
      wc = changes.detect { |ch| ch["Field"] == "Work Category" }
      if wc
        category = wc
        break
      end
    }
    category
  end
end
