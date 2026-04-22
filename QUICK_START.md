# A2Z Blueprint — Quick Start (Local)

## Run the system

Double-click **run.bat**

Or from terminal:
```
cd "C:\Users\Joshua\Desktop\A2Z Blue Print\a2z"
.venv\Scripts\activate
streamlit run app.py
```

Then open: http://localhost:8501

## Login credentials

| Role | Username | Password |
|---|---|---|
| MD / Full Admin | william001 | Staff0001 |
| System Admin | admin | admin123 |
| CFO | yasmin004 | Staff0004 |
| CCO (Credit) | gregory005 | Staff0005 |
| Any staff | firstname + last 3 digits of staff code | Staff + last 4 digits |

## Key facts

- 67 modules across 22 departments
- 1,438 users with role-based access
- All data lives in `data/` folder as JSON files
- No internet connection needed to run locally

## Before a presentation

1. Run it locally and confirm login works
2. Clear browser cache (Ctrl+Shift+Delete)
3. Open in a clean browser window
4. Log in as william001 to show the full MD view

## Git commands (when ready to push)

```bash
git add .
git commit -m "your message"
git push origin main
```
