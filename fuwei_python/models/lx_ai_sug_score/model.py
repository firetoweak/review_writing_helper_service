from sqlalchemy.dialects.mysql import LONGTEXT, DECIMAL

from conf.db import db
from sqlalchemy import Column, Integer, String, Text, and_, DateTime, func, or_, ForeignKey
from flask_paginate import  get_page_args,Pagination
from models.users.models import User
import re


class LxAiSugScore(db.Model):
    __tablename__ = 'lx_ai_sug_score'
    id = Column(Integer, primary_key=True)
    file_key  = Column(String(255),default="")
    file_name = Column(String(255),default="")
    title = Column(String(255),default="")
    select_1 = Column(Integer,default=0)
    select_2 =  Column(Integer,default=0)
    step_1 =  Column(Text,default="")
    step_1_score = Column(Integer,default=None)
    step_1_ai =  Column(Text,default="")
    step_2 =  Column(Text,default="")
    step_2_score = Column(Integer,default=None)
    step_2_ai =  Column(Text,default="")
    step_3 =  Column(Text,default="")
    step_3_score = Column(Integer,default=None)
    step_3_ai =  Column(Text,default="")
    step_4 =  Column(Text,default="")
    step_4_score = Column(Integer,default=None)
    step_4_ai =  Column(Text,default="")
    step_5 =  Column(Text,default="")
    step_5_score = Column(Integer,default=None)
    step_5_ai =  Column(Text,default="")
    total_score = Column(DECIMAL(4,1),default=None)
    case = Column(Integer,default=0)
    all_markdwon_text = Column(LONGTEXT,default="")
    summarize_text =  Column(Text,default="")
    xmind_json =  Column(Text,default="")
    user_id = Column(Integer,default=0)
    type = Column(Integer,default=0)
    admin_user_id = Column(Integer,default=0)
    state = Column(Integer,default=0)
    is_delete  = Column(Integer,default=0)
    is_admin_delete = Column(Integer,default=0)
    error_mess = Column(Text,default="")
    summarize_val_sug = Column(Text,default=None)
    create_time = Column(db.DateTime, server_default=func.now(),nullable=False)
    update_time = Column(DateTime,server_default=func.now(), onupdate=func.now(),nullable=False)
    anti_shake_logs = db.relationship('LxAntiShakeLog', backref='LxAiSugScore', lazy="joined")

    drives = {'1':'市场机会分析','2':'产品价值设定','3':'产品包定义','4':'产品执行策略','5':'投资收益分析'}
    CASE_TEXT = [
                "做好市场机会分析与产品价值定位是后续所有活动的基础，不能绕过",
                "选定典型目标客户，以有效支撑成交为目标，做好产品包定义是下一步活动的关键",
                "在产品包定义的基础上，做好产品的执行策略与投入产出分析是下一步的工作重点",
                "当前产品立项3个阶段的工作质量整体均基本达标，可以按照目前的主要观点与各领域的IPMT委员及专家进行充分沟通后，明确共识与关键分歧，并在此基础上对本次产品立项发起IPMT评审和决策。"
            ]
    select_1_text = ['重大项目机会驱动型立项','市场机会/威胁分析驱动型立项','市场机会/威胁分析+重大项目机会双驱动型立项','战略制高点/瓶颈点争夺型立项']
    select_2_text = ['首次','迭代升级']
    PART_TXT = {
                1:['【对市场分析工作的评估意见】','【对市场分析工作的改进建议】'],
                2:['【对产品价值设定的评估意见】','【对产品价值设定的改进建议】'],
                3:['【对产品包定义的评估意见】','【对产品包定义的改进建议】'],
                4:['【产品执行策略工作的评估意见】','【产品执行策略工作的改进建议】'],
                5: ['【投资收益分析工作的评估意见】', '【投资收益分析工作的改进建议】'],
                }
    def to_dict(self):
        return {
            column.name: getattr(self, column.name)for column in self.__table__.columns
        }
    @staticmethod
    def addUploadRec(data,user_id,admin_user_id,id=0):
        LxAiSugScore.query.filter(and_(LxAiSugScore.id == id, LxAiSugScore.user_id == user_id, LxAiSugScore.state == 0)).delete()
        record =  LxAiSugScore(file_name=data['file_name'], state=0, user_id=user_id, admin_user_id=admin_user_id)
        db.session.add(record)
        db.session.flush()  # 生成主键值但不提交
        db.session.refresh(record)  # 重新加载对象以获取最新的主键值
        db.session.commit()
        return record.id

    @staticmethod
    def addApiUploadRec(data,filename,user_id,admin_user_id):
        record =  LxAiSugScore(file_name=filename, title=data['title'], select_1=data['drive_source'], select_2=data['lx_time'], state=-2, user_id=user_id, admin_user_id=admin_user_id)
        db.session.add(record)
        db.session.flush()  # 生成主键值但不提交
        db.session.refresh(record)  # 重新加载对象以获取最新的主键值
        db.session.commit()
        return record.id

    @staticmethod
    def editUploadRec(data,id,user_id):
        item = LxAiSugScore.getOneById(id, user_id)
        item.file_name = data['file_name']
        db.session.commit()

    @staticmethod
    def saveMarkdown(id,markdown,key):
        LxAiSugScore.query.filter(and_(LxAiSugScore.id == id, LxAiSugScore.state == 0)).update({'all_markdwon_text': markdown, 'file_key':key}, synchronize_session=False)
        db.session.commit()

    @staticmethod
    def saveApiMarkdown(id,markdown,key):
        LxAiSugScore.query.filter(and_(LxAiSugScore.id == id, LxAiSugScore.state == -2)).update({'all_markdwon_text': markdown, 'file_key':key}, synchronize_session=False)
        db.session.commit()

    @staticmethod
    def saveUploadFinish(data,user_id):
        LxAiSugScore.query.filter(and_(LxAiSugScore.id == data['id'], LxAiSugScore.state == 0, LxAiSugScore.user_id == user_id)).update({'title': data['title'], 'select_1':data['select_1'], 'select_2':data['select_2'], 'state':-2}, synchronize_session=False)
        db.session.commit()

    @staticmethod
    def getList(user_id=1,type=0,state=1,search=""):
        page, per_page, offset = get_page_args(page_parameter='page', per_page_parameter='per_page')
        query   =  LxAiSugScore.query.order_by(LxAiSugScore.create_time.desc()).filter(and_(LxAiSugScore.user_id == user_id, LxAiSugScore.is_delete == 0))
        if state !="":
            query = query.filter(and_(LxAiSugScore.state == state))
        if search!="":
            query = query.filter(and_(LxAiSugScore.title == search))
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
    def getOneById(id,user_id,state=0):
        db.session.expunge_all()
        db.session.expire_all()
        item = LxAiSugScore.query.filter(and_(LxAiSugScore.id == id, LxAiSugScore.state == state, LxAiSugScore.is_delete == 0, LxAiSugScore.user_id == user_id)).first()
        return item

    @staticmethod
    def getOneBySpecialId(id):
        db.session.expunge_all()
        db.session.expire_all()
        item = LxAiSugScore.query.filter(LxAiSugScore.id == id).first()
        return item

    @staticmethod
    def adminGetOneById(id,state=0):
        db.session.expunge_all()
        db.session.expire_all()
        item = LxAiSugScore.query.filter(and_(LxAiSugScore.id == id, LxAiSugScore.state == state, LxAiSugScore.is_delete == 0)).first()
        if item:
            db.session.refresh(item)
        return item

    @staticmethod
    def getApiOneById(id,user_id):
        item = LxAiSugScore.query.filter(and_(LxAiSugScore.id == id, LxAiSugScore.is_delete == 0, LxAiSugScore.user_id == user_id)).first()
        return item
    @staticmethod
    def set_step(id, user_id, data, state, step_scores_length):
        if step_scores_length<=1:
            item = LxAiSugScore.getOneById(id, user_id, state=state)
            for key,val in data.items():
                if key =='error_mess' and val!="":
                    setattr(item, key, item.error_mess+'\n'+str(val))
                else:
                    setattr(item,key,val)
            db.session.commit()

    @staticmethod
    def set_summarize(record_id, user_id, data, state):
        item = LxAiSugScore.getOneById(record_id, user_id, state)
        item.summarize_text = data['summarize_text']
        if data['error_mess']!="":
            item.error_mess = item.error_mess+"\n"+data['error_mess']
        db.session.commit()

    @staticmethod
    def setXmind(id,user_id,data,state):
        item = LxAiSugScore.getOneById(id, user_id, state)
        item.xmind_json = data['xmind_json']
        if data['error_mess']!="":
            item.error_mess = item.error_mess+"\n"+data['error_mess']
        db.session.commit()

    @staticmethod
    def set_fail(record_id, user_id, state):
        item = LxAiSugScore.getOneById(record_id, user_id, state)
        item.state = -3
        db.session.commit()

    @staticmethod
    def set_sucess(record_id, user_id, state, total_score, old_state):
        item = LxAiSugScore.getOneById(record_id, user_id, old_state)
        item.state = state
        item.total_score = total_score
        db.session.commit()

    @staticmethod
    def repeat_set_state(id, user_id):
        item = LxAiSugScore.getOneById(id, user_id, -3)
        item.state = -2
        db.session.commit()

    @staticmethod
    def delOne(id,user_id):
        LxAiSugScore.query.filter(and_(LxAiSugScore.id == id, LxAiSugScore.user_id == user_id, LxAiSugScore.state != -2)).update({'is_delete': 1})
        db.session.commit()

    @staticmethod
    def delEmpty(id,user_id):
        LxAiSugScore.query.filter(and_(LxAiSugScore.id == id, LxAiSugScore.user_id == user_id)).delete()
        db.session.commit()

    @staticmethod
    def getUserAiSugScore(user_name):
        page, per_page, offset = get_page_args(page_parameter='page', per_page_parameter='per_page')
        query = db.session.query(LxAiSugScore).join(User, User.user_id == LxAiSugScore.user_id)
        query = query.filter(LxAiSugScore.state == 1)
        query = query.filter(LxAiSugScore.is_admin_delete == 0)
        if user_name!="":
            pattern = r'^1\d{10}$'
            if  re.match(pattern, user_name):
                u =  User.get_one_mobile_user(user_name)
                if u==None:
                    admin_user_id = -1
                else:
                    admin_user_id = u.user_id
                query = query.filter(or_(User.admin_user_id == admin_user_id,User.user_id==admin_user_id))
            else:
                query = query.filter(User.email == user_name)
        total = query.count()
        query = query.add_entity(User)
        results = query.order_by(LxAiSugScore.create_time.desc()).offset(offset).limit(per_page).all()
        pagination = Pagination(
            page=page,
            per_page=per_page,
            total=total,
            css_framework='bootstrap'  # 支持 bootstrap4/bootstrap5/foundation 等
        )
        return pagination,results

    @staticmethod
    def adminDeleteAiSugScore(id):
        LxAiSugScore.query.filter(and_(LxAiSugScore.id == id)).update({'is_admin_delete': 1}, synchronize_session=False)
        db.session.commit()
    @staticmethod
    def set_score(item, i, score):
        setattr(item,f'step_{i}_score',score)
        db.session.commit()
    @staticmethod
    def set_summarize_val_sug(record_id, user_id, state, data):
        item = LxAiSugScore.getOneById(record_id, user_id, state)
        item.summarize_val_sug = data['summarize_val_sug']
        if data['error_mess'] != "":
            item.error_mess = item.error_mess + "\n" + data['error_mess']
        db.session.commit()
    @staticmethod
    def set_case(item, tag):
        item.case = tag
        db.session.commit()
        return item
class LxAntiShakeLog(db.Model):
    __tablename__ = 'lx_anti_shake_log'
    id = Column(Integer, primary_key=True)
    lx_id = Column(Integer,ForeignKey('lx_ai_sug_score.id', ondelete='CASCADE'),nullable=True,comment="")
    content = Column(Text, default="")
    create_time = Column(db.DateTime, server_default=func.now(),nullable=False)
    update_time = Column(DateTime,server_default=func.now(), onupdate=func.now(),nullable=False)


    @staticmethod
    def add_one(data):
        record = LxAntiShakeLog(lx_id=data["lx_id"],content=data["content"])
        db.session.add(record)
        db.session.commit()