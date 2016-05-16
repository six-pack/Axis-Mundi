# -*- mode: python -*-

block_cipher = None


a = Analysis(['axismundi.py'],
             pathex=['.'],
             hiddenimports=[],
             hookspath=None,
             runtime_hooks=None,
             excludes=None)
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

##### SHIP GPG WITH GENERATED EXE - Even though this sucks it is an easier start for users who don't have a gpg executable already installed
# Below paths are for brew gpg
a.datas += [('binaries/gpg','/usr/local/bin/gpg','DATA')]
a.datas += [('binaries/gpgkeys_hkp','/usr/local/Cellar/gnupg/1.4.20/libexec/gnupg/gpgkeys_hkp','DATA')]
a.datas += [('binaries/gpgkeys_curl','/usr/local/Cellar/gnupg/1.4.20/libexec/gnupg/gpgkeys_curl','DATA')]

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
