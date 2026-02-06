# Setting Up the GitHub App

This guide walks through creating a GitHub App for automated org management.

## Why a GitHub App?

GitHub Apps provide scoped, short-lived tokens — more secure than personal access tokens. They also give a clear audit trail showing which automation made changes.

## Steps

### 1. Create the App

1. Go to **GitHub Settings** → **Developer settings** → **GitHub Apps** → **New GitHub App**
2. Fill in:
   - **Name**: `caelicode-org-manager` (or any unique name)
   - **Homepage URL**: Your repo URL
   - **Webhook**: Uncheck "Active" (not needed)
3. Set **Permissions**:

   | Permission | Access |
   |-----------|--------|
   | Members | Read & write |
   | Organization administration | Read & write |
   | Administration | Read & write |

4. Under **Where can this app be installed?** → select **Only on this account**
5. Click **Create GitHub App**

### 2. Generate a Private Key

1. On the app settings page, scroll to **Private keys**
2. Click **Generate a private key**
3. A `.pem` file downloads — keep this safe

### 3. Install the App

1. On the app page, click **Install App** in the sidebar
2. Select the **caelicode** organization
3. Choose **All repositories** or select specific repos
4. Click **Install**

### 4. Store Credentials

In your `github-user-management` repo:

1. Go to **Settings** → **Secrets and variables** → **Actions**
2. Create a **secret**: `ORG_MANAGER_PRIVATE_KEY`
   - Paste the entire contents of the `.pem` file
3. Go to the **Variables** tab
4. Create a **variable**: `ORG_MANAGER_APP_ID`
   - Set it to the App ID (found on the app's settings page)

### 5. Verify

Run the **Manual Sync** workflow with `dry_run: true` from the Actions tab. It should successfully authenticate and show the current org state.

## Alternative: Fine-Grained PAT

If you prefer not to create a GitHub App, you can use a fine-grained personal access token:

1. Go to **Settings** → **Developer settings** → **Personal access tokens** → **Fine-grained tokens**
2. Create a token scoped to the `caelicode` organization
3. Grant permissions: Organization (read & write), Members (read & write), Administration (read & write)
4. Store it as a repo secret: `ORG_MANAGER_PAT`
5. Update the workflow files to use the PAT instead of the GitHub App token

Note: With a PAT, you'll need to replace the `actions/create-github-app-token` step with a direct token reference.
