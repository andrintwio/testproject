# TW Module Catalog

A technical tool designed to aggregate and analyze Odoo modules across multiple GitHub repositories. It provides a centralized repository of technical metadata, dependency analysis, and module similarity detection.

## Features

- **GitHub Repository Scanning**: Automatically scans repositories within a configured GitHub Organization to identify Odoo modules.
- **Manifest Parsing**: Extracts metadata from `__manifest__.py` including dependencies, authorship, summary, and versioning.
- **Pillar Hashing System**: Implements a 5-pillar hashing algorithm to identify identical or derivative modules across different repositories:
    1. **Functional Identity**: name + depends
    2. **Structural Identity**: name + data files
    3. **Intent**: summary
    4. **Origin**: name + author
    5. **Technical DNA**: depends + data files
- **Similarity Detection**: Uses a "3/5 match" heuristic on pillar hashes to group modules into "Clusters" and identify siblings.
- **Dependency Tagging**: Automatically generates and assigns tags based on module dependencies using regex parsing.
- **README/Description Extraction**: Converts `README.md`, `README.rst`, and `index.html` into searchable HTML content.
- **Usage Tracking**: Allows users to "bookmark" modules they have used, providing a popular/usage-based sorting.
- **Blacklist Management**: Allows exclusion of specific repositories from the catalog.

## Installation

1. Install the `tw_module_catalog` module.
2. Ensure Python dependencies are met: `PyGithub`, `markdown`, `docutils`.
3. The module depends on `tw_infrastructure` for security groups and `mail` for communication features.

## Configuration

1. **GitHub Token**: Go to **Settings > Technical > System Parameters** and set the key `twio.github_token` with a valid Fine-grained or Classic GitHub Personal Access Token.
2. **Organization**: The default organization is currently hardcoded to `twio-tech` in `tw_module_catalog.py`.
3. **Blacklist**: Go to **Configuration > Repository Blacklist** to add repository names that should be ignored during sync.

## Usage

- **Execution timing**: GitHub sync only runs during nighttime (00:00 - 05:00 UTC) to avoid performance impact. This check can be bypassed via the manual sync button.

### Syncing the Catalog

The catalog can be updated in two ways:.
1. **Scheduled Sync**: Uses a cron job to process repositories in bursts (restricted to 00:00 - 05:00 UTC).

### Analyzing Clusters

Navigate to a module form to see the **Related Modules** tab. This shows "Siblings" found in other repositories based on the Cluster ID (generated from the pillar hashes).

## Cron Job

The module includes a scheduled action **"GitHub Module Catalog: Sync"**:
- **Execution Interval**: Every 12 hours (default).
- **Batch Processing**: Processes repositories in bursts of 10 to avoid GitHub API rate limits and long-running transaction timeouts.
- **Sync Threshold**: Only re-scans repositories if they haven't been scanned in the last 12 hours or if they were never scanned.

## Logic
Discovery:
- Scans all repos
- Checks if repo was already scanned in the last 12 hours
    - If not, it will fetch the repo and check for modules
    - The Sync Queue checks if a module found by the Discoverer is already in the catalog or in the queue
        - If model is already in catalog with matching module_sha we skip.
        - If model is already pending and the SHA matches, we do nothing.
        - If model is in catalog but with different sha we update the queue entry.
        - If model is not in catalog and not in queue we add it to the queue
