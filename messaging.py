import gnupg
import json
from utilities import current_time

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
        self.transaction_types =[] # List of allowed transaction types (FE, blind notarized, multisig escrow etc)
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
    # things like orders and other application specific things. The message type is specified by the TYPE parameter
    def __init__(self):
        self.id = ''
        self.version = ''
        self.sender = ''
        self.recipient = ''
        self.subject = ''
        self.datetime_sent = ''
        self.datetime_received = ''
        self.sent = False
        self.read = False
        self.type = ''
        self.inreplyto = ''
        self.flags = '' # for future usage
        self.body = ''
        self.signed='' # set to true when a valid outer signature is present in the body (not to be set by users)
        self.cleartext=''
        self.sub_messages = [] # Contracts etc.
    def loadjson (self, j):
        # additional checking here would not hurt
        try:
            self.__dict__ = json.loads(j)
        except:
            print "Could not get JSON, dropping message"
            return False
        return True

class Messaging():
    # Overarching message handling class
    def __init__(self, mypgpkeyid, pgppassphrase, homedir):
        self.mypgpkeyid = mypgpkeyid
        self.gpg = gnupg.GPG(gnupghome=homedir + '/.gnupg')
        self.pgp_passphrase = pgppassphrase
        self.allowUnsignedMessages = True
#       self.gpg.options = "--no-emit-version"

    def PrepareMessage(self,message,alt_pgpkey=None, signmessage=True):
        # Send a message object. First serialize, then sign, then encrypt (if recipients are named), finally send.
        # First set the send time - ALWAYS USE UTC! Never use any local system timezone information
        self.recipient = message.recipient
        message.datetime_sent = current_time()
        serialized_message = json.dumps(message,default=jdefault,sort_keys=True)
        # Now PGP clearsign if enabled
        if signmessage:
            final_clear_message = str(self.gpg.sign(serialized_message, keyid=self.mypgpkeyid,passphrase=self.pgp_passphrase ))
        else:
            final_clear_message = serialized_message
        # Now always encrypt if this is a directed message
        if self.recipient:
            # TODO: encrypt to alternate pgp key if ephemeral pgp message keys are enabled and we have one for this recipient
            final_message_raw = self.gpg.encrypt(final_clear_message,self.recipient,passphrase=self.pgp_passphrase, always_trust=True)
            if final_message_raw == False:
                # Encryption did not succeed - stop now
                print ("Encryption failed")
                return False
            else: final_message = str(final_message_raw)
        else:
             # This will be an unencrypted message (only for "posted" broadcast messages such as listings and open chat channels)
             final_message = final_clear_message
        # OK, ready to send
        return final_message

    def GetMessage(self,rawmessage,alt_pgpkey=None):
        # Decode and return a message object. First decrypt if encrypted, then check outer signature if signed, the parse
        # json, then attempt to safely deserialize into a message object, then set received time, finally return message or error
        lrawmessage = str(rawmessage)
        # First set the send time - ALWAYS USE UTC! Never use any local system timezone information
        #### Step 1 - Is it encrypted?
        if lrawmessage.startswith('-----BEGIN PGP MESSAGE-----'):
            decrypt_msg = self.gpg.decrypt(lrawmessage, passphrase=self.pgp_passphrase )
            if not str(decrypt_msg):
                print "Unable to decrypt received message, dropping message"
                return False
            else:
                clear_lrawmessage = str(decrypt_msg)
        else:
            clear_lrawmessage = lrawmessage
        #### Step 2 - Is it signed?
        if clear_lrawmessage.startswith('-----BEGIN PGP SIGNED MESSAGE-----'):
            #print "Clear-signed message identified..."
            verify_signature = self.gpg.verify(clear_lrawmessage)
            if verify_signature.key_id:
                try:
                    clear_strippedlrawmessage = clear_lrawmessage[clear_lrawmessage.index('{'):clear_lrawmessage.rindex('}')+1]
                except:
                    return False
            else:
                return False
        else:
            print "WARNING: Unsigned message block identified..."
            # TODO: If allow unsigned is set to on we will process this message, else drop it as invalid
            if self.allowUnsignedMessages:
                clear_strippedlrawmessage = clear_lrawmessage
            else:
                return False
        #### Step 3 - Is it a valid JSON message?
        message = Message()
        if message.loadjson(clear_strippedlrawmessage) == False:
            print "Could not decode JSON, dropping message. Message was " + clear_strippedlrawmessage
            return False
        else:
            message.datetime_received =  current_time()
            return message
