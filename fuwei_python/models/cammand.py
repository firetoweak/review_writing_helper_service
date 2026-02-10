from conf.db import db
from sqlalchemy import  Column, Integer, String ,Float,and_,DateTime, Text
class cammand(db.Model):
    __tablename__ = 'cammand'
    id = Column(Integer, primary_key=True)
    step1 = Column(Text, default="")
    step2 = Column(Text, default="")
    step3 = Column(Text, default="")
    step4 = Column(Text, default="")
    type = Column(Integer, default=0)
    all = Column(Text, default=0)
    name = Column(String(255), default="")
    type_child = Column(Integer, default=0)
    @staticmethod
    def editOne(data):
        record = cammand.query.filter(and_(cammand.id == data['id'])).first()
        record.all = data['all']
        db.session.commit()

    @staticmethod
    def getOne(type,type_child=0):
        record = cammand.query.filter(and_(cammand.type == type,cammand.type_child == type_child)).first()
        return record

    @staticmethod
    def getCammand(type,type_child=0)->str:
        record = cammand.getOne(type,type_child)
        return record.all

    @staticmethod
    def adminGetAll():
        records = cammand.query.all()
        return records

    @staticmethod
    def getCammandCase(type_child):
        print(type_child)
        record = cammand.query.filter(and_(cammand.type == 4,cammand.type_child == type_child)).first()
        print(record)
        return record
