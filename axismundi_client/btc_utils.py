import pybitcointools as btc


def create_stealth_address(spend_pubkey, magic_byte=42):
    # magic_byte = 42 for mainnet, 43 for testnet.
    hex_spendkey = btc.encode_pubkey(spend_pubkey, 'hex_compressed')
    hex_data = '00{0:066x}'.format(int(hex_spendkey, 16))
    addr = btc.hex_to_b58check(hex_data, magic_byte)
    return addr


def sender_payee_address_from_stealth(sender_prikey, receiver_pubkey):
    # sender - derive payee address
    ss1 = btc.multiply(receiver_pubkey, sender_prikey)
    ss2 = btc.sha256(btc.encode_pubkey((ss1), 'bin_compressed'))
    addr = btc.pubkey_to_address(btc.add_pubkeys(
        receiver_pubkey, btc.privtopub(ss2)))
    return addr


def receiver_payee_privkey_from_stealth(receiver_prikey, sender_pubkey):
    # sender - derive payee address
    ss1 = btc.multiply(sender_pubkey, receiver_prikey)
    ss2 = btc.sha256(btc.encode_pubkey((ss1), 'bin_compressed'))
    key = btc.add_privkeys(receiver_prikey, ss2)
    return key

### general btc utils

def is_btc_address(bc):
    # TODO: This check needs to be a little more effective...
    return True

