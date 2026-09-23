' Double-click to stop JP Grammar Trainer (backend, frontend, Postgres container).
' Your data stays - Postgres data lives in a named Docker volume that survives this.

Set fso = CreateObject("Scripting.FileSystemObject")
strDir = fso.GetParentFolderName(WScript.ScriptFullName)
strScript = strDir & "\stop.ps1"

Set objShell = CreateObject("WScript.Shell")
objShell.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & strScript & """", 0, True
MsgBox "JP Grammar Trainer stopped.", 64, "JP Grammar Trainer"
