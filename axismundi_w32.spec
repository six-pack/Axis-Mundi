# -*- mode: python -*-
a = Analysis(['client.py'],
             pathex=[''],
             hiddenimports=[],
             hookspath=None,
             runtime_hooks=None)

##### include mydir in distribution #######
def extra_datas(mydir):
    def rec_glob(p, files):
        import os
        import glob
        for d in glob.glob(p):
            if os.path.isfile(d):
                files.append(d)
            rec_glob("%s/*" % d, files)
    files = []
    rec_glob("%s/*" % mydir, files)
    extra_datas = []
    for f in files:
        extra_datas.append((f, f, 'DATA'))

    return extra_datas

a.datas += [('icon.png','icon.png','DATA')]
a.datas += [('words.txt','words.txt','DATA')]
a.datas += extra_datas('static')
a.datas += extra_datas('templates')

# SQLITE3 DLL must be present in the Axis Mundi base directory - download 32 or 64 bit sqlite DLL from https://www.sqlite.org/download.html

print a.datas

pyz = PYZ(a.pure)
exe = EXE(pyz,
          a.scripts,
          a.binaries,
          a.zipfiles,
          a.datas,
          name='axismundi.exe',
          debug=False,
          strip=None,
          upx=True,
          console=True,
          icon='icon.ico' )




