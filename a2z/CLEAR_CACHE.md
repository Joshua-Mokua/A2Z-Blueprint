# Clearing Python cache (run before starting)

## PowerShell (Windows — recommended)
```powershell
Remove-Item -Recurse -Force pages\__pycache__ -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force utils\__pycache__ -ErrorAction SilentlyContinue
streamlit run app.py
```

## Command Prompt (Windows)
```cmd
rmdir /s /q pages\__pycache__ 2>nul
rmdir /s /q utils\__pycache__ 2>nul
streamlit run app.py
```

## macOS / Linux
```bash
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; streamlit run app.py
```
