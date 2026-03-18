# Desktop Cleanup Worker

## Purpose
Remove Electron/desktop-specific files and verify browser-only startup works.

## Procedure

1. **Baseline verification**
   - Run `npm run dev` (or equivalent) from frontend; verify current startup
   - Capture current port usage and process names
   - Document which files are desktop-specific (Electron main, installers, launchers)

2. **Desktop file removal**
   - Remove Electron main process files (`electron/` directory or `main.js` for Electron)
   - Remove installer/build scripts for desktop (`build_setup_exe.bat`, `setup.py`, `TradeLab-Setup.*`)
   - Remove desktop launcher scripts (`*.vbs`, `*.bat`, `*.ps1` for desktop startup)
   - Remove `electron` from `package.json` dependencies and scripts
   - Remove Electron-specific Vite config (`base: './'` for Electron)
   - Commit removal with clear message

3. **Browser-only startup verification**
   - Start backend: `cd backend && python main.py` (port 8000)
   - Start frontend: `cd frontend && npm run dev` (port 3001)
   - Open browser to `http://127.0.0.1:3001`
   - Verify app loads and API calls succeed
   - Verify no Electron process appears

4. **Documentation**
   - Update README with browser-only startup instructions
   - Remove desktop-specific documentation sections

5. **Handoff**
   - Return summary of removed files
   - Return verification that browser startup works
   - Note any desktop files that were kept (with rationale)
