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
         new_conf_item = db.Config(name="proxy")
         new_conf_item.value = "127.0.0.1"
         new_conf_item.displayname = "Proxy"
         session.add(new_conf_item)
         new_conf_item = db.Config(name="proxy_port")
         new_conf_item.value = "9050"
         new_conf_item.displayname = "Proxy Port"
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
         # Finally commit
         session.commit()
         return True
    except:
         session.rollback()
         return False
