require "net/http"
require "uri"
require "json"

def build_audit_history_request(domain, action)
  uri = URI.parse("https://#{domain}/Services/AuditHistoryService.asmx/#{action}")
  request = Net::HTTP::Post.new(uri)
  request.content_type = "application/json"
  request
end

target_domain = "plan.tpondemand.com"
targets_entities = (249295..249295).to_a

#target_domain = "atera.tpondemand.com"
#targets_entities = (4736..4737).to_a

targets_entities.each do |i|
  action = "GetDetailedAuditRecordsLimitedForEntityType"
  request = build_audit_history_request(target_domain, action)

  request.body = JSON.dump({
    "entityID" => i.to_s,
    "start" => 0,
    "limit" => 100,
    "entityType" => "request",
  })

  req_options = {
    use_ssl: request.uri.scheme == "https",
  }

  response = Net::HTTP.start(request.uri.hostname, request.uri.port, req_options) do |http|
    http.request(request)
  end

  p [i, response.code]
  if response.code == "200"
    changes = JSON.parse(response.body)["d"].map { |c| c.select { |key, _| %w[EntityID ID Description Date].include?(key) } }

    action = "GetChangeGroupsForEntityType"
    request = build_audit_history_request(target_domain, action)

    changes.each do |change|
      request.body = JSON.dump({
        "entityID" => i.to_s,
        "keys" => [
          { "historyId": change["ID"], "entityTypeName": "Request" },
        ],
        "entityType" => "request",
      })

      req_options = {
        use_ssl: request.uri.scheme == "https",
      }

      response = Net::HTTP.start(request.uri.hostname, request.uri.port, req_options) do |http|
        http.request(request)
      end

      p response.code
      p response.body
    end
    exit
  end
end
