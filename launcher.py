import subprocess
import sys

subprocess.Popen(
    [r'C:/Users/Administrator/AppData/Local/Programs/Python/Python311/pythonw.exe', r'C:/mall_system/app.py'],
    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
    stdout=open(r'C:/mall_system/server.log', 'a'),
    stderr=open(r'C:/mall_system/server_error.log', 'a'),
    stdin=subprocess.DEVNULL
)
print('Flask started')
