# Odoo.sh Monitoring Module

Monitor Odoo.sh repositories and branches from Odoo.

## Features

- **Hourly Cron Job**: Automatically syncs repositories and branches every hour
- **Knowledge Page**: Displays all repositories and branches with interactive dropdowns
- **Data Storage**: All data is stored directly in Knowledge articles

## Installation

1. Place the module in your Odoo addons directory
2. Update the apps list
3. Install "Odoo.sh Monitoring"

## Configuration

1. Go to **Settings > Odoo.sh Monitoring**
2. Configure the **Project ID** (default: 359937)
3. Configure the **Session ID** (get it from your Odoo.sh session)
4. Click "Sync Now" to sync manually or wait for the cron job

## Usage

### View Repositories in Knowledge

1. Go to the **Knowledge** app
2. Find the article "Odoo.sh Repository Monitoring"
3. Click "Refresh Display" to reload the data
4. Expand each repository to see its branches

## Cron Job

The cron job runs automatically every hour. Check its status at:
**Settings > Technical > Automation > Scheduled Actions**
