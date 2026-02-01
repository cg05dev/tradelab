' VBScript launcher to run PowerShell completely hidden
' This prevents any console window from appearing

Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

' Get the directory where this script is located
scriptPath = fso.GetParentFolderName(WScript.ScriptFullName)
ps1Path = scriptPath & "\start-tradelab-desktop.ps1"

' Check if PowerShell script exists
If Not fso.FileExists(ps1Path) Then
    MsgBox "PowerShell launcher not found: " & ps1Path, vbCritical, "TradeLab Error"
    WScript.Quit 1
End If

' Run PowerShell script completely hidden (0 = hidden window)
WshShell.Run "powershell.exe -WindowStyle Hidden -ExecutionPolicy Bypass -File """ & ps1Path & """", 0, False

' Exit immediately - don't wait for the process
WScript.Quit 0

