# -*- mode: python -*-

block_cipher = None


a = Analysis(['client.py'],
             pathex=['.'],
             hiddenimports=[],
             hookspath=None,
             runtime_hooks=None,
             excludes=None),
#             cipher=block_cipher)

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

print a.datas

pyz = PYZ(a.pure) # , cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          a.binaries,
          a.zipfiles,
          a.datas,
          name='axismundi',
          debug=False,
          strip=False,
          upx=True,
          console=True,
          icon='icon.ico')
