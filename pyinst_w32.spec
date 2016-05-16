# -*- mode: python -*-
a = Analysis(['axismundi.py'],
             pathex=[''],
             binaries=[],
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

##### SHIP GPG WITH GENERATED EXE - Even though this sucks it is an easier start for users who don't have a gpg executable already installed
a.datas += [('binaries\\gpg.exe','c:\Program Files\GNU\GnuPG\gpg.exe','DATA')]
a.datas += [('binaries\\gpgkeys_hkp.exe','c:\Program Files\GNU\GnuPG\gpgkeys_hkp.exe','DATA')]
a.datas += [('binaries\\gpgkeys_curl.exe','c:\Program Files\GNU\GnuPG\gpgkeys_curl.exe','DATA')]

## Pyinstaller on Windows needs us to explicitly define _sqlite.pyd to support pysqlcipher
#a.datas += [('pysqlcipher\\_sqlite.pyd','_sqlite.pyd','DATA')]# This requires you to place a copy of _sqlite.py in your AM base folder - only do that if next line fails
a.datas += [('pysqlcipher\\_sqlite.pyd','build/axismundi_w32/pysqlcipher-2.6.4-py2.7-win32.egg/pysqlcipher/_sqlite.pyd','DATA')] # This should be present by the time data is added TODO: Make better

## Standard AM data files
a.datas += [('icon.png','icon.png','DATA')]
a.datas += [('words.txt','words.txt','DATA')]
a.datas += extra_datas('static')
a.datas += extra_datas('templates')

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




