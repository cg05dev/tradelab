# PowerShell script to launch TradeLab Desktop App hidden
# Add Windows Forms for message boxes
Add-Type -AssemblyName System.Windows.Forms

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$frontendDir = Join-Path $scriptDir "frontend"

# Check if Node.js is installed
try {
    $null = Get-Command node -ErrorAction Stop
} catch {
    [System.Windows.Forms.MessageBox]::Show("Node.js is not installed or not in PATH. Please install Node.js from https://nodejs.org/", "TradeLab Error", "OK", "Error")
    exit 1
}

# Check if frontend directory exists
if (-not (Test-Path $frontendDir)) {
    [System.Windows.Forms.MessageBox]::Show("Frontend directory not found! Expected: $frontendDir", "TradeLab Error", "OK", "Error")
    exit 1
}

# Check if Electron is installed
$electronPath = Join-Path $frontendDir "node_modules\electron"
if (-not (Test-Path $electronPath)) {
    # Install dependencies
    Push-Location $frontendDir
    try {
        $installProcess = Start-Process -FilePath "npm" -ArgumentList "install" -WorkingDirectory $frontendDir -WindowStyle Hidden -Wait -PassThru
        if ($installProcess.ExitCode -ne 0) {
            [System.Windows.Forms.MessageBox]::Show("Failed to install Electron dependencies. Please run: cd frontend && npm install", "TradeLab Error", "OK", "Error")
            Pop-Location
            exit 1
        }
    } catch {
        [System.Windows.Forms.MessageBox]::Show("Failed to install dependencies: $_", "TradeLab Error", "OK", "Error")
        Pop-Location
        exit 1
    }
    Pop-Location
}

# Start Electron app (this will show the Electron window, but not a console)
Push-Location $frontendDir
try {
    # Use cmd.exe to run npm - more reliable than running npm directly
    # When Electron exits, npm will exit, and cmd will exit too
    $processInfo = New-Object System.Diagnostics.ProcessStartInfo
    $processInfo.FileName = "cmd.exe"
    $processInfo.Arguments = "/c npm run electron:dev"
    $processInfo.WorkingDirectory = $frontendDir
    $processInfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
    $processInfo.UseShellExecute = $false
    $processInfo.CreateNoWindow = $true
    
    $electronProcess = New-Object System.Diagnostics.Process
    $electronProcess.StartInfo = $processInfo
    $electronProcess.Start() | Out-Null
    
    if ($null -eq $electronProcess -or $electronProcess.HasExited) {
        throw "Failed to start Electron process"
    }
    
    # Wait for Electron to exit
    $electronProcess.WaitForExit()
    
    # Exit immediately with the same code
    $exitCode = if ($electronProcess.HasExited) { $electronProcess.ExitCode } else { 0 }
    exit $exitCode
} catch {
    $errorMsg = if ($null -ne $_) { $_.ToString() } else { "Unknown error" }
    [System.Windows.Forms.MessageBox]::Show("Failed to start Electron: $errorMsg", "TradeLab Error", "OK", "Error")
    Pop-Location
    exit 1
} finally {
    Pop-Location
}

