from conf.db import db
from sqlalchemy import Column, Integer, String, Float, and_, DateTime, Text
from datetime import datetime
class docAiaq(db.Model):
    __tablename__ = 'doc_ai_aq'
    id = Column(Integer, primary_key=True)
    file_id= Column(Integer, default=0)
    question = Column(Text, default="")
    anwser = Column(Text, default="")
    create_time = Column(db.DateTime, default=datetime.now())

    @staticmethod
    def addOne(data):
        db.session.add(docAiaq(question=data['question'],anwser=data['anwser']))
        db.session.commit()
    @staticmethod
    def getList():
        items  =  docAiaq.query.order_by(docAiaq.id.desc()).offset(0).limit(10).all()
        return items
