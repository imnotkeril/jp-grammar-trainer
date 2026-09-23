' Double-click this file to start JP Grammar Trainer - no terminal window appears.
' Runs launch.ps1 hidden: Postgres, migrations, seed, backend, frontend, then opens
' http://localhost:3000 automatically. On error, opens logs\launch.log in Notepad instead.

Set fso = CreateObject("Scripting.FileSystemObject")
strDir = fso.GetParentFolderName(WScript.ScriptFullName)
strScript = strDir & "\launch.ps1"

Set objShell = CreateObject("WScript.Shell")
objShell.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & strScript & """", 0, False
