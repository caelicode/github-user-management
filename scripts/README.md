# GitHub User Management Scripts

This directory contains modular scripts for managing GitHub users in the CDCgov organization.

## Structure

The scripts are organized in a modular structure for better maintainability and reusability:

- `remove_github_users.py`: Main script entry point for removing users from CDCgov organization
- `main.py`: Newer alternative entry point with the same functionality
- `github_client.py`: GitHub API client with reusable functions for organization management
- `utils.py`: General utilities for logging, file handling, and data processing
- `workflow_utils.py`: Utilities for GitHub Actions workflow integration

## Usage

### Environment Variables

- `GITHUB_TOKEN`: GitHub API token with organization admin permissions
- `CALLBACK_TOKEN`: GitHub token for sending dispatches to other repositories
- `TEST_MODE`: Set to "true" to run in test mode (no actual removals)
- `USERNAMES_JSON`: JSON array of GitHub usernames to process
- `ORG_NAME`: (Optional) Name of the GitHub organization (defaults to "cdcgov")
- `TARGET_BRANCH`: (Optional) Branch to target in callbacks (defaults to "main")

### Basic Usage

```bash
# Set required environment variables
export GITHUB_TOKEN="your_github_token"
export CALLBACK_TOKEN="your_callback_token"
export TEST_MODE="true"
export USERNAMES_JSON='["username1", "username2"]'

# Run the script
python remove_github_users.py
```

### From GitHub Actions Workflow

```yaml
- name: Execute User Removal Script
  env:
    GITHUB_TOKEN: ${{ steps.generate-token.outputs.token }}
    CALLBACK_TOKEN: ${{ secrets.CALLBACK_TOKEN }}
    TEST_MODE: ${{ env.TEST_MODE }}
    USERNAMES_JSON: ${{ env.USERNAMES_JSON }}
  run: |
    python scripts/remove_github_users.py
```

## Output

The script produces:
- Detailed logs to both console and a timestamped log file
- A JSON file with detailed results
- GitHub Actions step summary (when running in GitHub Actions)
- A callback dispatch to update user lists in the cdcent/ocio-github-infra repository

## Error Handling

- Non-zero exit code when any user removal fails
- Detailed error messages for each failure
- Support for GitHub's rate limiting and API error responses
