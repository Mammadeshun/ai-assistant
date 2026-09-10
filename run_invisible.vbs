Set WshShell = CreateObject("WScript.Shell")
' Replace the path below with the exact path to your ai_assistant folder
WshShell.Run "cmd.exe /c cd C:\Users\shaye\Desktop\ai_assistant && C:\Users\shaye\anaconda3\condabin\conda.bat activate base && python main.py", 0, False
