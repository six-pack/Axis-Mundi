def create_defaults(db,session,pgp_keyid,display_name,publish_id):
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
         new_conf_item.value = "jqzxl4pxii7yjcjv.onion"                 # Hardcode in these seed entry points
         new_conf_item.displayname = "Entry Points"
         session.add(new_conf_item)
         new_conf_item = db.Config(name="hubnodes")
         new_conf_item.value = "c6gizttsgqhoqity.onion"                 # Hardcode in these seed entry points
         new_conf_item.displayname = "Entry Points"
         session.add(new_conf_item)
         new_conf_item = db.Config(name="hubnodes")
         new_conf_item.value = "r2j7zovmdkplwfrz.onion"                 # Hardcode in these seed entry points
         new_conf_item.displayname = "Entry Points"
         session.add(new_conf_item)
         new_conf_item = db.Config(name="hubnodes")
         new_conf_item.value = "evdjwy36ugatq2nm.onion"                 # Hardcode in these seed entry points
         new_conf_item.displayname = "Entry Points"
         session.add(new_conf_item)
         new_conf_item = db.Config(name="hubnodes")
         new_conf_item.value = "sq6bvhqsnopp7xqx32v6qriky4zmph7avh4n4jzfvudcqehhqifa.b32.i2p"                 # Hardcode in these i2p seed entry points
         new_conf_item.displayname = "Entry Points"
         session.add(new_conf_item)
         new_conf_item = db.Config(name="hubnodes")
         new_conf_item.value = "o5bgiilpfir7nyofkruggiehk655brlr5xsrkdjdyv3mbpmaesrq.b32.i2p"                 # Hardcode in these i2p seed entry points
         new_conf_item.displayname = "Entry Points"
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
         new_conf_item.value = "9150"
         new_conf_item.displayname = "Tor Proxy Port"
         session.add(new_conf_item)
         new_conf_item = db.Config(name="i2p_proxy")
         new_conf_item.value = "127.0.0.1"
         new_conf_item.displayname = "i2p Proxy"
         session.add(new_conf_item)
         new_conf_item = db.Config(name="i2p_proxy_port")
         new_conf_item.value = "9050"
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
         # Now static data
         # TODO: Countries
         # Currencies
         curr_db_item = db.currencies(code='USD')
         curr_db_item.name = 'US Dollar'
         session.add(curr_db_item)
         curr_db_item = db.currencies(code='EUR')
         curr_db_item.name = 'Euro'
         session.add(curr_db_item)
         curr_db_item = db.currencies(code='BTC')
         curr_db_item.name = 'Bitcoin'
         session.add(curr_db_item)
         curr_db_item = db.currencies(code='ZAR')
         curr_db_item.name = 'South African Rand'
         session.add(curr_db_item)
         curr_db_item = db.currencies(code='AUD')
         curr_db_item.name = 'Australian Dollar'
         session.add(curr_db_item)
         curr_db_item = db.currencies(code='GBP')
         curr_db_item.name = 'British Pound'
         session.add(curr_db_item)
         curr_db_item = db.currencies(code='CAD')
         curr_db_item.name = 'Canadian Dollar'
         session.add(curr_db_item)
         curr_db_item = db.currencies(code='SEK')
         curr_db_item.name = 'Swedish Krone'
         session.add(curr_db_item)    
         curr_db_item = db.currencies(code='ISK')
         curr_db_item.name = 'Icelandic Krona'
         session.add(curr_db_item) 
         curr_db_item = db.currencies(code='NOK')
         curr_db_item.name = 'Norwegian Krone'
         session.add(curr_db_item) 
         curr_db_item = db.currencies(code='DKK')
         curr_db_item.name = 'Danish Krone'
         session.add(curr_db_item) 
         curr_db_item = db.currencies(code='RUB')
         curr_db_item.name = 'Russian Ruble'
         session.add(curr_db_item) 
                  # Finally commit
         session.commit()
         return True
    except:
         session.rollback()
         return False
