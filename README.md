# LinkedIn Job Assistant

Local Python desktop software for:

- defining target role scopes like `Software Engineer`, `Full Stack Java Developer`, or `Front End Developer`
- searching LinkedIn jobs from a manually authenticated browser session
- qualifying roles against your filters
- drafting recruiter outreach and follow-up messages
- automating LinkedIn Easy Apply flows when the form is recognized
- classifying external ATS links and routing unsupported flows to review

## Quick start

1. Install Python 3.11+.
2. Create a virtual environment.
3. Install dependencies:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .[dev]
playwright install chromium
```

4. Launch the desktop app:

```powershell
linkedin-job-assistant
```

## Notes

- The app uses a manual LinkedIn login each run and does not store your raw LinkedIn password.
- Unsupported or ambiguous application questions are routed to `needs_review`.
- LinkedIn selectors and ATS flows are isolated inside dedicated services so they can be updated independently.
