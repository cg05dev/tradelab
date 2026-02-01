#!/usr/bin/env python3
"""
TradeLab Setup Wizard
Combines all setup steps into a single executable
"""

import os
import sys
import subprocess
import shutil
import platform
from pathlib import Path

# Colors for Windows console
class Colors:
    GREEN = '\033[92m' if platform.system() != 'Windows' else ''
    RED = '\033[91m' if platform.system() != 'Windows' else ''
    YELLOW = '\033[93m' if platform.system() != 'Windows' else ''
    BLUE = '\033[94m' if platform.system() != 'Windows' else ''
    RESET = '\033[0m' if platform.system() != 'Windows' else ''

def print_header():
    """Print setup header"""
    print("\n" + "=" * 50)
    print("      TradeLab Setup Wizard")
    print("=" * 50 + "\n")

def print_step(step_num, total_steps, message):
    """Print step message"""
    print(f"[{step_num}/{total_steps}] {message}...")

def print_success(message):
    """Print success message"""
    print(f"{Colors.GREEN}[OK]{Colors.RESET} {message}")

def print_error(message):
    """Print error message"""
    print(f"{Colors.RED}[X]{Colors.RESET} {message}")

def print_info(message):
    """Print info message"""
    print(f"{Colors.BLUE}[INFO]{Colors.RESET} {message}")

