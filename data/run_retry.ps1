$stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-Content -Path "D:\clipper\data\retry_publish.log" -Value "=== task run $stamp ==="
& "D:\clipper\.venv\Scripts\python.exe" "D:\clipper\data\retry_once.py" *>> "D:\clipper\data\retry_publish.log"