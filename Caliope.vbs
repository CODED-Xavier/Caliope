' Caliope without the black window: runs Play.bat hidden (the desktop shortcut points here).
' Play.bat shows a loading screen with the icon and a progress bar until the app's window opens.
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
here = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = here
sh.Run "cmd /c """"" & here & "\Play.bat"" --quiet""", 0, False
