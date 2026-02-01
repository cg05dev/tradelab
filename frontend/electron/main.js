import { app, BrowserWindow } from 'electron'
import path from 'path'
import { spawn } from 'child_process'
import fs from 'fs'
import { fileURLToPath } from 'url'
import http from 'http'

// Get __dirname equivalent in ES modules
const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

let mainWindow = null
let backendProcess = null
let frontendProcess = null
let healthCheckInterval = null
let cleanupTimeouts = []

// Paths
const isDev = !app.isPackaged || process.env.NODE_ENV === 'development'
// __dirname in Electron main process points to the electron folder
const backendPath = isDev 
  ? path.resolve(__dirname, '../../backend')
  : path.join(process.resourcesPath, 'backend')
const frontendPath = path.resolve(__dirname, '..')

console.log('Electron starting...')
console.log('isDev:', isDev)
console.log('__dirname:', __dirname)
console.log('backendPath:', backendPath)
console.log('frontendPath:', frontendPath)

// Start backend server
function startBackend() {
  return new Promise((resolve, reject) => {
    const venvPython = path.join(backendPath, 'venv', 'Scripts', 'python.exe')
    const pythonPath = fs.existsSync(venvPython) ? venvPython : 'python'
    const mainPy = path.join(backendPath, 'main.py')
    
    console.log('Starting backend server...')
    console.log('Backend path:', backendPath)
    console.log('Python path:', pythonPath)
    
    backendProcess = spawn(pythonPath, [mainPy], {
      cwd: backendPath,
      shell: true,
      stdio: 'pipe',
      env: { ...process.env }
    })

    let backendReady = false

    // Try to detect backend ready via health check
    const checkHealth = () => {
      if (backendReady) return
      
      try {
        const req = http.get('http://127.0.0.1:8000/health', { timeout: 500 }, (res) => {
          if (res.statusCode === 200 && !backendReady) {
            backendReady = true
            console.log('Backend server started! (health check passed)')
            resolve()
          }
        })
        req.on('error', () => {
          // Backend not ready yet, will retry
        })
        req.on('timeout', () => {
          req.destroy()
        })
      } catch (err) {
        // Ignore errors, will retry or timeout
      }
    }

    // Start checking health after 500ms, then every 200ms
    const healthCheckTimeout = setTimeout(() => {
      healthCheckInterval = setInterval(() => {
        if (backendReady) {
          clearInterval(healthCheckInterval)
          healthCheckInterval = null
          return
        }
        checkHealth()
      }, 200)
      
      // Clear interval after timeout
      const clearIntervalTimeout = setTimeout(() => {
        if (healthCheckInterval) {
          clearInterval(healthCheckInterval)
          healthCheckInterval = null
        }
      }, 2000)
      cleanupTimeouts.push(clearIntervalTimeout)
    }, 500)
    cleanupTimeouts.push(healthCheckTimeout)

    backendProcess.stdout.on('data', (data) => {
      const output = data.toString()
      console.log(`Backend: ${output}`)
      // Also check for uvicorn startup messages
      if ((output.includes('Uvicorn running') || output.includes('Application startup complete')) && !backendReady) {
        backendReady = true
        console.log('Backend server started!')
        resolve()
      }
    })

    backendProcess.stderr.on('data', (data) => {
      const output = data.toString()
      console.error(`Backend error: ${output}`)
      // Some Python output goes to stderr but isn't an error
      if ((output.includes('Uvicorn running') || output.includes('Application startup complete')) && !backendReady) {
        backendReady = true
        console.log('Backend server started!')
        resolve()
      }
    })

    backendProcess.on('error', (error) => {
      console.error('Failed to start backend:', error)
      if (!backendReady) {
        reject(error)
      }
    })

    // Timeout after 2 seconds - assume it started (faster startup)
    setTimeout(() => {
      if (!backendReady) {
        console.log('Backend startup timeout - assuming it started')
        backendReady = true
        resolve()
      }
    }, 2000)
  })
}

// Start frontend dev server (only in development)
function startFrontend() {
  if (!isDev) return Promise.resolve()

  return new Promise((resolve) => {
    console.log('Starting frontend dev server...')
    frontendProcess = spawn('npm', ['run', 'dev'], {
      cwd: frontendPath,
      shell: true,
      stdio: 'pipe'
    })

    frontendProcess.stdout.on('data', (data) => {
      const output = data.toString()
      console.log(`Frontend: ${output}`)
      if (output.includes('Local:') || output.includes('localhost:3001') || output.includes('127.0.0.1:3001')) {
        // Resolve immediately - no need to wait
        resolve()
      }
    })

    frontendProcess.stderr.on('data', (data) => {
      console.error(`Frontend error: ${data}`)
    })

    // Timeout after 3 seconds (faster startup)
    setTimeout(() => {
      console.log('Frontend dev server timeout - assuming it started')
      resolve()
    }, 3000)
  })
}

