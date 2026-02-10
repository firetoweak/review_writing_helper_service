from sqlalchemy.dialects.mysql import LONGTEXT

from conf.db import db
from sqlalchemy import  Column, Integer, String ,Float,and_,DateTime,text,or_,func
from datetime import datetime,timedelta,timezone
class valAiaq(db.Model):
    __tablename__ = 'val_ai_aq'
    id = Column(Integer, primary_key=True)
    question = Column(LONGTEXT, default="")
    answer = Column(LONGTEXT, default="")
    user_id  = Column(Integer, default=0)
    admin_user_id =  Column(Integer, default=0)
    ai_score_id = Column(String(128), default='')
    type  = Column(Integer, default=0)
    create_time = Column(db.DateTime, server_default=func.now(),nullable=False)
    update_time = Column(DateTime,server_default=func.now(), onupdate=func.now(),nullable=False)

    @staticmethod
    def addOne(data):
        newValAiAq = valAiaq(question=data['question'],user_id=data['user_id'],ai_score_id=data['ai_score_id'],answer=data['answer'],type=data['type'],admin_user_id=data['admin_user_id'])
        db.session.add(newValAiAq)
        db.session.commit()
        return newValAiAq.id
    @staticmethod
    def getList(user_id=1,ai_score_id=0,page=1):
        now = datetime.now()
        five_m_ago = now - timedelta(seconds=300)
        paginate  =  valAiaq.query.order_by(valAiaq.id.desc()).filter(or_(and_(valAiaq.user_id == user_id, valAiaq.ai_score_id ==ai_score_id,valAiaq.answer!=""),and_(valAiaq.user_id == user_id, valAiaq.ai_score_id ==ai_score_id,valAiaq.answer=="",valAiaq.create_time>five_m_ago.strftime("%Y-%m-%d %H:%M:%S")))).paginate(page=page, per_page=10, error_out=False)
        items = paginate.items
        return items
    @staticmethod
    def getListByIdStr(idstr:str):
        if idstr=="":
            return []
        sql = f"select ai_score_id,question,answer from val_ai_aq where ai_score_id in ({idstr}) and answer<>'' order by id desc"
        result = db.session.execute(text(sql)).fetchall()
        return result
    @staticmethod
    def setAnswer(answer,id):
        record = valAiaq.query.filter(and_(valAiaq.id == id)).first()
        record.answer = answer
        db.session.commit()
    @staticmethod
    def getAqById(id,user_id):
        record = valAiaq.query.filter(and_(valAiaq.id == id,valAiaq.user_id==user_id)).first()
        return record
    @staticmethod
    def getAdminRecordNum(admin_user_id,type,admin_last_update):
        num  =  valAiaq.query.order_by(valAiaq.id.desc()).filter(and_(valAiaq.admin_user_id == admin_user_id,valAiaq.answer!="",valAiaq.type==type,valAiaq.create_time>=admin_last_update)).count()
        return num
