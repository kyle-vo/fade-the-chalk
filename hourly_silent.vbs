' Silent launcher for the scheduled rerun. Task Scheduler starting powershell.exe directly flashes a console window
' (and can steal focus from a full-screen game) before -WindowStyle Hidden takes effect. wscript has no window, and
' Run(..., 0, False) starts PowerShell already hidden, so nothing appears on screen at all.
Set sh = CreateObject("WScript.Shell")
dir = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = dir
sh.Run "powershell.exe -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File """ & dir & "\hourly.ps1""", 0, True
