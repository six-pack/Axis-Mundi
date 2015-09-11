from sqlalchemy import Column, ForeignKey, Integer, String, Boolean, DECIMAL, DateTime, insert
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
#import pycountry
import time
from os.path import isfile
import paginate
from platform import system as get_os


class Storage():

    def __init__(self, passphrase, database, appdir):
        self.database = database
        self.appdir = appdir
        self.passphrase = passphrase
        self.DBSession = sessionmaker

    Base = declarative_base()

    class Config(Base):
        __tablename__ = 'config'
        id = Column(Integer, primary_key=True)
        name = Column(String(250), nullable=False)
        value = Column(String(2048), nullable=False)
        displayname = Column(String(250), nullable=False)

    class PrivateMessaging(Base):
        __tablename__ = 'privatemessaging'
        id = Column(Integer, primary_key=True)
        message_id = Column(String(32), nullable=False)
        sender_key = Column(String(16), nullable=False)
        sender_name = Column(String(64))
        recipient_key = Column(String(16), nullable=False)
        recipient_name = Column(String(64))
        message_date = Column(DateTime)
        # Make sure we enforce a purge date
        message_purge_date = Column(DateTime, nullable=False)
        subject = Column(String(250))
        body = Column(String(32768))         # 32KB limit for PM message body
        parent_message_id = Column(String(32))
        message_read = Column(Boolean)
        message_sent = Column(Boolean)
        message_direction = Column(String(5))

    class Contacts(Base):
        __tablename__ = 'contacts'
        id = Column(Integer, primary_key=True)
        contact_key = Column(String(16), nullable=False)
        contact_name = Column(String(64))
        contact_flags = Column(String(1024))

    class Listings(Base):
        __tablename__ = 'listings'
        id = Column(Integer, primary_key=True)
        title = Column(String(80), nullable=False)
        category = Column(String(255), nullable=False)
        description = Column(String(4096), nullable=False)
        public = Column(Boolean)
        qty_available = Column(Integer)
        order_max_qty = Column(Integer)
        # Column(DECIMAL(8), nullable=False) # sqlalchemy/sqlite doesn't do
        # decimal
        price = Column(String(20), nullable=False)
        currency_code = Column(String, ForeignKey('currencies.code'))
    #    country_id = Column(Integer, ForeignKey('countries.id'))
    #    ships_from = relationship(country_id)
    #    ships_to = relationship(country_id)
        # will hold json list of shipping options
        shipping_options = Column(String())
        image_base64 = Column(String())

    class Orders(Base):
        __tablename__ = 'orders'
        id = Column(Integer, primary_key=True)
        orderid = Column(String(32), nullable=False)
        seller_key = Column(String(16), nullable=False)
        buyer_key = Column(String(16), nullable=False)
        notary_key = Column(String(16))
        order_date = Column(DateTime, nullable=False)
        order_status = Column(String(64), nullable=False)
        delivery_address = Column(String())
        order_note = Column(String())
        order_type = Column(String(16), nullable=False)
        buyer_ephemeral_btc_seed = Column(String(256))
        buyer_btc_pub_key = Column(String(256))
        payment_btc_address = Column(String(80))
        payment_status = Column(String(64))
        seller_btc_stealth = Column(String(80))
        item_id = Column(String(16), nullable=False)
        title = Column(String(80), nullable=False)
        price = Column(String(20), nullable=False)
        currency_code = Column(String, ForeignKey('currencies.code'))
        # will hold json list of shipping options
        shipping_options = Column(String())
        image_base64 = Column(String())
        publish_date = Column(DateTime, nullable=False)
        raw_item = Column(String())  # raw signed item message text of current message chain with signing
        raw_seed = Column(String(), nullable=False)  # raw signed item message text for seed contract
        quantity = Column(Integer)
        shipping = Column(String())
        line_total_price = Column(String(20), nullable=False)
        line_total_btc_price = Column(String(20), nullable=False)
        feedback_left = Column(String())
        feedback_received = Column(String())
        auxillary = Column(String()) # bucket for future use
        session_id = Column(String(32)) # needed to support looking glass mode
        is_synced = Column(Boolean)

    class Countries(Base):
        __tablename__ = 'countries'
        id = Column(Integer, primary_key=True)
        country = Column(String(80), nullable=False)

    class currencies(Base):
        __tablename__ = 'currencies'
        code = Column(String(4), primary_key=True, nullable=False)
        name = Column(String(40), nullable=False)
        exchange_rate = Column(String(10), nullable=False)
        last_update = Column(DateTime) # if blank means never

    class Cart(Base):
        __tablename__ = 'shopping_cart'
        id = Column(Integer, primary_key=True)
        seller_key_id = Column(String(16), nullable=False)
        item_id = Column(String(16), nullable=False)
        title = Column(String(80), nullable=False)
        qty_available = Column(Integer)
        order_max_qty = Column(Integer)
        price = Column(String(20), nullable=False)
        currency_code = Column(String, ForeignKey('currencies.code'))
        # will hold json list of shipping options
        shipping_options = Column(String())
        image_base64 = Column(String())
        publish_date = Column(DateTime, nullable=False)
        seller_btc_stealth = Column(String(80))
        raw_item = Column(String())  # raw signed item message text
        quantity = Column(Integer)
        shipping = Column(String())
        line_total_price = Column(String(20), nullable=False)
        order_type = Column(String(32))
        session_id = Column(String(32)) # needed to support looking glass mode

    class cachePGPKeys(Base):
        __tablename__ = 'cachepgpkeys'
        id = Column(Integer, primary_key=True)
        key_id = Column(String(16), nullable=False)
        updated = Column(DateTime, nullable=False)
        keyblock = Column(String(8192))

    class cacheDirectory(Base):
        __tablename__ = 'cachedirectory'
        id = Column(Integer, primary_key=True)
        key_id = Column(String(16), nullable=False)
        updated = Column(DateTime, nullable=False)
        display_name = Column(String())
        # TODO: Add other key fields but keep it light

    class cacheListings(Base):
        __tablename__ = 'cachelistings'
        id = Column(Integer, primary_key=True)
        key_id = Column(String(16), nullable=False)
        updated = Column(DateTime, nullable=False)
        listings_block = Column(String())

    class cacheItems(Base):
        __tablename__ = 'cacheitems'
        t_id = Column(Integer, primary_key=True)
        id = Column(Integer, nullable=False) # Item id
        key_id = Column(String(16), nullable=False)
        updated = Column(DateTime, nullable=False)
        listings_block = Column(String())
        title = Column(String(80), nullable=False)
        category = Column(String(255), nullable=False)
        description = Column(String(4096), nullable=False)
        qty_available = Column(Integer)
        order_max_qty = Column(Integer)
        price = Column(String(20), nullable=False)
        currency_code = Column(String, ForeignKey('currencies.code'))
        # will hold json list of shipping options
        shipping_options = Column(String())
        image_base64 = Column(String())
        seller_btc_stealth = Column(String(80))
        publish_date = Column(DateTime, nullable=False)

    class cacheProfiles(Base):
        __tablename__ = 'cacheprofiles'
        id = Column(Integer, primary_key=True)
        key_id = Column(String(16), nullable=False)
        updated = Column(DateTime, nullable=False)
        display_name = Column(String(80))
        profile_text = Column(String(4096))
        avatar_base64 = Column(String())  # this does not seem efficient

    def InitDB(self, passphrase, dbfilepath):
        #engine = create_engine('sqlite+pysqlcipher://:PASSPHRASE@/storage.db?cipher=aes-256-cfb&kdf_iter=64000')
        # This next one works although a numeric passphrase must be given
        #        self.engine = create_engine('sqlite+pysqlcipher://:' + passphrase + '/' + dbfilepath)
        print dbfilepath
        # DATABASE ENCRYPTION CAN BE DISABLED/ENABLED HERE
        if get_os() == 'Windows':
            # TESTING ONLY - THIS CREATES A CLEAR-TEXT STORAGE DATABASE!
            self.engine = create_engine(
                r'sqlite+pysqlcipher://:'+passphrase+'/' + dbfilepath, connect_args={'check_same_thread': False}) # Encrypted database
