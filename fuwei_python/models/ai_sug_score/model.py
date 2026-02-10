from flask import session

from common.aliOss import aliOss
from conf.db import db
from sqlalchemy import Column, Integer, String, Text, and_, DateTime, func, or_, ForeignKey, SmallInteger
from flask_paginate import  get_page_args,Pagination
from models.users.models import User
import pandas as pd
import re
class AiSugScore(db.Model):
    __tablename__ = 'ai_sug_score'
    id = Column(String(128), primary_key=True)
    step1 = Column(Text,default="")
    step2 = Column(Text,default="")
    step3 =  Column(Text,default="")
    step4 =  Column(Text,default="")
    ai_step1 =  Column(Text,default="")
    ai_step2 = Column(Text,default="")
    ai_step3 = Column(Text,default="")
    ai_step4 = Column(Text,default="")
    step1_score = Column(Integer,default=0)
    step2_score = Column(Integer,default=0)
    step3_score = Column(Integer,default=0)
    step4_score = Column(Integer,default=0)
    user_id = Column(Integer,default=0)
    type = Column(Integer,default=0)
    admin_user_id = Column(Integer,default=0)
    state = Column(Integer,default=0)
    is_delete  = Column(Integer,default=0)
    is_admin_delete = Column(Integer,default=0)
    error_mess = Column(Text,default="")
    model_name =  Column(String(64),default="")
    create_time = Column(db.DateTime, server_default=func.now(),nullable=False)
    update_time = Column(DateTime,server_default=func.now(), onupdate=func.now(),nullable=False)
    defect_id = Column(Integer,default=None)
    anti_shake_logs = db.relationship('AntiShakeLog', backref='AiSugScore', lazy="joined")
    defect = db.relationship(
        'Defect',
        primaryjoin='AiSugScore.defect_id == Defect.id',
        foreign_keys='AiSugScore.defect_id', #逻辑外键
        #backref=db.backref('defect', lazy='subquery'),  # 使用子查询替代 JOIN
        lazy='joined',
    )

    def to_dict(self):
        return {
            column.name: getattr(self, column.name)for column in self.__table__.columns
        }
    #aqs = relationship("valAiaq", backref="ai_sug_score")
    pageShowConfig = [
        {
         'title_list':'产品缺陷管理',
         'title_add':'产品缺陷管理工作质量评估新增',
         'title_edit':'产品缺陷管理工作质量评估编辑',
         'title_result': '产品缺陷管理工作质量评估结果',
         'step1':'产品缺陷描述','step2':'原因分析','step3':'解决措施实施','step4':'回归测试',
         'menu-step1': '产品缺陷', 'menu-step2': '原因分析', 'menu-step3': '解决措施', 'menu-step4': '回归测试',
        },
        {
        "title_list": '产品需求管理',
        'title_add': '产品需求管理新增',
        'title_edit': '产品需求管理新增编辑',
        'step1': '需求描述', 'step2': '需求分析','step3': '需求决策', 'step4': '验证结果',
        'menu-step1': '需求描述', 'menu-step2': '需求分析', 'menu-step3': '需求决策', 'menu-step4': '验证结果',

        },
    ]
    uploadFiles = [
                    ["产品缺陷批量导入.xlsx","产品缺陷批量导入.zip"],
                    ["产品需求批量导入.xlsx", "产品需求批量导入.zip"],
            ]
    columnStep = ["step1","step2","step3","step4"]
    @staticmethod
    def add_one(data):
        state = data['state'] if "state" in data else 0
        defect_id = data['defect_id']  if 'defect_id' in  data else None
        db.session.add(AiSugScore(id=data['id'],step1=data['step1'],step2=data['step2'],step3=data['step3'],step4=data['step4'],user_id=data['user_id'],type=data['type'],state=state,admin_user_id=data['admin_user_id'],defect_id=defect_id))
        db.session.commit()

    @staticmethod
    def get_list(user_id=1, record_type=0, state=1, search="",ai_sug_score_id=""):
        page, per_page, offset = get_page_args(page_parameter='page', per_page_parameter='per_page')
        query   =  AiSugScore.query.outerjoin(AiSugScore.defect).order_by(AiSugScore.create_time.desc()).filter(and_( AiSugScore.type == record_type, AiSugScore.is_delete == 0))
        if state !="":
            query = query.filter(and_(AiSugScore.state == state))
        if search!="":
            search = f'%{search}%'
            query = query.filter(or_(AiSugScore.step1.like(search),AiSugScore.step2.like(search),AiSugScore.step3.like(search),AiSugScore.step4.like(search)))
        if ai_sug_score_id!="":
            query = query.filter(and_(AiSugScore.id == ai_sug_score_id,AiSugScore.admin_user_id == session['admin_user_id']))
        else:
            query = query.filter(and_(AiSugScore.user_id == user_id))
        total = query.count()
        items = query.offset(offset).limit(per_page).all()
        pagination = Pagination(
            page=page,
            per_page=per_page,
            total=total,
            css_framework='bootstrap5',  # 支持 bootstrap4/bootstrap5/foundation 等
            alignment = 'right',  # 分页居中
            prev_label = '<',  # 自定义上一页文本
            next_label = '>',  # 自定义下一页文本
        )
        return pagination,items
    @staticmethod
    def get_one(user_id=1, id=0):
        item =  AiSugScore.query.filter(and_(AiSugScore.user_id == user_id, AiSugScore.id ==id,AiSugScore.is_delete==0)).first()
        return item
    @staticmethod
    def editOne(data):
        record = AiSugScore.get_one(user_id=data['user_id'], id=data['id'])
        record.step1 = data['step1']
        record.step2 = data['step2']
        record.step3 = data['step3']
        record.step4 = data['step4']
        if "state" in data:
            state = data['state']
        else:
            state = 0
        record.state = state
        db.session.commit()
    @staticmethod
    def edit_ai(data):
        record = AiSugScore.get_one(user_id=data['user_id'], id=data['id'])
        record.ai_step1 = data['ai_step1']
        record.ai_step2 = data['ai_step2']
        record.ai_step3 = data['ai_step3']
        record.ai_step4 = data['ai_step4']
        record.step1_score = data['step1_score']
        record.step2_score = data['step2_score']
        record.step3_score = data['step3_score']
        record.step4_score = data['step4_score']
        record.step4_score = data['step4_score']
        record.model_name = data['model_name']
        record.state = 1
        db.session.commit()
    @staticmethod
    def getAllExport(user_id=0,type=0,state=1):
        items  =  AiSugScore.query.filter(and_(AiSugScore.user_id == user_id, AiSugScore.type ==type,AiSugScore.state==state,AiSugScore.is_delete==0)).all()
        return items

    @staticmethod
    def getBatchExec(user_id):
        items  =  AiSugScore.query.order_by(AiSugScore.create_time.asc()).filter(and_(AiSugScore.state==-1,AiSugScore.is_delete==0,AiSugScore.user_id==user_id)).all()
        return items

    @staticmethod
    def getAdminUserRecordNum(admin_user_id,type,admin_last_update):
        num = AiSugScore.query.order_by(AiSugScore.create_time.asc()).filter(and_(AiSugScore.state == 1, AiSugScore.admin_user_id == admin_user_id,AiSugScore.type == type,AiSugScore.create_time>=admin_last_update)).count()
        return num

    @staticmethod
    def get_user_ai_sug_score(record_type, search):
        page, per_page, offset = get_page_args(page_parameter='page', per_page_parameter='per_page')
        query = db.session.query(AiSugScore).join(User,User.user_id == AiSugScore.user_id)
        query = query.filter(AiSugScore.state == 1)
        query = query.filter(AiSugScore.is_admin_delete == 0)
        if record_type>=0:
            query = query.filter(AiSugScore.type == record_type)
        if search!="":
            if  re.match( r'^1\d{10}$', search):
                u =  User.get_one_mobile_user(search)
                if u==None:
                    admin_user_id = -1
                else:
                    admin_user_id = u.user_id
                query = query.filter(or_(User.admin_user_id == admin_user_id,User.user_id==admin_user_id))
            elif re.match(r'^(\w)+(\.\w+)*@(\w)+((\.\w+)+)$',search):
                query = query.filter(User.email == search)
            else:
                query = query.filter(AiSugScore.id == search)
        total = query.count()
        query = query.add_entity(User)
        results = query.order_by(AiSugScore.create_time.desc()).offset(offset).limit(per_page).all()
        pagination = Pagination(
            page=page,
            per_page=per_page,
            total=total,
            css_framework='bootstrap'  # 支持 bootstrap4/bootstrap5/foundation 等
        )
        return pagination,results
    @staticmethod
    def getMarkDownData(item):
        if item.type == 0:
            pandaData = {
                '评估项': ['产品缺陷描述', '原因分析', '解决措施实施', '回归测试'],
                '内容': [item.step1, item.step2, item.step3, item.step4],
                'AI建议': [item.ai_step1, item.ai_step2, item.ai_step3, item.ai_step4],
                '评分': [item.step1_score, item.step2_score, item.step3_score, item.step4_score],
            }
        else:
            pandaData = {
                '评估项': ['需求描述', '需求分析', '需求决策', '验证结果'],
                '内容': [item.step1, item.step2, item.step3, item.step4],
                'AI建议': [item.ai_step1, item.ai_step2, item.ai_step3, item.ai_step4],
                '评分': [item.step1_score, item.step2_score, item.step3_score, item.step4_score],
            }
        df = pd.DataFrame(pandaData)
        markdown_table = df.to_html()
        return markdown_table
    @staticmethod
    def getIndexTotal(user_id):
        total0 = AiSugScore.query.filter(and_(AiSugScore.user_id == user_id, AiSugScore.type == 0,AiSugScore.is_delete==0)).count()
        total1 = AiSugScore.query.filter(and_(AiSugScore.user_id == user_id, AiSugScore.type == 1,AiSugScore.is_delete==0)).count()
        return total0,total1
    @staticmethod
    def editAiIngState(data):
        record = AiSugScore.get_one(user_id=data['user_id'], id=data['id'])
        record.state = -2
        db.session.commit()
    @staticmethod
    def edit_ai_false_state(data, mess):
        record = AiSugScore.get_one(user_id=data['user_id'], id=data['id'])
        record.state = data['state']
        record.error_mess = record.error_mess+mess
        db.session.commit()
    @staticmethod
    def deleteUserAiSugScore(id,user_id):
        AiSugScore.query.filter(and_(AiSugScore.user_id==user_id,AiSugScore.id==id,AiSugScore.state!=-1,AiSugScore.state!=-2)).update({'is_delete': 1}, synchronize_session=False)
        db.session.commit()

    @staticmethod
    def adminDeleteAiSugScore(id):
        AiSugScore.query.filter(and_(AiSugScore.id==id)).update({'is_admin_delete': 1}, synchronize_session=False)
        db.session.commit()
    @staticmethod
    def edit_ai_save_state(data):
        record = AiSugScore.get_one(user_id=data['user_id'], id=data['id'])
        record.state = 0
        db.session.commit()
    @staticmethod
    def getDateTypeExport(user_id=0,type=0,state=1,b_date="",e_date="",is_admin=0):
        query = AiSugScore.query.filter(and_(AiSugScore.type ==type,AiSugScore.state==state))
        if is_admin==1:
            query = query.filter(and_(AiSugScore.is_admin_delete==0))
        else:
            query = query.filter(and_(AiSugScore.is_delete==0))
        if user_id>0:
            query = query.filter(and_(AiSugScore.user_id == user_id))
        if b_date!="":
            query = query.filter(and_(AiSugScore.create_time > b_date))
        if e_date!="":
            query = query.filter(and_(AiSugScore.create_time < e_date))
        return query.all()


    @staticmethod
    def get_pay_load(data, record_type):
        data['step1'],tag,ai_urls = aliOss.get_ai_contents(data['user_id'],data['step1'],0,{})
        data['step2'],tag,ai_urls = aliOss.get_ai_contents(data['user_id'],data['step2'],tag,ai_urls)
        data['step3'],tag,ai_urls = aliOss.get_ai_contents(data['user_id'],data['step3'],tag,ai_urls)
        data['step4'],tag,ai_urls = aliOss.get_ai_contents(data['user_id'],data['step4'],tag,ai_urls)

        if str(record_type)== '0':
            payload = {
                    "user": {
                        'text':{
                            "产品缺陷描述": data['step1'],
                            "原因分析": data['step2'],
                            "解决措施实施":  data['step3'],
                            "回归测试":  data['step4'],
                            },
                        "image_url": ai_urls,
                    },
                    "type": 100
            }
        else:
            payload = {
                    "user": {
                            'text': {
                                "需求描述": data['step1'],
                                "需求分析": data['step2'],
                                "需求决策": data['step3'],
                                "验证结果": data['step4'],
                            },
                        "image_url": ai_urls,
                    },
                "type": 101
            }
        return payload


class AntiShakeLog(db.Model):
    __tablename__ = 'anti_shake_log'
    id = Column(Integer, primary_key=True)
    val_id = Column(Integer,ForeignKey('ai_sug_score.id', ondelete='CASCADE'),nullable=True,comment="")
    type = Column(SmallInteger, nullable=False)
    content = Column(Text, default="")
    create_time = Column(db.DateTime, server_default=func.now(),nullable=False)
    update_time = Column(DateTime,server_default=func.now(), onupdate=func.now(),nullable=False)
    def to_dict(self):
        return {
            column.name: getattr(self, column.name)for column in self.__table__.columns
        }
    @staticmethod
    def add_one(data):
        record = AntiShakeLog(val_id=data["val_id"],type=data["type"],content=data["content"])
        db.session.add(record)
        db.session.commit()
