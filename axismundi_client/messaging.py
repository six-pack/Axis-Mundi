import json
import random
import string
import textwrap
from platform import system as get_os

import gnupg
from constants import *
from utilities import current_time, got_pgpkey, json_from_clearsigned


class Contract_seed(object):

    def __init__(self):
        self.type = 'Contract'
        self.id = ''
        self.vendor = ''
        self.buyer = ''
        self.notary = ''
        self.subject = ''
        self.description = ''
        self.btcpublicaddress_vendor = ''
        self.amount = ''
        # List of allowed transaction types (FE, blind notarized, multisig
        # escrow etc)
        self.transaction_types = []
        self.expiry_date = ''
        self.creation_date = ''


def jdefault(o):
    return o.__dict__


class Contact(object):
    # Contact class

    def __init__(self):
        self.id = ''
        self.displayname = ''
        self.pgpkey = ''
        self.pgpkeyid = ''
        self.flags = ''


class Message(object):
    # Generic message class - ALL messages take this format - sub-messages are dicts and may carry additional
    # things like orders and other application specific things. The message
    # type is specified by the TYPE parameter

    def __init__(self):
        self.id = ''.join(random.SystemRandom().choice(
            string.ascii_uppercase + string.ascii_lowercase + string.digits) for _ in range(8))
        self.version = ''
        self.sender = ''
        self.sender_name = ''
        self.recipient = ''
        self.recipient_name = ''
        self.subject = ''
        self.datetime_sent = ''
        self.datetime_received = ''
        self.sent = False
        self.read = False
        self.type = ''
        self.inreplyto = ''
        self.flags = ''  # for future usage
        self.body = ''
        # set to true when a valid outer signature is present in the body (not
        # to be set by users)
        self.signed = ''
        self.encrypted = ''
        self.sub_messages = []  # Contracts etc.
        self.raw_message = ''
        self.topic = ''

    def loadjson(self, j):
        # additional checking here would not hurt
        try:
            self.__dict__ = json.loads(j)
        except:
            print "Warning: Could not get JSON, dropping message"
            return False
        return True


class Messaging():
    # TODO : Refactor messaging...
    # Overarching message handling class

    def __init__(self, mypgpkeyid, pgppassphrase, pgp_dir, app_dir, gpg_binary):
        self.mypgpkeyid = mypgpkeyid
        if get_os() == 'Windows':
            keyring = app_dir + '\pubkeys.gpg'
            # TODO - account for filenames with spaces on windows
        else:
            keyring = app_dir + '/pubkeys.gpg'
        self.gpg = gnupg.GPG(gpgbinary=gpg_binary,gnupghome=pgp_dir, options={'--primary-keyring=' + keyring, '--no-emit-version', '--keyserver=hkp://127.0.0.1:5000',
                                                         '--keyserver-options=auto-key-retrieve=yes,http-proxy=', '--primary-keyring="' + keyring + '"'})  # removed '--auto-key-locate=keyserver',
        self.pgp_passphrase = pgppassphrase
#       self.gpg.options = "--no-emit-version"

    def PrepareMessage(self, message, alt_pgpkey=None, signmessage=True):
        # Send a message object. First serialize, then sign, then encrypt (if recipients are named), finally send.
        # First set the send time - ALWAYS USE UTC! Never use any local system
        # timezone information
        self.recipient = message.recipient
        message.datetime_sent = current_time()
        serialized_message = json.dumps(
            message, default=jdefault, sort_keys=True)
        # Now PGP clearsign if enabled
        # print serialized_message
        serialized_message = textwrap.fill(
            serialized_message, 80, drop_whitespace=False)
        # print serialized_message
        if signmessage:
            final_clear_message = str(self.gpg.sign(
                serialized_message, keyid=self.mypgpkeyid, passphrase=self.pgp_passphrase))
        else:
            final_clear_message = serialized_message
        # Now always encrypt if this is a directed message
        if self.recipient:
            # TODO: encrypt to alternate pgp key if ephemeral pgp message keys
            # are enabled and we have one for this recipient
            print "Info: PrepareMessage: calling recv keys"
            # We don't really want to do this every time but it will do for now
            self.gpg.recv_keys('hkp://127.0.0.1:5000', self.recipient)
            print "Info: PrepareMessage: calling encrypt"
            final_message_raw = self.gpg.encrypt(
                final_clear_message, self.recipient, passphrase=self.pgp_passphrase, always_trust=True)
            if final_message_raw == False:
                # Encryption did not succeed - stop now
                print "ERROR: Message encryption failed"
                return False
            else:
                final_message = str(final_message_raw)
        else:
            # This will be an unencrypted message (only for "posted" broadcast
            # messages such as listings and open chat channels)
            final_message = final_clear_message
        # OK, ready to send
        return final_message

    def GetMessage(self, rawmessage, client_instance, topic, alt_pgpkey=None, allow_unsigned=True):
        # Decode and return a message object. First decrypt if encrypted, then check outer signature if signed, the parse
        # json, then attempt to safely deserialize into a message object, then
        # set received time, finally return message or error
        input_message_encrypted = False
        input_message_signed = False
        lrawmessage = str(rawmessage)
        # First set the send time - ALWAYS USE UTC! Never use any local system timezone information
        # Step 1 - Is it encrypted?
        if lrawmessage.startswith('-----BEGIN PGP MESSAGE-----'):
            decrypt_msg = self.gpg.decrypt(
                lrawmessage, passphrase=self.pgp_passphrase)
            if not str(decrypt_msg):
                print "Warning: Unable to decrypt received message, dropping message"
                return False
            else:
                clear_lrawmessage = str(decrypt_msg)
                input_message_encrypted = True
        else:
            clear_lrawmessage = lrawmessage
