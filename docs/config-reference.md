# Configuration Reference

All config files use YAML format and are validated against JSON schemas in the `schemas/` directory.

## `config/org.yml`

Organization-level settings.

```yaml
organization:
  name: caelicode           # Required — GitHub org name
  default_member_role: member  # Default role for new members
```

## `config/members.yml`

Organization member roster.

```yaml
members:
  - username: alice          # GitHub username (required)
    role: admin              # admin | member (required)
  - username: bob
    role: member
```

**Roles:**

| Role | Description |
|------|-------------|
| `admin` | Full org admin — can manage settings, billing, teams |
| `member` | Standard org member |

**Username format:** Alphanumeric characters and hyphens. No leading or trailing hyphens.

## `config/teams.yml`

Team definitions with membership and repository access.

```yaml
teams:
  team-name:                  # Team name (becomes the slug)
    description: "..."        # Team description (required)
    privacy: closed           # closed | secret (required)
    members:                  # Team members (optional)
      - username: alice
        role: maintainer      # maintainer | member
      - username: bob
        role: member
    repos:                    # Repository permissions (optional)
      repo-name: push         # pull | triage | push | maintain | admin
```

**Privacy:**

| Value | Description |
|-------|-------------|
| `closed` | Visible to all org members |
| `secret` | Only visible to team members and org owners |

**Team member roles:**

| Role | Description |
|------|-------------|
| `maintainer` | Can manage team settings and membership |
| `member` | Standard team member |

**Repository permissions:**

| Level | Description |
|-------|-------------|
| `pull` | Read-only access |
| `triage` | Read + manage issues and PRs |
| `push` | Read + write access |
| `maintain` | Push + manage repo settings (not admin) |
| `admin` | Full repository admin |

## `config/repositories.yml`

Repository settings and branch protection rules.

```yaml
repositories:
  repo-name:
    description: "..."        # Repo description
    visibility: public        # public | private
    default_branch: main      # Default branch name
    features:
      has_issues: true
      has_wiki: false
      has_projects: false
    branch_protection:         # Branch protection (public repos only!)
      main:
        required_reviews: 1
        dismiss_stale_reviews: true
        require_status_checks: false
        required_status_contexts: []
        enforce_admins: false
        restrict_pushes: false
```

**Branch protection fields:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `required_reviews` | int (1-6) | 1 | Required approving reviews |
| `dismiss_stale_reviews` | bool | true | Dismiss reviews when new commits push |
| `require_status_checks` | bool | false | Require status checks to pass |
| `required_status_contexts` | list | [] | Specific status checks required |
| `enforce_admins` | bool | false | Include administrators in restrictions |
| `restrict_pushes` | bool | false | Restrict who can push to the branch |

**Important:** Branch protection is only available on **public repositories** with the GitHub Free plan. Rules for private repos will be skipped with a warning.

## Validation

Configs are validated in two ways:

1. **Schema validation** — checks structure and field types against JSON schemas
2. **Cross-reference checks**:
   - Team members must exist in `members.yml`
   - Repos referenced in teams generate warnings if not in `repositories.yml`
   - Branch protection on private repos generates a warning
   - Members not in any team generate a warning
   - Duplicate usernames/team members are flagged as errors
