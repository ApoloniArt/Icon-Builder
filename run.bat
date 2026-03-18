@echo off
cd /d "%~dp0"

:: ============================================================
:: IconTool - one-click build
:: ============================================================
::
:: READ THIS BEFORE RUNNING — choose one of the three options
:: below and delete or comment out the other two.
::
:: ── OPTION 1: System Python ─────────────────────────────────
:: Use this if you installed Python from python.org
:: First run:  pip install pillow pywin32
::
::   python icon_tool.py build
::
:: ── OPTION 2: ComfyUI embedded Python (direct path) ─────────
:: Replace the path below with your actual ComfyUI location.
:: First run:  D:\ComfyUI_windows_portable\python_embeded\python.exe -m pip install pillow pywin32
::
::   D:\ComfyUI_windows_portable\python_embeded\python.exe icon_tool.py build
::
:: ── OPTION 3: pathtomain helper (advanced, multiple installs)─
:: Use this if you have a pathtomain.bat set up on your PATH.
:: See README.md Option B2 for setup instructions.
::
::   call pathtomain
::   python icon_tool.py build
::
:: ============================================================
:: DELETE EVERYTHING ABOVE THIS LINE ONCE CONFIGURED
:: ============================================================

:: Currently set to Option 3 (pathtomain) -- change to match your setup
call pathtomain
python icon_tool.py build

pause