#        print clear_lrawmessage
        # Step 2 - Is it signed?
        if clear_lrawmessage.startswith('-----BEGIN PGP SIGNED MESSAGE-----'):
            tmp_key = False
            try:
                tmp_stripped_msg = json_from_clearsigned(clear_lrawmessage)
                tmp_message = Message()
                tmp_message.loadjson(tmp_stripped_msg)
                tmp_key = tmp_message.sender
                # we will need this when we finally get the key
                tmp_message.raw_message = rawmessage
                tmp_message.topic = topic
            except:
                print "Warning: Failed to parse json response and extract sender key id"
                return False
            if tmp_key:
                # check if this key needs to be retreived
                if got_pgpkey(client_instance.storageDB, tmp_key):
                    print "Info: Already have the necessary key " + tmp_key  # we already have the key
                else:
                    print "Info: Need key " + tmp_key  # defer message processing until key is retrieved
                    # assign a temporary random id
                    random_id = random.randrange(1, stop=999999999, step=1)
                    client_instance.task_state_pgpkeys[tmp_key][
                        'state'] = KEY_LOOKUP_STATE_INITIAL  # create task request for a lookup
                    client_instance.task_state_messages[random_id][
                        'state'] = MSG_STATE_KEY_REQUESTED
                    client_instance.task_state_messages[
                        random_id]['message'] = tmp_message
                    return MSG_STATE_KEY_REQUESTED

            else:
                print "Warning: Sending keyid could not be extracted from message - unable to verify sender key - dropping message..."
#                print clear_lrawmessage
                return False
#        print clear_lrawmessage
        if clear_lrawmessage.startswith('-----BEGIN PGP SIGNED MESSAGE-----'):
            signed = True
            verify_signature = self.gpg.verify(clear_lrawmessage)
            # if verify_signature.pubkey_fingerprint:    # Proper signature check,
            # full fp only returned if key present
            if verify_signature.key_id:     # Weak signature check - TODO: TESTING ONLY!
                input_message_signed = True
                try:
                    clear_strippedlrawmessage = json_from_clearsigned(clear_lrawmessage)
                    #clear_strippedlrawmessage = clear_lrawmessage[
                    #    clear_lrawmessage.index('{'):clear_lrawmessage.rindex('}') + 1]
                except:
                    return False
            else:
                return False
        else:
            print "Warning: Unsigned message block identified..."
            if allow_unsigned:
                clear_strippedlrawmessage = clear_lrawmessage
                signed = False
            else:
                return False
        # Step 3 - Is it a valid JSON message?
        #clear_strippedlrawmessage = clear_strippedlrawmessage.replace(
        #    '\n', '')  # strip out all those newlines we added pre-signing
        message = Message()
        if message.loadjson(clear_strippedlrawmessage) == False:
            print "Warning: Could not decode JSON, dropping message. Message was " + clear_strippedlrawmessage
            return False
        else:
            # Finally make sure the sender keyid matches the signing keyid
            if signed and not (verify_signature.key_id == message.sender):
                print "Warning: Apparent spoofed message!! - Claims to be from " + message.sender
                return False
            if input_message_encrypted:
                message.encrypted = True
            if input_message_signed:
                message.signed = True
            message.datetime_received = current_time()
            message.topic = topic
            return message
