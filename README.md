# Govtools Posts Tracker

This tool tracks social media posts (currently X/Twitter) for a list of accounts, capturing a daily screenshot and metadata (posts count, bio, status).

## Setup

1.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    playwright install chromium
    ```

2.  **Configure Handles**:
    Add the social media handles you want to track to `USSTATE.csv`.
    The file should be a list of handles, one per line (header optional but recommended to be `handle`).

## Usage

Run the tracker:

```bash
python tracker.py
```

The script will:
1.  Read handles from `USSTATE.csv`.
2.  Create a daily output directory in `data/YYYY-MM-DD`.
3.  For each handle:
    - Visit the profile page.
    - Capture a screenshot of the top portion.
    - Extract post count, bio, and status.
    - Save the screenshot to `data/YYYY-MM-DD/screenshots/`.
    - Append the metadata to `data/YYYY-MM-DD/summary.csv`.

## Automation

To run this daily, you can set up a cron job or a GitHub Action.

### GitHub Action (Example)

Create `.github/workflows/daily.yml`:

```yaml
name: Daily Posts Tracker

on:
  schedule:
    - cron: '0 12 * * *' # Runs at 12:00 UTC every day
  workflow_dispatch:

jobs:
  track:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'
          
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          playwright install chromium
          
      - name: Run tracker
        run: python tracker.py
        
      - name: Commit and push changes
        run: |
          git config --global user.name 'github-actions[bot]'
          git config --global user.email 'github-actions[bot]@users.noreply.github.com'
          git add data/
          git commit -m "Daily tracking update $(date +'%Y-%m-%d')"
          git push
```
