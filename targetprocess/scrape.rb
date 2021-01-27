$LOAD_PATH << File.join(File.dirname(__FILE__), "lib")
require "tp"
require "dotenv"

Dotenv.load

config = {
  subdomain: ENV["TP_SUBDOMAIN"],
  token: ENV["TP_TOKEN"],
  session_cookie: ENV["TP_SESSION_COOKIE"],
}

if config.map { |k, v| v.nil? ? k : nil }.any?
  print "Invalid configuration. Missing keys: "
  puts config.map { |k, v| v.nil? ? k : nil }.compact
  exit 1
end

tp = TargetProcess.new(config)

mod_squad_user_stories = tp.user_stories(where: "Project.Id eq 6429", take: 1000)

mod_squad_user_stories.each do |us|
  category = tp.last_work_category_change(id: us["Id"])
  if category
    formatted = [category["EntityID"], (category["NewValue"] || category["OldValue"])]
  else
    formatted = [us["Id"], "nil"]
  end
  puts formatted.join(",")
end

exit
