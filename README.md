# GitHub Organization Management — GitOps

Manage your GitHub organization as code. Define members, teams, repositories, and branch protection in YAML config files. Changes are applied automatically via GitHub Actions when you merge to `main`.

## How It Works

```
config/members.yml  ──┐
config/teams.yml    ──┤──→  PR (plan preview)  ──→  Merge  ──→  GitHub API sync
config/repos.yml    ──┘                                          ↑
                                                    Drift detection (scheduled)
```

1. **Edit config files** — add members, create teams, set permissions
2. **Open a PR** — a plan comment shows exactly what will change (Terraform-style)
3. **Merge to main** — the Apply workflow syncs the org to match config
4. **Drift detection** — a scheduled check catches manual changes made outside config

## Quick Start

### 1. Set Up Authentication

Create a [GitHub App](docs/setup-github-app.md) for the `caelicode` org with these permissions:
- Members: read & write
- Organization: read & write
- Administration: read & write

Store the credentials as repo secrets:
- `ORG_MANAGER_PRIVATE_KEY` — the app's private key
- `ORG_MANAGER_APP_ID` — set as a repository **variable** (not secret)

### 2. Configure Your Org

Edit the YAML files in `config/`:

**Add members** (`config/members.yml`):
```yaml
members:
  - username: alice
    role: admin
  - username: bob
    role: member
```

**Create teams** (`config/teams.yml`):
```yaml
teams:
  backend:
    description: "Backend engineering"
    privacy: closed
    members:
      - username: alice
        role: maintainer
      - username: bob
        role: member
    repos:
      api-service: push
```

**Set branch protection** (`config/repositories.yml`):
```yaml
repositories:
  api-service:
    description: "Main API"
    visibility: public
    branch_protection:
      main:
        required_reviews: 1
        dismiss_stale_reviews: true
```

### 3. Push and Sync

```bash
git add config/
git commit -m "Initial org setup"
git push origin main
```

The Apply workflow runs automatically and syncs your GitHub org.

## Workflows

| Workflow | Trigger | What it does |
|----------|---------|-------------|
| **Plan** | PR to `config/**` | Posts a plan comment on the PR showing adds/removes/changes |
| **Apply** | Push to `main` (config changes) | Syncs the org — applies all config changes |
| **Drift Detection** | Every 12 hours (scheduled) | Checks for manual changes, opens/closes an issue |
| **Manual Sync** | Manual trigger (Actions UI) | On-demand sync with optional dry-run mode |

## PR Plan Preview

When you open a PR that touches config files, a comment like this appears:

```
## Organization Sync Plan

3 to add, 1 to change, 0 to remove

### Members
+ Invite `charlie` as `member`

### Teams
+ Create team `frontend` (closed)
~ Update `backend` description

### Team Permissions
+ Grant `frontend` → `web-app` (push)
```

## Repository Structure

```
config/              ← Your org configuration (edit these)
├── org.yml          ← Organization name
├── members.yml      ← Member roster with roles
├── teams.yml        ← Teams, membership, repo access
└── repositories.yml ← Repo settings, branch protection

schemas/             ← JSON Schema validation
scripts/             ← Python automation engine
.github/workflows/   ← GitHub Actions (plan, apply, drift, manual)
docs/                ← Setup guides and references
```

## Free Tier Constraints

This project is designed for GitHub Free organizations:

| Feature | Free Plan Support |
|---------|------------------|
| Org member management | Yes |
| Team management | Yes |
| Team-repo permissions | Yes |
| Branch protection (public repos) | Yes |
| Branch protection (private repos) | No — requires paid plan |
| GitHub Actions | Unlimited for public repos, 2000 min/month for private |

Branch protection rules on private repos are automatically skipped with a warning.

## Self-Service Onboarding

New members can join the org by opening a PR that adds their username to `config/members.yml`. A maintainer reviews and merges — the Apply workflow handles the GitHub invitation automatically.

## Security

- All changes are version-controlled and auditable via git history
- PR plan previews prevent accidental changes
- Drift detection catches unauthorized manual modifications
- Audit logs are uploaded as workflow artifacts (90-day retention)
- Branch protection warnings flag public repos without protection

<!-- DASHBOARD_START -->
<!-- DASHBOARD_END -->
