# Lowe's Return Timeframe Lookup

A FastAPI + Playwright web application that accepts a Lowe's Item # or Manufacturer Model #, searches Lowe's, identifies the product, and maps the product information to Lowe's return-policy rules.

## 1. Run on Windows

Open PowerShell in this project folder:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
uvicorn app.main:app --reload
```

Then open:

http://127.0.0.1:8000

If PowerShell blocks activation, run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.venv\Scripts\Activate.ps1
```

## 2. Test

Try a Lowe's Item # or Model # in the search box.

The backend searches the Lowe's search page with Playwright, opens the first product page it finds, extracts product information, and applies the policy engine.

## 3. Deploy

This project includes a Dockerfile and Render configuration.

A practical deployment flow is:

1. Create a GitHub repository.
2. Upload this project.
3. Create a new Web Service on Render.
4. Connect the repository.
5. Select Docker.
6. Deploy.

The browser is installed inside the Docker image, so Playwright can run on the server.

## Important production note

Lowe's can change its website structure, bot protections, product pages, and return policy. The scraper may need maintenance when the website changes.

The policy rules in `app/policy.py` are intentionally explicit rather than using an LLM to guess return windows. Before using the application for real customer decisions, compare the displayed result with the current Lowe's policy page and keep the rules synchronized.

Official policy:
https://www.lowes.com/l/help/returns-policy
