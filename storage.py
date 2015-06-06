from sqlalchemy import Column, ForeignKey, Integer, String, Boolean, DECIMAL,DateTime, insert
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

    def __init__ (self, passphrase, database, appdir):
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
        message_purge_date = Column(DateTime, nullable=False) # Make sure we enforce a purge date
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
        description = Column(String(4096), nullable=False)
        public = Column(Boolean)
        quantity = Column(Integer)
        max_order_quantity = Column(Integer)
        price = Column(DECIMAL(8), nullable=False)
        currency_code = Column(String, ForeignKey('currencies.code'))
        currency = relationship('currencies')
        country_id = Column(Integer, ForeignKey('countries.id'))
    #    ships_from = relationship(country_id)
    #    ships_to = relationship(country_id)
        # shipping?

    class Orders(Base):
        __tablename__ = 'orders'
        id = Column(Integer, primary_key=True)
        orderid = Column(String(32), nullable=False)
        seller_key = Column(String(16), nullable=False)
        seller_name = Column(String(64))
        buyer_key = Column(String(16), nullable=False)
        buyer_name = Column(String(64))
        notary_key = Column(String(16))
        notary_name = Column(String(64))
        order_date = Column(DateTime, nullable=False)
        order_status = Column(String(64))
        #, product title, prod description, quatity, seller, buyer, encrypted address(!), total price, notes, status, relevant timestamps

    class Countries(Base):
        __tablename__ = 'countries'
        id = Column(Integer, primary_key=True)
        country = Column(String(80), nullable=False)

    class currencies(Base):
        __tablename__ = 'currencies'
        code = Column(String(4), primary_key=True, nullable=False)
        name = Column(String(40), nullable=False)

    class cachePGPKeys(Base):
        __tablename__ = 'cachepgpkeys'
        id = Column(Integer, primary_key=True)
        key_id = Column(String(16), nullable=False)
        updated = Column(DateTime, nullable=False)
        keyblock = Column(String(8192))

    class cacheProfiles(Base):
        __tablename__ = 'cacheprofiles'
        id = Column(Integer, primary_key=True)
        key_id = Column(String(16), nullable=False)
        updated = Column(DateTime, nullable=False)
        display_name = Column(String(80))
        profile_text = Column(String(4096))
        avatar_base64 = Column(String()) # this does not seem efficient

    def InitDB(self,passphrase,dbfilepath):
        #engine = create_engine('sqlite+pysqlcipher://:PASSPHRASE@/storage.db?cipher=aes-256-cfb&kdf_iter=64000')
        # This next one works although a numeric passphrase must be given
#        self.engine = create_engine('sqlite+pysqlcipher://:' + passphrase + '/' + dbfilepath)
        print dbfilepath
        if get_os() == 'Windows':
            self.engine = create_engine(r'sqlite:///' + dbfilepath, connect_args={'check_same_thread':False})  # TESTING ONLY - THIS CREATES A CLEAR-TEXT STORAGE DATABASE!
                                                                #  poolclass=StaticPool
        else:
            self.engine = create_engine('sqlite:////' + dbfilepath, connect_args={'check_same_thread':False})  # TESTING ONLY - THIS CREATES A CLEAR-TEXT STORAGE DATABASE!
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
            if self.InitDB(self.passphrase, self.appdir + '\\' +self.database):
                    return True
            else:
                if newstoragedb: print "Error creating storage database"
                else: print "Error accessing storage database"
                return False
        else:
            if self.InitDB(self.passphrase, self.appdir + '/' +self.database):
                    return True
            else:
                if newstoragedb: print "Error creating storage database"
                else: print "Error accessing storage database"
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
        super(SqlalchemyOrmPage, self).__init__(*args, wrapper_class=SqlalchemyOrmWrapper, **kwargs)

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

