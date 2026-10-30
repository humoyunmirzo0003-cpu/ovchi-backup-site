"""Generic one-shot staging bootstrap; contains no credentials or private bot source.
Run only after reviewing the source and verifying the exact downloaded SHA256.
"""
import base64
import datetime
import json
import re
import sys

LIVE_HASHES={}

REMOTE='import ast,fcntl,hashlib,io,json,os,pathlib,re,stat,sys,time,zipfile\n\ndef checked_archive(raw,expected):\n if len(raw)>5*1024*1024 or hashlib.sha256(raw).hexdigest()!=expected:raise ValueError()\n files={};total=0\n with zipfile.ZipFile(io.BytesIO(raw)) as archive:\n  if len(archive.infolist())>150:raise ValueError()\n  for info in archive.infolist():\n   path=pathlib.PurePosixPath(info.filename)\n   if path.is_absolute() or \'..\' in path.parts or len(path.parts)<2 or path.parts[0]!=\'ovchi-ready\' or str(path)!=info.filename or chr(92) in info.filename:raise ValueError()\n   if stat.S_ISLNK(info.external_attr>>16) or info.is_dir():raise ValueError()\n   name=str(pathlib.PurePosixPath(*path.parts[1:]))\n   if name in files or any(part in (\'.git\',\'.ssh\',\'data\',\'backups\',\'sessions\',\'requests\') for part in path.parts):raise ValueError()\n   if path.name!=\'.gitignore\' and (path.name.startswith(\'.\') or path.suffix not in (\'.py\',\'.md\',\'.txt\',\'.json\',\'.yml\',\'.reference\')):raise ValueError()\n   total+=info.file_size\n   if total>10*1024*1024 or info.file_size>2*1024*1024:raise ValueError()\n   files[name]=archive.read(info)\n manifest=json.loads(files[\'PACKAGE_SHA256.json\'])\n if set(files)!=set(manifest)|{\'PACKAGE_SHA256.json\'}:raise ValueError()\n for name,expected_hash in manifest.items():\n  if not isinstance(expected_hash,str) or not re.fullmatch(\'[a-f0-9]{64}\',expected_hash) or hashlib.sha256(files[name]).hexdigest()!=expected_hash:raise ValueError()\n return files\n\ndef patch_voice(source):\n tree=ast.parse(source)\n imports=[n for n in tree.body if isinstance(n,ast.Import) and len(n.names)==1 and n.names[0].name==\'ovchi_sync_tts\' and n.names[0].asname is None]\n functions=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==\'synthesize\']\n if len(imports)!=1 or len(functions)!=1 or \'ovchi_sync_tts.synthesize\' not in ast.unparse(functions[0]):raise ValueError()\n lines=source.splitlines(keepends=True);node=imports[0]\n lines[node.lineno-1:node.end_lineno]=[\'import ovchi_eleven_tts as ovchi_sync_tts  # staging only\\n\']\n result=\'\'.join(lines);compile(result,\'staged_voice\',\'exec\');return result\n\ndef write_new(path,data):\n path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)\n fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)\n with os.fdopen(fd,\'wb\') as f:f.write(data)\n\ndef main():\n # Revoke authorization before accepting the single, checksum-pinned upload.\n fd=os.open(KEY,os.O_RDWR|os.O_NOFOLLOW)\n with os.fdopen(fd,\'r+\') as f:\n  fcntl.flock(f,fcntl.LOCK_EX)\n  if not f.read() or time.time()>=EXPIRES:raise ValueError()\n  f.seek(0);f.truncate();f.flush();os.fsync(f.fileno())\n raw=sys.stdin.buffer.read(5*1024*1024+1)\n files=checked_archive(raw,ZIP_SHA)\n stage=pathlib.Path(STAGE)\n for name,expected in SOURCES.items():\n  path=stage/name\n  if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:raise ValueError()\n dest=stage/\'package\'\n if dest.exists() or dest.is_symlink():raise ValueError()\n dest.mkdir(mode=0o700)\n for name,data in files.items():write_new(dest/name,data)\n candidate=patch_voice((stage/\'ovchi_voice.py\').read_text())\n temp=stage/\'voice-candidate.py\'\n write_new(temp,candidate.encode());os.replace(temp,stage/\'ovchi_voice.py\')\n write_new(stage/\'ovchi_eleven_tts.py\',files[\'ovchi_eleven_tts.py\'])\n conf=json.loads(files[\'config/eleven.example.json\'])\n if conf.get(\'enabled\') is not False:raise ValueError()\n write_new(stage/\'.ovchi_eleven.json\',json.dumps(conf,indent=2).encode())\n hashes={}\n for name in (*SOURCES,\'ovchi_eleven_tts.py\'):\n  data=(stage/name).read_bytes();compile(data,name,\'exec\');hashes[name]=hashlib.sha256(data).hexdigest()\n # Mark the source and candidate hashes so approved deployment can detect drift.\n manifest={\'live\':\'/opt/ovchi\',\'originals\':SOURCES,\'candidate\':{name:hashes[name] for name in (\'ovchi_voice.py\',\'ovchi_eleven_tts.py\')},\'created_at\':time.time()}\n write_new(stage/\'stage-manifest.json\',json.dumps(manifest,indent=2).encode())\n with open(SETUP_REPORT) as f:backup=json.load(f)\n print(json.dumps({\'status\':\'stage_ready\',\'stage\':STAGE,\'package_commit\':COMMIT,\'zip_sha256\':ZIP_SHA,\'compiled\':True,\'tts_enabled\':False,\'api_key_present\':False,\'production_changed\':False,\'bot_started\':False,\'real_audio_generated\':False,\'backup_verified_by_setup\':backup[\'backup_verified\'],\'code_backup_only\':True,\'backup_path\':backup[\'backup_path\'],\'candidate_hashes\':hashes},sort_keys=True))\n\nif __name__==\'__main__\':\n try:main()\n except Exception:\n  print(\'{"status":"stage_failed","production_changed":false}\')\n  sys.exit(1)\n'

