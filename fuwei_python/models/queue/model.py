from sqlalchemy import Column, Integer, String, func, DateTime, and_

from conf.db import db


class EmailQueue(db.Model):
    __tablename__ = 'email_queue'
    id = Column(Integer, primary_key=True)
    email = Column(String(512), default="")
    content = Column(String(512), default=0)
    status =  Column(Integer, default=0)
    create_time = Column(db.DateTime, server_default=func.now(),nullable=False)
    update_time = Column(DateTime,server_default=func.now(), onupdate=func.now(),nullable=False)

    @staticmethod
    def batch_add_email(datas):
        objects = []
        for data in datas:
            objects.append(EmailQueue(email=data[1], content=data[0]))
        db.session.bulk_save_objects(objects)
        db.session.commit()

    @staticmethod
    def get_all_not_send():
        items  =  EmailQueue.query.order_by(EmailQueue.create_time.asc()).filter(and_(EmailQueue.status == 0)).all()
        return items

    @staticmethod
    def set_status(record_id, status):
        item =  EmailQueue.query.filter(and_(EmailQueue.id == record_id)).first()
        item.status = status
        db.session.commit()


class Smsqueue(db.Model):
    __tablename__ = 'sms_queue'
    id = Column(Integer, primary_key=True)
    admin_user_id  = Column(Integer, default=0)
    type = Column(Integer, default=0)
    e1 = Column(Integer, default=0)
    e2 = Column(Integer, default=0)
    send_num = Column(Integer, default=0)
    module = Column(String(255), default="")
    create_time = Column(db.DateTime, server_default=func.now(),nullable=False)
    update_time = Column(DateTime,server_default=func.now(), onupdate=func.now(),nullable=False)

    @staticmethod
    def add_one(data):
        record = Smsqueue.query.filter(and_(Smsqueue.admin_user_id == data['admin_user_id'], Smsqueue.type == data['type'], Smsqueue.module == data['module'])).first()
        if record is None:
            db.session.add(Smsqueue(admin_user_id=data['admin_user_id'], type=data['type'], module=data['module'], e1=data['e1'], e2=data['e2']))
            db.session.commit()

    @staticmethod
    def get_all():
        return Smsqueue.query.all()

    # @staticmethod
    # def getOne(admin_user_id):
    #     return smsQueue.query.filter(and_(smsQueue.admin_user_id == admin_user_id, user.password ==data['password'],user.status==1,user.is_delete==0)).first()

    @staticmethod
    def set_queue(item, e1, e2):
        print(f"eeeeeeee:{e1},{e2}")
        if item.send_num+1>=5:
            Smsqueue.query.filter(and_(Smsqueue.id == item.id)).delete()
            db.session.commit()
            return ''
        if e1 == 0 and e2 == 0:
            Smsqueue.query.filter(and_(Smsqueue.id == item.id)).delete()
            db.session.commit()
            return ''
        else:
            Smsqueue.query.filter(and_(Smsqueue.id == item.id)).update({"e1":e1, "e2":e2, "send_num":item.send_num})
            db.session.commit()
            return None
