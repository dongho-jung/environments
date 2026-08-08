resource "host_link" "capelabs_jira_skill" {
  for_each = {
    claude = "~/.claude/skills/capelabs-jira"
    codex  = "~/.codex/skills/capelabs-jira"
  }

  source       = "skills/capelabs-jira"
  destination  = each.value
  stage_source = true
}
