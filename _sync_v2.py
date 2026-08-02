import paramiko, os, time

HOST='152.136.246.33'; USER='Administrator'; PASS='ZZxx123456789'
LOCAL='C:/Users/18065/WorkBuddy/2026-07-27-19-50-45/mall_system'
REMOTE_BASE='C:/mall_system'

files=['app.py','templates/admin/template_designer.html','templates/admin/wechat.html']
stale='C:/mall_system/templates/admin/builtin_templates.html'

t=paramiko.Transport((HOST,22)); t.connect(username=USER,password=PASS)
sftp=paramiko.SFTPClient.from_transport(t)
for f in files:
    localp=os.path.join(LOCAL,f); remotep=REMOTE_BASE+'/'+f
    d=os.path.dirname(remotep).replace('\\','/')
    parts=d.split('/'); cur=''
    for p in parts:
        if not p: continue
        cur=cur+'/'+p if cur else p
        try: sftp.stat(cur)
        except IOError:
            try: sftp.mkdir(cur)
            except IOError: pass
    sftp.put(localp, remotep); print('uploaded ->', remotep)
try:
    sftp.remove(stale); print('removed stale ->', stale)
except IOError:
    print('stale already gone or missing')
sftp.close(); t.close()

# restart Flask
c=paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST,username=USER,password=PASS,timeout=30)
print('kill old:', c.exec_command('taskkill /F /PID 5280')[1].read().decode('gbk','ignore').strip())
c.exec_command('schtasks /end /tn "FlaskMallServer"')
time.sleep(2)
print('run:', c.exec_command('schtasks /run /tn "FlaskMallServer"')[1].read().decode('gbk','ignore').strip())
time.sleep(6)
print('pythonw:', c.exec_command('tasklist | findstr /I pythonw')[1].read().decode('gbk','ignore').strip())
c.close()

import urllib.request
try:
    with urllib.request.urlopen('http://152.136.246.33:5000/api/publish/built-in-templates',timeout=15) as r:
        b=r.read().decode('utf-8')
        print('ENDPOINT', r.status, 'templates:', b.count('"id"'))
except Exception as e:
    print('ENDPOINT ERROR:', repr(e))
