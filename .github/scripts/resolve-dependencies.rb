#!/usr/bin/env ruby
# Resolve requested resources and their prerequisites into a stable topological order.
require "yaml"

path = ".github/deploy/dependencies.yaml"
known_resources = %w[vpc s3 ec2 ecs]

begin
  document = YAML.safe_load_file(path, permitted_classes: [], aliases: false)
  graph = document.fetch("dependencies")
rescue StandardError => error
  abort "Cannot read #{path}: #{error.message}"
end

unless graph.is_a?(Hash) && graph.keys.all? { |name| name.is_a?(String) }
  abort "dependencies.yaml must contain a 'dependencies' mapping"
end

missing = known_resources - graph.keys
unknown = graph.keys - known_resources
abort "Missing resources in dependencies.yaml: #{missing.join(', ')}" unless missing.empty?
abort "Unsupported resources in dependencies.yaml: #{unknown.join(', ')}" unless unknown.empty?

graph.each do |resource, dependencies|
  unless dependencies.is_a?(Array) && dependencies.all? { |name| name.is_a?(String) }
    abort "Dependencies for '#{resource}' must be a list of resource names"
  end
  abort "Duplicate dependency listed for '#{resource}'" unless dependencies.uniq == dependencies
  unknown_dependencies = dependencies - graph.keys
  unless unknown_dependencies.empty?
    abort "Unknown dependencies for '#{resource}': #{unknown_dependencies.join(', ')}"
  end
end

# Topologically sort the complete graph, using YAML insertion order to break ties.
pending = graph.keys.dup
ordered = []
until pending.empty?
  ready = pending.find { |resource| (graph.fetch(resource) & pending).empty? }
  abort "Dependency cycle detected in #{path}" unless ready

  ordered << ready
  pending.delete(ready)
end

requested = ARGV.fetch(0, "")
if requested.empty?
  selected = []
elsif requested == "all"
  selected = graph.keys.dup
else
  selected = requested.split(",").uniq
  unknown_targets = selected - graph.keys
  abort "Unknown requested resources: #{unknown_targets.join(', ')}" unless unknown_targets.empty?
end

# Deploy prerequisites of every changed/selected target too.
include_dependencies = lambda do |resource|
  return if selected.include?(resource)

  selected << resource
  graph.fetch(resource).each { |dependency| include_dependencies.call(dependency) }
end
requested_targets = requested == "all" ? graph.keys.dup : requested.split(",").uniq
requested_targets.each { |resource| include_dependencies.call(resource) }

puts ordered.select { |resource| selected.include?(resource) }.join(",")
