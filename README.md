# GitHub Organization Management — GitOps

Manage your GitHub organization as code. Define members, teams, repositories, and branch protection in YAML config files. Changes are applied automatically via GitHub Actions when you merge to `main`.

## How It Works

```
config/members.yml      ──┐
config/teams.yml        ──┤──→  PR (plan preview)  ──→  Merge  ──→  GitHub API sync
config/repositories.yml ──┘                                          ↑
                                                        Drift detection (scheduled)
                                                        Auto-protect (scheduled)
```

1. **Edit config files** — add members, create teams, set permissions
2. **Open a PR** — a plan comment shows exactly what will change (Terraform-style)
3. **Merge to main** — the Apply workflow syncs the org to match config
4. **Drift detection** — a scheduled check catches manual changes made outside config
5. **Auto-protect** — new public repos get default branch protection automatically

## Quick Start

### 1. Set Up Authentication

Create a [GitHub App](docs/setup-github-app.md) for your org with these permissions:
- Members: read & write
- Organization: read & write
- Administration: read & write

Store the credentials:
- `ORG_MANAGER_PRIVATE_KEY` — the app's private key (repo secret)
- `ORG_MANAGER_APP_ID` — the app's ID (repo variable)

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
| **Drift Detection** | Every 12 hours | Checks for manual changes, opens/closes an issue |
| **Auto-Protect** | Every 6 hours + after sync | Applies default branch protection to unmanaged public repos |
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
config/                  ← Your org configuration (edit these)
├── org.yml              ← Organization name
├── members.yml          ← Member roster with roles
├── teams.yml            ← Teams, membership, repo access
└── repositories.yml     ← Repo settings, branch protection

schemas/                 ← JSON Schema validation
scripts/                 ← Python automation engine
.github/workflows/       ← GitHub Actions (plan, apply, drift, auto-protect, manual)
docs/                    ← Setup guides and references
tests/                   ← Config loader and reconciler tests
archive/                 ← Legacy CDC removal scripts (reference only)
```

## Security

- All changes are version-controlled and auditable via git history
- PR plan previews prevent accidental changes
- Drift detection catches unauthorized manual modifications
- Auto-protect ensures new repos don't go unprotected
- Audit logs are uploaded as workflow artifacts (90-day retention)
- Security audit flags unprotected public repos, excessive admins, stale teams

<!-- DASHBOARD_START -->
<!-- DASHBOARD_END -->
