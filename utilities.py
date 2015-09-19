from datetime import datetime
from PIL import Image
import cStringIO
import base64
import re
import json
import random
import string
import itertools
import os
import sys
from platform import system as get_os



class Listing(object):
    # Listing class

    def __init__(self):
        # This will form part of btc address generation
        self.id = str(random.SystemRandom().randint(1000000000, 2000000000))
        self.title = ''
        self.description = ''
        self.unitprice = ''
        self.currency_code = ''
        self.categories = ''
        self.is_public = True
        self.image_str = ''
        self.quantity_available = 0
        self.order_max_qty = 0
        self.ships_from = ''
        self.ships_to = []
        self.shipping_options = ''


class full_name(object):

    def __init__(self, display_name, pgpkey_id):
        self.display_name = display_name
        self.pgpkey_id = pgpkey_id


class queue_task(object):   # Tasks passed from the front end to the main thread for processing

    def __init__(self, id, command, data):
        self.id = id
        self.command = command
        self.data = data


def current_time():
    utc_datetime = datetime.utcnow()
    # always zero seconds to reduce impact of clock time skew leakage
    return utc_datetime.strftime("%Y-%m-%d %H:%M") + ":00"


def get_age(when):
    age = datetime.utcnow() - when
    return age.seconds


def encode_image(buf, size):
    im = Image.open(cStringIO.StringIO(buf))
    im.thumbnail(size, Image.ANTIALIAS)
    image_buffer = cStringIO.StringIO()
    im.save(image_buffer, "PNG")
    image_buffer.getvalue()
    b64_image = base64.b64encode(image_buffer.getvalue())
    return b64_image


def got_pgpkey(orm, key_id):
    if key_id == '':
        return True
    session = orm.DBSession()
    key_present = session.query(
        orm.cachePGPKeys).filter_by(key_id=key_id).first()
    if key_present:
        return True
    else:
        return False


def parse_user_name(name):
    if not name:
        return None
    key_only = re.compile('^[0-9a-fA-F]{16}$')
    if key_only.match(name):
        pgp_keyid = name
        fullname = full_name
        fullname.display_name = ''
        fullname.pgpkey_id = name
        return fullname
    elif re.match('.*\([0-9a-fA-F]{16}\)(?!.*\([0-9a-fA-F]{16}\))$', name):
        display_name = name[0:str(name).rindex('(')].strip()
        pgp_keyid = name[str(name).rindex('(') + 1:len(name) - 1]
        fullname = full_name
        fullname.display_name = display_name
        fullname.pgpkey_id = pgp_keyid
        return fullname
    else:
        print "Unable to extract display name/key if from recipient"
        return None
   # display_name =


def generate_seed(wordlist_path, words=12):
    seed = ''
    # TODO: allow user specified wordlist AND handle different
    # locations/non-existant words
    wordlist = getWords(wordlist_path)
    if words < 12:
        words = 12
    for x in range(0, words - 1):
        seed = ' '.join(random.SystemRandom().choice(wordlist)
                        for _ in range(words))
    return seed


def getWords(filepath):
    with open(filepath) as f:
        words = []
        pos = {}
        position = itertools.count()
        for line in f:
            for word in line.split():
                if word not in pos:
                    pos[word] = position.next()
                    words.append(word)
    return sorted(words, key=pos.__getitem__)

def os_is_tails():
    # is this OS Tails
    try:
        with open('/etc/os-release') as f:
            if re.match('TAILS_PRODUCT_NAME',f.readline()):
                return True
    except:
        pass
    return False

def replace_in_file(path,text,subs,flags=0):
    with open (path,"r+") as file:
        file_contents=file.read()
        text_pattern = re.compile(re.escape(text), flags)
        file_contents = text_pattern.sub(subs,file_contents)
        file.seek(0)
        file.truncate()
        file.write(file_contents)


########  Pyinstaller onefile need paths translation #####################


def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def json_from_clearsigned(clearsigned_rawmessage):
    if clearsigned_rawmessage.startswith('-----BEGIN PGP SIGNED MESSAGE-----'):
        nearly_stripped_message = clearsigned_rawmessage[
                            clearsigned_rawmessage.index('{'):clearsigned_rawmessage.rindex('}') + 1]
        # Now replace and '- ' if at start of line with nothing to mirror pgp escaping of dashes
        current_stage_signed = re.sub('(?m)^- ',"",nearly_stripped_message) # pgp wont do this for us
        # Now strip the line breaks that were added prior to signing
        stripped_message = current_stage_signed.replace('\n', '')  # strip out all those newlines we added pre-signing
        return stripped_message
    else:
        return False