#                r'sqlite:///' + dbfilepath, connect_args={'check_same_thread': False}) # Cleartext database (testing)
            #  poolclass=StaticPool
        else:
            # TESTING ONLY - THIS CREATES A CLEAR-TEXT STORAGE DATABASE!
            self.engine = create_engine(
                'sqlite+pysqlcipher://:'+passphrase+'//' + dbfilepath, connect_args={'check_same_thread': False}) # Encrypted database
#                'sqlite:////' + dbfilepath, connect_args={'check_same_thread': False}) # Cleartext database (testing)
            #  poolclass=StaticPool
        try:
            self.Base.metadata.create_all(self.engine)
        except:
            print "Error creating database"
            return False
        self.Base.metadata.bind = self.engine
        self.DBSession = sessionmaker(bind=self.engine)
        return True
        # Populate initial data

    def Start(self):
        newstoragedb = True
        if isfile(self.appdir + '/' + self.database):
            newstoragedb = False

        if get_os() == 'Windows':
            if self.InitDB(self.passphrase, self.appdir + '\\' + self.database):
                return True
            else:
                if newstoragedb:
                    print "Error creating storage database"
                else:
                    print "Error accessing storage database"
                return False
        else:
            if self.InitDB(self.passphrase, self.appdir + '/' + self.database):
                return True
            else:
                if newstoragedb:
                    print "Error creating storage database"
                else:
                    print "Error accessing storage database"
                return False

    def Stop(self):
        try:
            #            self.engine.close()
            self.engine.remove()
        except:
            print "Error removing DB session"

"""Enhances the paginate.Page class to work with SQLAlchemy objects"""


class SqlalchemyOrmWrapper(object):
    """Wrapper class to access elements of an SQLAlchemy ORM query result."""

    def __init__(self, obj):
        self.obj = obj

    def __getitem__(self, range):
        if not isinstance(range, slice):
            raise Exception("__getitem__ without slicing not supported")
        return self.obj[range]

    def __len__(self):
        return self.obj.count()


class SqlalchemyOrmPage(paginate.Page):

    def __init__(self, *args, **kwargs):
        super(SqlalchemyOrmPage, self).__init__(
            *args, wrapper_class=SqlalchemyOrmWrapper, **kwargs)


class SqlalchemySelectWrapper(object):
    """Wrapper class to access elements of an SQLAlchemy SELECT query."""

    def __init__(self, obj):
        self.obj = obj

    def __getitem__(self, range):
        if not isinstance(range, slice):
            raise Exception("__getitem__ without slicing not supported")
        # value for offset
        offset_v = range.start
        limit = range.stop - range.start
        result = self.obj.sqlalchemy_session.execute(selection).fetchall()
        select = result.offset(offset_v).limit(limit)
        return self.sqlalchemy_session.execute(select).fetchall()

    def __len__(self):
        return self.obj.scalar()


class SqlalchemySelectPage(paginate.Page):

    def __init__(self, *args, **kwargs):
        """sqlalchemy_connection: SQLAlchemy connection object"""
        super(SqlalchemySelectPage, self).__init__(*args, wrapper_class=SqlalchemySelectWrapper,
                                                   **kwargs)
