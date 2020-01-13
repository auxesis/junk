require "pry"
require "httparty"
require "pagerduty"
require "ejson_wrapper"
require "dotenv"

Dotenv.load

def credentials
  @creds ||= EJSONWrapper.decrypt("credentials.ejson", private_key: ENV["CHECK_APPOINTMENTS_PRIVATE_KEY"])
end

def config
  credentials.merge({
    current_appointment: 1579640400, # + (86400 * 2),
  })
end

def appointments
  query = {
    "mode" => "NBNApptSchedulerValidate",
    "mobileNumber" => config[:nbn][:mobileNumber],
    "uniqueCode" => config[:nbn][:uniqueCode],
  }
  url = "https://www.aussiebroadband.com.au/__process.php"
  response = HTTParty.post(url, body: query)

  if not response["appointments"]
    puts response.parsed_response
    raise RuntimeError
  end
  normalized = response["appointments"].map { |k, v| v.merge("unix_time" => k.to_i) }
  normalized.sort_by { |v| v["unix_time"] }
end

def earliest_appointment(refresh: false)
  @earliest = appointments.first if refresh # if we're forced
  @earliest ||= appointments.first # if it's not set
  @earliest
end

def pagerduty
  @pagerduty ||= Pagerduty.new(config[:pagerduty][:api_key])
end

def newer_appointment?
  earliest_appointment(refresh: true)["unix_time"] < config[:current_appointment]
end

def alert
  earliest = earliest_appointment
  incident = pagerduty.trigger(
    "New appointment available: #{earliest["appointmentFormatted"]}",
    incident_key: "new nbn appointment available",
    details: earliest,
  )
  puts "Triggered incident for new appointment: #{earliest["appointmentFormatted"]}"
end

def main
  alert if newer_appointment?
end

begin
  main if __FILE__ == $PROGRAM_NAME
rescue => e
  incident = pagerduty.trigger(
    "check_appointments.rb error",
    incident_key: "check_appointments.rb error",
    details: {
      exception: e.class,
      message: e.message,
      backtrace: e.backtrace.join("\n"),
    },
  )
  puts "Incident created for unhandled error"
  exit(1)
end