// Create the main window
function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1000,
    minHeight: 700,
    backgroundColor: '#000000',
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      webSecurity: true,
      spellcheck: false,
      enableRemoteModule: false,
      sandbox: false
    },
    titleBarStyle: 'default',
    show: false // Don't show until ready
  })

  // Load the app
  if (isDev) {
    // In development, load from Vite dev server
    // Retry loading until successful (frontend might not be ready yet)
    const tryLoadURL = () => {
      console.log('Loading from Vite dev server: http://127.0.0.1:3001')
      mainWindow.loadURL('http://127.0.0.1:3001').catch(err => {
        console.log('Frontend not ready yet, retrying in 300ms...')
        setTimeout(tryLoadURL, 300)
      })
    }
    tryLoadURL()
    // DevTools disabled for cleaner experience (can be opened with F12 if needed)
    // mainWindow.webContents.openDevTools()
  } else {
    // In production, load from built files
    const indexPath = path.join(__dirname, '../dist/index.html')
    console.log('Loading from file:', indexPath)
    mainWindow.loadFile(indexPath).catch(err => {
      console.error('Failed to load file:', err)
    })
  }

  // Show window when ready
  mainWindow.once('ready-to-show', () => {
    mainWindow.show()
    mainWindow.focus()
  })

  // Handle window closed
  mainWindow.on('closed', () => {
    mainWindow = null
  })
}

// App lifecycle
app.whenReady().then(async () => {
  try {
    // Create window immediately for faster perceived startup
    createWindow()
    
    // Start backend and frontend in parallel (don't wait - let them start in background)
    // This allows the window to show immediately while services start
    Promise.all([
      startBackend().catch(err => console.error('Backend start error:', err)),
      isDev ? startFrontend().catch(err => console.error('Frontend start error:', err)) : Promise.resolve()
    ]).then(() => {
      console.log('All services started!')
    })
  } catch (error) {
    console.error('Failed to start services:', error)
    // Window should already be created, so user can see the app
  }
})

// Helper function to stop all processes
function stopAllProcesses() {
  console.log('Stopping all processes...')
  
  // Clear all intervals and timeouts
  if (healthCheckInterval) {
    clearInterval(healthCheckInterval)
    healthCheckInterval = null
  }
  cleanupTimeouts.forEach(timeout => clearTimeout(timeout))
  cleanupTimeouts = []
  
  // Stop backend
  if (backendProcess && !backendProcess.killed) {
    console.log('Stopping backend server...')
    try {
      backendProcess.kill('SIGTERM')
      // Force kill after 1 second if still running
      const killTimeout = setTimeout(() => {
        if (backendProcess && !backendProcess.killed) {
          console.log('Force killing backend server...')
          backendProcess.kill('SIGKILL')
        }
      }, 1000)
      cleanupTimeouts.push(killTimeout)
    } catch (error) {
      console.error('Error stopping backend:', error)
    }
  }
  
  // Stop frontend dev server
  if (frontendProcess && !frontendProcess.killed) {
    console.log('Stopping frontend dev server...')
    try {
      frontendProcess.kill('SIGTERM')
      // Force kill after 500ms if still running
      const killTimeout = setTimeout(() => {
        if (frontendProcess && !frontendProcess.killed) {
          console.log('Force killing frontend dev server...')
          frontendProcess.kill('SIGKILL')
        }
      }, 500)
      cleanupTimeouts.push(killTimeout)
    } catch (error) {
      console.error('Error stopping frontend:', error)
    }
  }
}

app.on('window-all-closed', () => {
  // Stop all processes when window closes
  stopAllProcesses()
  
  // On macOS, keep app running even when all windows are closed
  if (process.platform !== 'darwin') {
    // Give processes time to clean up, then exit
    setTimeout(() => {
      process.exit(0)
    }, 1500)
  }
})

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow()
  }
})

// Handle app quit
app.on('before-quit', (event) => {
  // Stop all processes
  stopAllProcesses()
  
  // Force exit after cleanup
  setTimeout(() => {
    process.exit(0)
  }, 1500)
})

// Handle uncaught exceptions
process.on('uncaughtException', (error) => {
  console.error('Uncaught exception:', error)
})