def check_command(command, name, download_url):
    """Check if a command is available"""
    try:
        result = subprocess.run(
            [command, '--version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            version = result.stdout.strip().split('\n')[0]
            print_success(f"{name} {version} detected")
            return True
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
        pass
    
    print_error(f"{name} not found!")
    print(f"\nPlease install {name} from:")
    print(f"{download_url}\n")
    if name == "Python":
        print("Make sure to check 'Add Python to PATH' during installation!\n")
    return False

def setup_backend(script_dir):
    """Setup Python backend"""
    backend_dir = script_dir / "backend"
    
    if not backend_dir.exists():
        print_error("Backend directory not found!")
        return False
    
    os.chdir(backend_dir)
    
    # Create virtual environment if it doesn't exist
    venv_dir = backend_dir / "venv"
    if not venv_dir.exists():
        print("Creating Python virtual environment...")
        try:
            subprocess.run(
                [sys.executable, "-m", "venv", "venv"],
                check=True,
                timeout=60
            )
            print_success("Virtual environment created")
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as e:
            print_error("Failed to create virtual environment")
            return False
    
    # Determine Python executable in venv
    if platform.system() == "Windows":
        python_exe = venv_dir / "Scripts" / "python.exe"
        pip_exe = venv_dir / "Scripts" / "pip.exe"
    else:
        python_exe = venv_dir / "bin" / "python"
        pip_exe = venv_dir / "bin" / "pip"
    
    # Upgrade pip
    print("Upgrading pip...")
    try:
        subprocess.run(
            [str(pip_exe), "install", "--upgrade", "pip", "--quiet"],
            check=True,
            timeout=120
        )
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
        print_info("pip upgrade skipped (may already be latest)")
    
    # Install requirements
    print("Installing Python packages...")
    requirements_file = backend_dir / "requirements.txt"
    if not requirements_file.exists():
        print_error("requirements.txt not found!")
        return False
    
    try:
        subprocess.run(
            [str(pip_exe), "install", "-r", str(requirements_file)],
            check=True,
            timeout=300
        )
        print_success("Backend setup complete")
        return True
    except subprocess.TimeoutExpired:
        print_error("Installation timed out")
        return False
    except subprocess.CalledProcessError:
        print_error("Failed to install backend dependencies")
        return False

def setup_frontend(script_dir):
    """Setup Node.js frontend"""
    frontend_dir = script_dir / "frontend"
    
    if not frontend_dir.exists():
        print_error("Frontend directory not found!")
        return False
    
    os.chdir(frontend_dir)
    
    # Check if node_modules exists
    node_modules = frontend_dir / "node_modules"
    if node_modules.exists() and (node_modules / "electron").exists():
        print_info("Frontend dependencies already installed")
        print_success("Frontend setup complete")
        return True
    
    print("Installing Node.js packages (this may take a minute)...")
    try:
        subprocess.run(
            ["npm", "install"],
            check=True,
            timeout=600
        )
        print_success("Frontend setup complete")
        return True
    except subprocess.TimeoutExpired:
        print_error("Installation timed out")
        return False
    except subprocess.CalledProcessError:
        print_error("Failed to install frontend dependencies")
        return False

def create_shortcut(script_dir):
    """Create desktop shortcut"""
    if platform.system() != "Windows":
        print_info("Shortcut creation only supported on Windows")
        return True
    
    try:
        import win32com.client
    except ImportError:
        print_info("pywin32 not available, skipping shortcut creation")
        print("You can create a shortcut manually using create-shortcut.bat")
        print("Or install pywin32: pip install pywin32")
        return True
    
    # Get desktop path
    desktop = Path.home() / "Desktop"
    if not desktop.exists():
        desktop = Path(os.environ.get("PUBLIC", "")) / "Desktop"
        if not desktop.exists():
            print_error("Could not find Desktop folder")
            return False
    
    shortcut_path = desktop / "TradeLab.lnk"
    
    # Determine launcher file
    launcher_vbs = script_dir / "start-tradelab-desktop-launcher.vbs"
    launcher_ps1 = script_dir / "start-tradelab-desktop.ps1"
    launcher_bat = script_dir / "start-tradelab-desktop.bat"
    icon_file = script_dir / "frontend" / "assets" / "icon.ico"
    
    if launcher_vbs.exists():
        target = str(launcher_vbs)
        args = f'"{launcher_vbs}"'
        exe = "wscript.exe"
    elif launcher_ps1.exists():
        target = str(launcher_ps1)
        args = f'-WindowStyle Hidden -ExecutionPolicy Bypass -File "{launcher_ps1}"'
        exe = "powershell.exe"
    elif launcher_bat.exists():
        target = str(launcher_bat)
        args = f'/k cd /d "{script_dir}" && "{launcher_bat}"'
        exe = "cmd.exe"
    else:
        print_error("No launcher file found!")
        return False
    
    # Remove existing shortcut
    if shortcut_path.exists():
        try:
            shortcut_path.unlink()
        except:
            pass
    
    # Create shortcut
    try:
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(str(shortcut_path))
        shortcut.Targetpath = exe
        shortcut.Arguments = args
        shortcut.WorkingDirectory = str(script_dir)
        shortcut.Description = "TradeLab Desktop App"
        
        if icon_file.exists():
            shortcut.IconLocation = str(icon_file)
        
        shortcut.save()
        print_success("Desktop shortcut created")
        
        # Open File Explorer to show the desktop shortcut
        try:
            if platform.system() == "Windows":
                import subprocess
                subprocess.Popen(f'explorer /select,"{shortcut_path}"')
                print_info("Opened File Explorer to show desktop shortcut")
        except Exception:
            pass  # Ignore errors opening explorer
        
        return True
    except Exception as e:
        print_error(f"Failed to create shortcut: {e}")
        return False

def main():
    """Main setup function"""
    print_header()
    
    # Get script directory
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        script_dir = Path(sys.executable).parent
    else:
        # Running as script
        script_dir = Path(__file__).parent
    
    # Verify we're in the correct directory
    if not (script_dir / "backend").exists() or not (script_dir / "frontend").exists():
        print_error("Setup script must be run from the TradeLab project root directory!")
        print(f"\nCurrent directory: {script_dir}")
        print("\nPlease ensure the setup script is in the same folder as 'backend' and 'frontend' directories.")
        input("\nPress Enter to exit...")
        return 1
    
    # Step 1: Check Python
    print_step(1, 5, "Checking Python")
    if not check_command("python", "Python", "https://www.python.org/downloads/"):
        input("\nPress Enter to exit...")
        return 1
    
    # Step 2: Check Node.js
    print_step(2, 5, "Checking Node.js")
    if not check_command("node", "Node.js", "https://nodejs.org/"):
        input("\nPress Enter to exit...")
        return 1
    
    # Step 3: Setup Backend
    print_step(3, 5, "Setting up Backend")
    if not setup_backend(script_dir):
        input("\nPress Enter to exit...")
        return 1
    
    # Step 4: Setup Frontend
    print_step(4, 5, "Setting up Frontend")
    if not setup_frontend(script_dir):
        input("\nPress Enter to exit...")
        return 1
    
    # Step 5: Create Desktop Shortcut
    print_step(5, 5, "Creating Desktop Shortcut")
    create_shortcut(script_dir)  # Don't fail if shortcut creation fails
    
    # Success!
    print("\n" + "=" * 50)
    print("      Setup Complete!")
    print("=" * 50)
    print("\nYou can now run TradeLab using:")
    print("  - The 'TradeLab' shortcut on your desktop")
    print("  - start-tradelab-desktop.bat (double-click)\n")
    
    # Open File Explorer to the project directory
    try:
        if platform.system() == "Windows":
            import subprocess
            subprocess.Popen(f'explorer "{script_dir}"')
            print_info("Opened File Explorer to project directory")
    except Exception:
        pass  # Ignore errors opening explorer
    
    input("\nPress Enter to exit...")
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nSetup cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        input("\nPress Enter to exit...")
        sys.exit(1)

