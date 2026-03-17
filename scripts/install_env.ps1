python -m venv .venv
.\.venv\Scripts\pip.exe install --upgrade pip
.\.venv\Scripts\pip.exe install -r ..\requirements.txt
Write-Host "Virtual environment created at .venv. To activate run: .\scripts\activate.ps1"