def setup_command(session,public,expires,zip_sha,commit):
    if not re.fullmatch('[0-9]{1,16}',session) or not re.fullmatch(r'ssh-ed25519 [A-Za-z0-9+/]+={0,2}(?: [A-Za-z0-9_.-]+)?',public):raise ValueError('Invalid staging identity')
    if not re.fullmatch('[a-f0-9]{64}',zip_sha) or not re.fullmatch('[a-f0-9]{40}',commit):raise ValueError('Invalid package identity')
    deadline=datetime.datetime.strptime(expires,'%Y%m%d%H%M%SZ').replace(tzinfo=datetime.timezone.utc)
    user='ovst'+session;home='/var/lib/ovchi-stage-'+session;stage='/opt/ovchi-staging/'+session
    backup='/opt/ovchi/backups/code_before_eleven_'+session
    handler='\n'.join(name+'='+repr(value) for name,value in {'KEY':home+'/.ssh/authorized_keys','STAGE':stage,'EXPIRES':int(deadline.timestamp()),'ZIP_SHA':zip_sha,'COMMIT':commit,'SOURCES':LIVE_HASHES,'SETUP_REPORT':home+'/setup.json'}.items())+'\n'+REMOTE
    line='restrict,expiry-time="'+expires+'",command="/usr/bin/python3 -I '+home+'/upload_once.py" '+public+'\n'
    source='''import hashlib,json,os,pwd,stat,subprocess,time
USER=USER_VALUE
HOME=HOME_VALUE
STAGE=STAGE_VALUE
BACKUP=BACKUP_VALUE
EXPIRES=EXPIRES_VALUE
UTC_END=UTC_END_VALUE
SOURCES=SOURCES_VALUE
HANDLER=HANDLER_VALUE
KEY_LINE=KEY_VALUE
assert os.geteuid()==0 and 60<EXPIRES-time.time()<=1800,"Konsol yoki ruxsat vaqti mos emas"
host=subprocess.run(["/usr/bin/ssh-keygen","-lf","/etc/ssh/ssh_host_ed25519_key.pub"],capture_output=True,text=True,check=True)
assert host.stdout.split()[1]=="SHA256:9yhtzAq70mgduLmDszQZB+RZ/FNvaS5XiObt4i3rIUk","Host kaliti mos emas"
try:
 pwd.getpwnam(USER);raise SystemExit("Hisob mavjud; toxtatildi")
except KeyError:pass
for path in (HOME,STAGE,BACKUP):assert not os.path.lexists(path),"Manzil mavjud; ustidan yozilmaydi"
buffers={}
for name,expected in SOURCES.items():
 fd=os.open("/opt/ovchi/"+name,os.O_RDONLY|os.O_NOFOLLOW)
 with os.fdopen(fd,"rb") as f:
  info=os.fstat(f.fileno());assert stat.S_ISREG(info.st_mode) and info.st_size<=2097152
  raw=f.read(2097153)
 assert len(raw)<=2097152 and hashlib.sha256(raw).hexdigest()==expected,"Server kodi ozgargan; toxtatildi"
 buffers[name]=raw
def parent(path,mode):
 if not os.path.lexists(path):os.mkdir(path,mode)
 info=os.lstat(path);assert stat.S_ISDIR(info.st_mode) and info.st_uid==0 and not info.st_mode&0o022
parent("/opt/ovchi/backups",0o700)
parent("/opt/ovchi-staging",0o711)
assert os.stat("/opt/ovchi-staging").st_mode&0o001,"Staging ota katalogiga kirish yopiq"
os.mkdir(BACKUP,0o700)
def save(path,data,mode=0o600,uid=0,gid=0):
 fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
 with os.fdopen(fd,"wb") as f:
  os.fchown(f.fileno(),uid,gid);f.write(data);f.flush();os.fsync(f.fileno())
for name,raw in buffers.items():save(BACKUP+"/"+name,raw)
for name,expected in SOURCES.items():assert hashlib.sha256(open(BACKUP+"/"+name,"rb").read()).hexdigest()==expected
save(BACKUP+"/code-manifest.json",json.dumps({"files":SOURCES,"code_only":True,"credentials_copied":False,"data_copied":False}).encode())
subprocess.run(["/usr/sbin/useradd","--system","--user-group","--no-create-home","--home-dir",HOME,"--shell","/bin/sh","--password","*",USER],check=True)
account=pwd.getpwnam(USER)
try:
 assert account.pw_uid!=0 and os.getgrouplist(USER,account.pw_gid)==[account.pw_gid]
 os.mkdir(HOME,0o750);os.chown(HOME,0,account.pw_gid)
 os.mkdir(HOME+"/.ssh",0o750);os.chown(HOME+"/.ssh",0,account.pw_gid)
 os.mkdir(STAGE,0o700);os.chown(STAGE,account.pw_uid,account.pw_gid)
 for name,raw in buffers.items():save(STAGE+"/"+name,raw,0o440,0,account.pw_gid)
 save(HOME+"/upload_once.py",HANDLER.encode(),0o440,0,account.pw_gid)
 save(HOME+"/setup.json",json.dumps({"backup_path":BACKUP,"backup_verified":True,"code_only":True}).encode(),0o440,0,account.pw_gid)
 subprocess.run(["/usr/bin/systemd-run","--quiet","--unit=ovchi-stage-expire-"+USER,"--on-calendar="+UTC_END,"--timer-property=AccuracySec=1s","/usr/sbin/usermod","--expiredate","1970-01-02",USER],check=True)
 save(HOME+"/.ssh/authorized_keys",KEY_LINE.encode(),0o600,account.pw_uid,account.pw_gid)
 print("OVCHI_STAGE_READY",UTC_END)
except BaseException:
 subprocess.run(["/usr/sbin/usermod","--expiredate","1970-01-02",USER],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 raise
'''
    values={'USER_VALUE':repr(user),'HOME_VALUE':repr(home),'STAGE_VALUE':repr(stage),'BACKUP_VALUE':repr(backup),'EXPIRES_VALUE':str(int(deadline.timestamp())),'UTC_END_VALUE':repr(deadline.strftime('%Y-%m-%d %H:%M:%S UTC')),'SOURCES_VALUE':repr(LIVE_HASHES),'HANDLER_VALUE':repr(handler),'KEY_VALUE':repr(line)}
    for marker,value in values.items():source=source.replace(marker,value)
    compile(source,'reviewed-staging-console','exec')
    return "python3 - <<'OVCHI_STAGE'\n"+source+'OVCHI_STAGE'

def main():
 global LIVE_HASHES
 if len(sys.argv)!=2:raise SystemExit("One reviewed public configuration is required")
 if len(sys.argv[1])>4096:raise SystemExit("Configuration too large")
 config=json.loads(base64.b64decode(sys.argv[1],validate=True))
 if set(config)!={"session","public_key","expires_utc","zip_sha256","commit","live_hashes"}:raise SystemExit("Unexpected configuration")
 values=config["live_hashes"]
 if set(values)!={"bot.py","ovchi_voice.py","ovchi_sync_tts.py"} or not all(isinstance(v,str) and re.fullmatch("[a-f0-9]{64}",v) for v in values.values()):raise SystemExit("Invalid reviewed source hashes")
 LIVE_HASHES=values
 command=setup_command(config["session"],config["public_key"],config["expires_utc"],config["zip_sha256"],config["commit"])
 source=command.split("\n",1)[1].rsplit("OVCHI_STAGE",1)[0]
 exec(compile(source,"reviewed-staging-bootstrap","exec"),{"__name__":"__main__"})

if __name__=="__main__":main()
