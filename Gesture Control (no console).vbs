' Starts Gesture Control without the black console window.
' Run "Gesture Control.bat" once first so everything is installed.
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
folder = fso.GetParentFolderName(WScript.ScriptFullName)
pythonw = folder & "\.venv\Scripts\pythonw.exe"
If Not fso.FileExists(pythonw) Then
    MsgBox "Run 'Gesture Control.bat' once first to set things up.", 48, "Gesture Control"
    WScript.Quit
End If
sh.CurrentDirectory = folder
sh.Run """" & pythonw & """ main.py", 0, False
