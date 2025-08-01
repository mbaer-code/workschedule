# workschedule-cloud/src/models.py
from .__init__ import db # Correctly imports the SQLAlchemy db instance

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    firebase_uid = db.Column(db.String(128), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

    subscription_status = db.Column(db.String(50), default='trial')
    ics_feed_token = db.Column(db.String(64), unique=True, nullable=True) 

    def __repr__(self):
        return f'<User {self.email} (UID: {self.firebase_uid})>'
