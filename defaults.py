def create_defaults(db, session, pgp_keyid, display_name, publish_id, btc_master_seed):
    try:
        # Identity default settings
        new_conf_item = db.Config(name="pgpkeyid")
        new_conf_item.value = pgp_keyid
        new_conf_item.displayname = "My PGP Key ID"
        session.add(new_conf_item)
        new_conf_item = db.Config(name="displayname")
        new_conf_item.value = display_name
        new_conf_item.displayname = "Name"
        session.add(new_conf_item)
        new_conf_item = db.Config(name="publish_identity")
        new_conf_item.value = str(publish_id)
        new_conf_item.displayname = "Publish To Directory"
        session.add(new_conf_item)
        # Network default settings
        new_conf_item = db.Config(name="hubnodes")
        # Hardcode in these seed entry points
        new_conf_item.value = "jqzxl4pxii7yjcjv.onion"
        new_conf_item.displayname = "Entry Points"
        session.add(new_conf_item)
        new_conf_item = db.Config(name="hubnodes")
        # Hardcode in these seed entry points
        new_conf_item.value = "c6gizttsgqhoqity.onion"
        new_conf_item.displayname = "Entry Points"
        session.add(new_conf_item)
        new_conf_item = db.Config(name="hubnodes")
        # Hardcode in these seed entry points
        new_conf_item.value = "r2j7zovmdkplwfrz.onion"
        new_conf_item.displayname = "Entry Points"
        session.add(new_conf_item)
        new_conf_item = db.Config(name="hubnodes")
        # Hardcode in these seed entry points
        new_conf_item.value = "evdjwy36ugatq2nm.onion"
        new_conf_item.displayname = "Entry Points"
        session.add(new_conf_item)
        new_conf_item = db.Config(name="hubnodes")
        # Hardcode in these i2p seed entry points
        new_conf_item.value = "sq6bvhqsnopp7xqx32v6qriky4zmph7avh4n4jzfvudcqehhqifa.b32.i2p"
        new_conf_item.displayname = "Entry Points"
        session.add(new_conf_item)
        new_conf_item = db.Config(name="hubnodes")
        # Hardcode in these i2p seed entry points
        new_conf_item.value = "o5bgiilpfir7nyofkruggiehk655brlr5xsrkdjdyv3mbpmaesrq.b32.i2p"
        new_conf_item.displayname = "Entry Points"
        session.add(new_conf_item)
        new_conf_item = db.Config(name="stratum_servers")
        # Hardcode in these servers from electrum
        new_conf_item.value = "electrum.be:50002:s"
        new_conf_item.displayname = "Stratum Servers"
        session.add(new_conf_item)
        new_conf_item = db.Config(name="stratum_servers")
        # Hardcode in these servers from electrum
        new_conf_item.value = "electrum.bitfuzz.nl:50002:s"
        new_conf_item.displayname = "Stratum Servers"
        session.add(new_conf_item)
        new_conf_item = db.Config(name="stratum_servers")
        # Hardcode in these servers from electrum
        new_conf_item.value = "h.1209k.com:50002:s"
        new_conf_item.displayname = "Stratum Servers"
        session.add(new_conf_item)
        new_conf_item = db.Config(name="stratum_servers")
        # Hardcode in these servers from electrum
        new_conf_item.value = "erbium.sytes.net:50002:s"
        new_conf_item.displayname = "Stratum Servers"
        session.add(new_conf_item)
        new_conf_item = db.Config(name="stratum_servers")
        # Hardcode in these servers from electrum
        new_conf_item.value = "ecdsa.net:50002:s"
        new_conf_item.displayname = "Stratum Servers"
        session.add(new_conf_item)
        new_conf_item = db.Config(name="stratum_servers")
        # Hardcode in these servers from electrum
        new_conf_item.value = "electrum.no-ip.org:50002:s"
        new_conf_item.displayname = "Stratum Servers"
        session.add(new_conf_item)
        new_conf_item = db.Config(name="stratum_servers")
        # Hardcode in these servers from electrum
        new_conf_item.value = "bitcoin.epicinet.net:50002:s"
        new_conf_item.displayname = "Stratum Servers"
        session.add(new_conf_item)
        new_conf_item = db.Config(name="stratum_servers")
        # Hardcode in these servers from electrum
        new_conf_item.value = "kirsche.emzy.de:50002:s"
        new_conf_item.displayname = "Stratum Servers"
        session.add(new_conf_item)
        new_conf_item = db.Config(name="stratum_servers")
        # Hardcode in these servers from electrum
        new_conf_item.value = "electrum.mindspot.org:50002:s"
        new_conf_item.displayname = "Stratum Servers"
        session.add(new_conf_item)
        new_conf_item = db.Config(name="stratum_servers")
        # Hardcode in these servers from electrum
        new_conf_item.value = "ecdsa.net:110:s"
        new_conf_item.displayname = "Stratum Servers"
        session.add(new_conf_item)
        new_conf_item = db.Config(name="stratum_servers")
        # Hardcode in these servers from electrum
        new_conf_item.value = "electrum.thwg.org:50002:s"
        new_conf_item.displayname = "Stratum Servers"
        session.add(new_conf_item)
        new_conf_item = db.Config(name="socks_enabled")
        new_conf_item.value = "True"
        new_conf_item.displayname = "SOCKS Proxy Enabled"
        session.add(new_conf_item)
        new_conf_item = db.Config(name="i2p_socks_enabled")
        new_conf_item.value = "False"
        new_conf_item.displayname = "i2p SOCKS Proxy Enabled"
        session.add(new_conf_item)
        new_conf_item = db.Config(name="proxy")
        new_conf_item.value = "127.0.0.1"
        new_conf_item.displayname = "Tor Proxy"
        session.add(new_conf_item)
        new_conf_item = db.Config(name="proxy_port")
        new_conf_item.value = "9050" # TODO investigate on what systems this is 9150?
        new_conf_item.displayname = "Tor Proxy Port"
        session.add(new_conf_item)
        new_conf_item = db.Config(name="i2p_proxy")
        new_conf_item.value = "127.0.0.1"
        new_conf_item.displayname = "i2p Proxy"
        session.add(new_conf_item)
        new_conf_item = db.Config(name="i2p_proxy_port")
        new_conf_item.value = "1080"
        new_conf_item.displayname = "i2p Proxy Port"
        session.add(new_conf_item)
        # Security default settings
        new_conf_item = db.Config(name="message_retention")
        new_conf_item.value = "30"
        new_conf_item.displayname = "Message Retention Period"
        session.add(new_conf_item)
        new_conf_item = db.Config(name="accept_unsigned")
        new_conf_item.value = "True"
        new_conf_item.displayname = "Accept Unsigned Messages"
        session.add(new_conf_item)
        # Trade default settings
        new_conf_item = db.Config(name="wallet_seed")
        new_conf_item.value = btc_master_seed
        new_conf_item.displayname = "Wallet Seed"
        session.add(new_conf_item)
        new_conf_item = db.Config(name="market_directory_helpers")
        new_conf_item.value = "1234567812345678"
        new_conf_item.displayname = "Market Directory Helpers"
        session.add(new_conf_item)
        new_conf_item = db.Config(name="market_notary_helpers")
        new_conf_item.value = "1234567812345678"
        new_conf_item.displayname = "Market Notaries"
        session.add(new_conf_item)
        new_conf_item = db.Config(name="market_listing_helpers")
        new_conf_item.value = "1234567812345678"
        new_conf_item.displayname = "Market Listing Helpers"
        session.add(new_conf_item)
        new_conf_item = db.Config(name="market_feedback_helpers")
        new_conf_item.value = "1234567812345678"
        new_conf_item.displayname = "Market Feedback Helpers"
        session.add(new_conf_item)
        new_conf_item = db.Config(name="is_looking_glass")
        new_conf_item.value = "False"
        new_conf_item.displayname = "Looking Glass mode"
        session.add(new_conf_item)
        new_conf_item = db.Config(name="is_notary")
        new_conf_item.value = "False"
        new_conf_item.displayname = "Act as a notary"
        session.add(new_conf_item)
        new_conf_item = db.Config(name="is_arbiter")
        new_conf_item.value = "False"
        new_conf_item.displayname = "Act as an arbiter"
        session.add(new_conf_item)
        session.commit()
        # Now static data
        # TODO: Countries
        # Currencies
        curr_db_item = db.currencies(code='USD')
        curr_db_item.name = 'US Dollar'
        curr_db_item.exchange_rate = 0
        session.add(curr_db_item)
        curr_db_item = db.currencies(code='EUR')
        curr_db_item.name = 'Euro'
        curr_db_item.exchange_rate = 0
        session.add(curr_db_item)
        curr_db_item = db.currencies(code='BTC')
        curr_db_item.name = 'Bitcoin'
        curr_db_item.exchange_rate = 1
        session.add(curr_db_item)
        curr_db_item = db.currencies(code='ZAR')
        curr_db_item.name = 'South African Rand'
        curr_db_item.exchange_rate = 0
        session.add(curr_db_item)
        curr_db_item = db.currencies(code='AUD')
        curr_db_item.name = 'Australian Dollar'
        curr_db_item.exchange_rate = 0
        session.add(curr_db_item)
        curr_db_item = db.currencies(code='GBP')
        curr_db_item.name = 'British Pound'
        curr_db_item.exchange_rate = 0
        session.add(curr_db_item)
        curr_db_item = db.currencies(code='CAD')
        curr_db_item.name = 'Canadian Dollar'
        curr_db_item.exchange_rate = 0
        session.add(curr_db_item)
        curr_db_item = db.currencies(code='SEK')
        curr_db_item.name = 'Swedish Krone'
        curr_db_item.exchange_rate = 0
        session.add(curr_db_item)
        curr_db_item = db.currencies(code='ISK')
        curr_db_item.name = 'Icelandic Krona'
        curr_db_item.exchange_rate = 0
        session.add(curr_db_item)
        curr_db_item = db.currencies(code='NOK')
        curr_db_item.name = 'Norwegian Krone'
        curr_db_item.exchange_rate = 0
        session.add(curr_db_item)
        curr_db_item = db.currencies(code='DKK')
        curr_db_item.name = 'Danish Krone'
        curr_db_item.exchange_rate = 0
        session.add(curr_db_item)
        curr_db_item = db.currencies(code='RUB')
        curr_db_item.name = 'Russian Ruble'
        curr_db_item.exchange_rate = 0
        session.add(curr_db_item)
        # Finally commit
        session.commit()
        return True
    except:
        session.rollback()
        return False
