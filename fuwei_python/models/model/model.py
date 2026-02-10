from conf.db import db
from sqlalchemy import Column, Integer, String, Float, and_, DateTime, SmallInteger, func, ForeignKey, Enum
import enum

class AntiShakeStatus(enum.Enum):
    """缺陷整体状态枚举"""
    OPEN = 'open'
    CLOSED = 'closed'


class Models(db.Model):
    __tablename__ = 'models'
    id = Column(Integer, primary_key=True)
    name = Column(String(128), default="")
    using = Column(Integer, default=0)
    key_name = Column(String(128), default="")
    base_url = Column(String(256), default="")
    model_name = Column(String(128), default="")
    api_key = Column(String(256), default="")
    aiConfig = {"base_url":"","api_key":"","model_name":"","name":""}
    def to_dict(self):
        return {
            column.name: getattr(self, column.name)for column in self.__table__.columns
        }
    @staticmethod
    def editOne(data={}):
        Models.query.update({"using":0})
        db.session.commit()
        record = Models.query.filter(and_(Models.id == data['id'])).first()
        record.using = 1
        db.session.commit()
        Models.aiConfig['base_url'] = ""
        Models.aiConfig['api_key'] = ""
        Models.aiConfig['model_name'] = ""
        Models.aiConfig['model_name'] = ""


    @staticmethod
    def getAll():
        return Models.query.all()

    @staticmethod
    def getUsingModel():
        if Models.aiConfig['base_url'] == "":
            record = Models.query.filter(and_(Models.using == 1)).first()
            Models.aiConfig['base_url'] = record.base_url
            Models.aiConfig['api_key'] = record.api_key
            Models.aiConfig['model_name'] = record.model_name
            Models.aiConfig['name'] = record.name
            return Models.aiConfig
        else:
            return Models.aiConfig

    @staticmethod
    def getQwPlus():
        record = Models.query.filter(and_(Models.key_name == 'ali-qwen-plus')).first()
        config = {"base_url":record.base_url,"api_key":record.api_key,"model_name":record.model_name,"name":record.name}
        return config

    @staticmethod
    def getModuleModel(model_id):
        record = Models.query.filter(and_(Models.id == model_id)).first()
        config = {"base_url": record.base_url, "api_key": record.api_key, "model_name": record.model_name,"name":record.name}
        return config

class ModuleToModel(db.Model):
    __tablename__ = 'module_to_model'
    id = Column(Integer, primary_key=True)
    module = Column(Integer, default=0)
    model_id = Column(Integer,ForeignKey('models.id', ondelete='CASCADE'), default=0)
    anti_shake_status = Column(String(20), Enum(AntiShakeStatus), nullable=False, default=AntiShakeStatus.CLOSED)
    create_time = Column(db.DateTime, server_default=func.now(), nullable=False)
    update_time = Column(db.DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    model = db.relationship('Models', backref='ModuleToModel', lazy=True)

    def to_dict(self):
        return {
            column.name: getattr(self, column.name)for column in self.__table__.columns
        }

    @staticmethod
    def add_one(data):
        db.session.query(ModuleToModel).filter(ModuleToModel.module == data['module']).delete()
        if str(data['id']) != "0":
            db.session.add(ModuleToModel(module=data['module'], model_id=data['id']))
        db.session.commit()

    @staticmethod
    def edit_one(data):
        record = ModuleToModel.get_module_model(data['module'])
        record.model_id = data['model']
        record.anti_shake_status = data['shake']
        db.session.commit()

    @staticmethod
    def get_all():
        items = ModuleToModel.query.all()
        data = {}
        for item in items:
            data[str(item.module)] = {}
            data[str(item.module)]['id'] = item.model_id
            data[str(item.module)]['anti_shake_status'] = item.anti_shake_status

        return data

    @staticmethod
    def get_module_model(module):
        record = ModuleToModel.query.filter(and_(ModuleToModel.module == module)).first()
        if record is not None:
            return record
        else:
            return None