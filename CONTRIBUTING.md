# Contributing

## Self-Service Onboarding

To join the `caelicode` organization:

1. Fork this repository
2. Add your username to `config/members.yml`:
   ```yaml
   members:
     # ... existing members ...
     - username: your-github-username
       role: member
   ```
3. Open a pull request
4. A maintainer will review and merge your PR
5. The automation sends you a GitHub org invitation — accept it

## Making Changes

All organization changes go through config files:

- **Members** → `config/members.yml`
- **Teams & permissions** → `config/teams.yml`
- **Repository settings** → `config/repositories.yml`

### Workflow

1. Create a branch and edit the relevant config file(s)
2. Open a PR — the Plan workflow posts a comment showing what will change
3. Review the plan to make sure it's correct
4. Get approval from a maintainer
5. Merge — the Apply workflow syncs the org automatically

### Validation

Config files are validated automatically:
- Schema validation (correct structure and field types)
- Cross-reference checks (team members exist in members list, etc.)
- Free tier warnings (branch protection on private repos, etc.)

If validation fails, the PR check will fail with specific error messages.

## Development

### Local Testing

```bash
# Install dependencies
pip install pyyaml jsonschema requests

# Validate config only (no GitHub API calls)
PYTHONPATH=scripts python scripts/plan.py --validate-only

# Dry-run plan (requires GITHUB_TOKEN)
export GITHUB_TOKEN="your_token"
PYTHONPATH=scripts python scripts/plan.py

# Dry-run apply
PYTHONPATH=scripts python scripts/apply.py --dry-run
```

### Running Tests

```bash
pip install pytest
pytest tests/
```
