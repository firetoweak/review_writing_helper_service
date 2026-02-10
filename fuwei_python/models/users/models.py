import time
from typing import List, Dict, Union

from common.aliSms import aliSms
from conf.db import db
from sqlalchemy import  Column, Integer, String , and_, delete,DateTime,func,or_
from flask_paginate import  get_page_args,Pagination
from conf.config import app_config
import random
import hashlib
import re

from models.queue.model import Smsqueue


class User(db.Model):
    __tablename__ = 'user'
    user_id = Column(Integer, primary_key=True)
    admin_user_id = Column(Integer, default=0)
    mobile = Column(String(128), default="")
    password = Column(String(128), default="")
    email = Column(String(255), default="")
    company_name = Column(String(255), default="")
    real_name = Column(String(128), default="")
    employees_num = Column(String(11), default="")
    sense = Column(String(255), default="")
    position = Column(String(255), default="")
    dept = Column(String(255), default="")
    token = Column(String(1024), default="")
    status = Column(Integer,default=0)
    is_delete = Column(Integer, default=0)
    create_time = Column(db.DateTime, server_default=func.now(),nullable=False)
    update_time = Column(DateTime,server_default=func.now(), onupdate=func.now(),nullable=False)
    allSense = ['互联网/IT', '企业服务', '智能硬件', '先进制造', '金融', '游戏', '电商', '其他']
    allPosition = ['老板/CEO','CTO/CIO','组织负责人','项目经理','产品经理','研发经理','测试经理','其他']
    allEmployeesNum = ['1-25','26-50','51-100','101-300','300+']
    servModule = {0:"缺陷管理质量评估模块" ,1:"缺陷管理质量评估模块",2:"立项管理质量评估模块",3:"IT缺陷流"}

    # 增加用户与角色的关联关系 多对多
    roles = db.relationship('Role', secondary='user_roles', back_populates='users', overlaps="user,role,user_roles")
    user_roles = db.relationship('UserRole', back_populates='user', cascade='all, delete-orphan', overlaps="role")

    email_right = db.relationship(
        'EmailUserRight',
        primaryjoin='User.user_id == EmailUserRight.user_id',
        foreign_keys='EmailUserRight.user_id', #逻辑外键
        # backref=db.backref('user', lazy='subquery'),  # 使用子查询替代 JOIN
        lazy='dynamic',  # 使用子查询替代 JOIN
        cascade='all, delete-orphan'  # 增强级联操作
    )

    mobile_rights = db.relationship(
        'MobileUserRight',
        primaryjoin='User.user_id == MobileUserRight.user_id',  # 显式连接条件
        foreign_keys='MobileUserRight.user_id',  # 明确被引用的字段
        # backref=db.backref('user', lazy='joined'),  # 反向时多对一
        lazy='dynamic',  # 正向返回Query对象 一对多
        cascade='save-update, merge, delete'  # 配置级联操作
    )


    def has_role(self, role_name):
        return any(role.name == role_name for role in self.roles)

    # 增加用户与模版的关联关系 一对多关系（隐含user_id外键在Template模型中）
    templates = db.relationship('Template', backref='user', lazy=True)

    @staticmethod
    def add_one(data, user_id=0):
        delete(User).filter(User.user_id==user_id)
        new_record = User(mobile=data['mobile'],password=data['password'],token=data['token'])
        db.session.add(new_record)
        db.session.flush()  # 生成主键值但不提交
        db.session.refresh(new_record)  # 重新加载对象以获取最新的主键值
        db.session.commit()
        return new_record.user_id
    @staticmethod
    def get_mobile_login_user(data):
        item =  User.query.filter(and_(User.mobile == data['mobile'], User.password ==data['password'],User.status==1,User.is_delete==0)).first()
        return item
    @staticmethod
    def get_emai_login_user(data):
        item =  User.query.filter(and_(User.email == data['mobile'], User.password ==data['password'],User.is_delete==0)).first()
        return item
    @staticmethod
    def check_register_user(data):
        item =  User.query.filter(and_(User.mobile == data['mobile'].strip(),User.status!=0,User.is_delete==0)).first()
        return item
    @staticmethod
    def get_register_email(data):
        item =  User.query.filter(and_(User.email == data['email'].strip()),User.is_delete==0).first()
        return item
    @staticmethod
    def update_pass(user_id:int, password:str):
        item =  User.get_user_by_id(user_id)
        item.password = password
        db.session.commit()
    @staticmethod
    def update_status(user_id:int, status:int):
        item =  User.get_user_by_id(user_id)
        item.status = status
        db.session.commit()
    @staticmethod
    def get_email_user_by_id(user_id, field):
        item =  User.query.filter(and_(User.user_id == user_id)).join(EmailUserRight, User.user_id == EmailUserRight.user_id).filter(getattr(EmailUserRight, field) == 1).first()
        return item
    @staticmethod
    def get_user_by_id(user_id):
        item =  User.query.filter(and_(User.user_id == user_id)).first()
        return item
    @staticmethod
    def get_user_by_email(admin_user_id, email):
        item =  User.query.filter(and_(User.admin_user_id == admin_user_id,User.email==email,User.is_delete==0)).first()
        return item
    @staticmethod
    def update_company_admin_profile(user_id:int, data):
        item =  User.query.filter(and_(User.user_id == user_id)).first()
        item.company_name = data['company_name']
        item.real_name = data['real_name']
        item.position = data['position']
        item.employees_num = data['employees_num']
        item.sense = data['sense']
        item.status = 1
        item.admin_user_id = 0
        db.session.commit()
    @staticmethod
    def add_inner_user(data,no_commit=None):
        new_record = User(password=data['password'],email=data['email'],real_name=data['real_name'],position=data['position'],dept=data['dept'],admin_user_id=data['admin_user_id'])
        db.session.add(new_record)
        db.session.flush()  # 生成主键值但不提交
        db.session.refresh(new_record)  # 重新加载对象以获取最新的主键值
        if no_commit is None:
            db.session.commit()
        return new_record.user_id
    '''
    移动用户编辑邮件用户的资料、邮件用户自己编辑自己资料
    '''
    @staticmethod
    def update_inner_user_profile(data, user_id, me=0):
        item =  User.query.filter(and_(User.user_id == data['user_id'],User.admin_user_id==user_id)).first()
        if me==0:
            item.real_name = data['real_name']
            item.email = data['email']
            item.position = data['position']
            item.dept = data['dept']
            if data['password'] != "":
                item.password = data['password']
        else:
            item.position = data['position']
            item.dept = data['dept']
        db.session.commit()
    @staticmethod
    def delete_inner_user(user_id, admin_user_id):
        if user_id>0:
            User.query.filter(and_(User.user_id==user_id,User.admin_user_id==admin_user_id)).update({'is_delete': 1}, synchronize_session=False)
        else:
            User.query.filter(and_(User.admin_user_id==admin_user_id)).update({'is_delete': 1}, synchronize_session=False)
        db.session.commit()
    @staticmethod
    def get_inner_user_list(admin_user_id, field, real_name, status):
        page, per_page, offset = get_page_args(page_parameter='page', per_page_parameter='per_page')
        # per_page = 1
        # offset = (page-1)*per_page
        query = User.query.order_by(User.create_time.desc()).filter(and_(User.admin_user_id == admin_user_id, User.is_delete==0))
        if real_name!="":
            query = query.filter(User.real_name==real_name)
        if status!="":
            query = query.filter(User.status==status)
        query = query.join(EmailUserRight, User.user_id == EmailUserRight.user_id).filter(getattr(EmailUserRight, field) == 1)
        total =query.count()
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
    def batch_insert_inner_user(datas, admin_user_id):
        objects = []
        emailDatas = []
        for data in datas:
            newPass = str(random.randint(100000, 999999))
            objects.append(User(password=newPass,email=data['email'],real_name=data['real_name'],position=data['position'],dept=data['dept'],admin_user_id=admin_user_id))
            randkey = hashlib.md5((data['password'] + data['email']).encode(encoding='UTF-8')).hexdigest()
            content = f"你好，{app_config['app_name']}的账号为：{data['email']},密码：{newPass}，激活链接：{app_config['domain']}/user/verifyemail?randkey={randkey}&email={data['email']}&admin_user_id={admin_user_id}"
            emailDatas.append([content,data['email']])
        db.session.bulk_save_objects(objects)
        db.session.commit()
        return emailDatas
    @staticmethod
    def batch_check_email(emails,field):
        query = User.query.filter(and_(User.email.in_(emails),User.status!=0,User.is_delete==0)).join(EmailUserRight, User.user_id == EmailUserRight.user_id).filter(getattr(EmailUserRight, field) == 1)
        item = query.all()
        return item
    @staticmethod
    def get_user_by_token(token):
        item = User.query.filter(and_(User.token==token,User.is_delete==0)).first()
        return item
    @staticmethod
    def update_token(item, token):
        item.token = token
        db.session.commit()

    @staticmethod
    def get_mobile_user_list(mobile):
        page, per_page, offset = get_page_args(page_parameter='page', per_page_parameter='per_page')
        per_page =50
        offset = (page-1)*per_page
        query   =  User.query.order_by(User.create_time.desc()).filter(and_(User.admin_user_id ==0,User.is_delete==0))
        if mobile!="":
            pattern = r'^1\d{10}$'
            if  re.match(pattern, mobile):
                query =query.filter(and_(User.mobile ==mobile))
            else:
                query = query.filter(and_(User.real_name == mobile))
        total = query.count()
        print(total)
        query = query.offset(offset).limit(per_page)
        items = query.all()
        pagination = Pagination(
            page=page,
            per_page=per_page,
            total=total,
            css_framework='bootstrap'  # 支持 bootstrap4/bootstrap5/foundation 等
        )
        return pagination,items
    @staticmethod
    def delete_mobile_user(user_id):
        User.query.filter(and_(User.user_id == user_id)).update({'is_delete': 1},synchronize_session=False)
        db.session.commit()
    @staticmethod
    def get_all_mobile_user():
        return User.query.order_by(User.create_time.desc()).filter(and_(User.admin_user_id ==0,User.is_delete==0)).all()

    @staticmethod
    def get_inner_user_num(admin_user_id, field):
            total = (User.query.filter( and_(User.admin_user_id == admin_user_id, User.is_delete == 0))
                     .join(EmailUserRight, User.user_id == EmailUserRight.user_id)
                     .filter(getattr(EmailUserRight, field) == 1)).count()
            return total

    @staticmethod
    def get_one_mobile_user(mobile):
        return User.query.filter(and_(User.mobile ==mobile,User.status==1)).first()

    @staticmethod
    def change_mobile(data, user_id):
        delete(User).filter(User.user_id==user_id)
        User.query.filter(and_(User.user_id == data['user_id'])).update({'mobile': data['mobile']}, synchronize_session=False)
        db.session.commit()

    @staticmethod
    def add_admin_mobile_user(data, user_id):
        delete(User).filter(User.user_id==user_id)
        new_record = User(mobile=data['mobile'],password=data['password'],company_name=data['company_name'],real_name=data['real_name'],sense=data['sense'],position=data['position'],status=1,employees_num=data['employees_num'],token=data['token'])
        db.session.add(new_record)
        db.session.flush()  # 生成主键值但不提交
        db.session.refresh(new_record)  # 重新加载对象以获取最新的主键值
        db.session.commit()
        return new_record.user_id

    @staticmethod
    def get_users_by_name_or_email(name_keyword="", email_keyword=""):
        """
        根据用户姓名或邮箱地址获取用户列表
        :param name_keyword: 姓名关键词，模糊匹配
        :param email_keyword: 邮箱关键词，模糊匹配
        :return: 符合格式要求的用户列表，包含user_id字段
        """
        # 构建基础查询条件
        query = User.query.filter(User.is_delete == 0)

        # 如果有查询条件，添加过滤
        if name_keyword or email_keyword:
            conditions = []
            if name_keyword:
                conditions.append(User.real_name.like(f'%{name_keyword}%'))
            if email_keyword:
                conditions.append(User.email.like(f'%{email_keyword}%'))
            query = query.filter(or_(*conditions))

        # 执行查询
        users = query.all()

        # 格式化返回结果
        result = []
        for user in users:
            result.append({
                'user_id': user.user_id,
                'email': user.email,
                'name': user.real_name,
                'department': user.dept
            })

        return result

    @staticmethod
    def get_company_users_by_user_id(user_id: int) -> List[Dict[str, Union[int, str, None]]]:
        """
        根据 user_id 获取同公司的所有用户（包括自己）
        :param user_id: 用户ID
        :return: 公司用户列表，包含基础信息
        """
        # 首先获取当前用户
        current_user = User.query.filter(
            User.user_id == user_id,
            User.is_delete == 0
        ).first()

        if not current_user:
            return []

        # 确定管理员ID：如果当前用户是管理员(admin_user_id=0)，则使用自己的user_id作为管理员ID
        admin_id: int = current_user.admin_user_id if current_user.admin_user_id != 0 else current_user.user_id

        # 查询所有同一公司的用户
        company_users: List[User] = User.query.filter(
            or_(
                User.admin_user_id == admin_id,
                User.user_id == admin_id  # 包括管理员自己
            ),
            User.is_delete == 0
        ).all()

        # 格式化返回结果
        result: List[Dict[str, Union[int, str, None]]] = []
        for user in company_users:
            result.append({
                'user_id': user.user_id,
                'email': user.email,
                'name': user.real_name,
                'department': user.dept,
                'position': user.position,
                'mobile': user.mobile
            })

        return result

    @staticmethod
    def get_like_defect_user_list(admin_user_id):
        '''
        获取缺陷流用户列表数据
        :param data:
        :return:
        query = User.query.filter(and_(
            or_(User.real_name.like(f"%{data['real_name']}%"), User.email.like(f"%{data['email']}%")),
            User.admin_user_id==data['admin_user_id'],
            User.is_delete==0,
            User.status==1)).join(User.email_right).filter(getattr(EmailUserRight, record_type) == 1)
        '''
        query = User.query.filter(and_(
            User.admin_user_id==admin_user_id,
            User.is_delete==0,
            User.status==1))
        return query.all()


class EmailUserRight(db.Model):
    __tablename__ = 'email_user_right'
    user_id = Column(Integer, primary_key=True)
    type_0 = Column(Integer,default=0)
    type_1 = Column(Integer,default=0)
    type_2 = Column(Integer,default=0)
    admin_user_id = Column(Integer,default=0)
    create_time = Column(db.DateTime, server_default=func.now(),nullable=False)
    update_time = Column(DateTime,server_default=func.now(), onupdate=func.now(),nullable=False)
    # user = db.relationship('User', primaryjoin='EmailUserRight.user_id == foreign(User.user_id)',
    #                        uselist=False,  # 一对一关系
    #                        lazy='dynamic',  # 预加载关联对象
    #                        backref=db.backref('email_user_right', lazy='dynamic'))

    @staticmethod
    def add_one(data={}, key='',no_commit=None):
        data[key] = 1
        db.session.add(EmailUserRight(user_id=data['user_id'], type_0=data['type_0'], type_1=data['type_1'], type_2=data['type_2'], admin_user_id=data['admin_user_id']))
        if no_commit is None:
            db.session.commit()
    @staticmethod
    def update_right(key_name:str, item):
        setattr(item, key_name, 1)
        db.session.commit()
    @staticmethod
    def get_one(user_id):
        item = EmailUserRight.query.filter(and_(EmailUserRight.user_id == user_id)).first()
        return item
    @staticmethod
    def get_email_user_num(admin_user_id, field):
        count = EmailUserRight.query.filter(and_(EmailUserRight.admin_user_id == admin_user_id, getattr(EmailUserRight, field) == 1)).count()
        return count
    @staticmethod
    def del_one_email_user(admin_user_id, user_id, key_name):
        item =EmailUserRight.query.filter(and_(EmailUserRight.admin_user_id == admin_user_id, EmailUserRight.user_id == user_id)).first()
        setattr(item, key_name, 0)
        db.session.commit()
        if item.type_0==0 and item.type_1==0:
            return True
        else:
            return False
    @staticmethod
    def batch_del_email_user(admin_user_id, key_name):
        EmailUserRight.query.filter(and_(EmailUserRight.admin_user_id == admin_user_id)).update({key_name:0})


class MobileUserRight(db.Model):
    __tablename__ = 'mobile_user_right'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, default=0)
    user_total_num= Column(Integer, default=0)
    invited_user_num= Column(Integer, default=0)
    remind_invited_num= Column(Integer, default=-1)
    request_num= Column(Integer, default=10)
    requested_num= Column(Integer, default=0)
    remind_request_num= Column(Integer, default=-1)
    to_date = Column(db.DateTime,nullable=True,default=None)
    remind_date = Column(db.DateTime,nullable=True,default=None)
    sended_remind_date_message = Column(Integer, default=0)
    sended_remind_invite_message  = Column(Integer, default=0)
    sended_remind_request_message = Column(Integer, default=0)
    type =  Column(Integer, default=0)
    state =  Column(Integer, default=0)

    remind_invited_open = Column(Integer, default=0)
    remind_request_open = Column(Integer, default=0)
    remind_date_open = Column(Integer, default=0)

    admin_last_update = Column(db.DateTime, server_default=func.now(),nullable=False)
    create_time = Column(db.DateTime, server_default=func.now(),nullable=False)
    update_time = Column(DateTime,server_default=func.now(), onupdate=func.now(),nullable=False)

    @staticmethod
    def add_one(data):
        if data['type'] == 1 or data['type'] ==0:
            db.session.add(MobileUserRight(user_id=data['user_id'], type=data['type']))
        else:
            db.session.add(MobileUserRight(user_id=data['user_id'], type=data['type'], request_num=0))
        db.session.commit()
    @staticmethod
    def get_rights(user_id):
        record = MobileUserRight.query.filter(and_(MobileUserRight.user_id == user_id)).all()
        return record
    @staticmethod
    def set_rights(data):
        record = MobileUserRight.query.filter(and_(MobileUserRight.id == data['id'])).first()
        record.user_total_num = data['user_total_num']
        record.request_num = data['request_num']
        record.to_date = data['to_date'] if data['to_date']!="" else None
        record.state = data['state']
        record.invited_user_num = 0
        record.requested_num = 0
        record.admin_last_update = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        record.remind_invited_num = data['remind_invited_num'] if data['remind_invited_num']!="" else 0
        record.remind_request_num = data['remind_request_num'] if data['remind_request_num']!="" else 0
        record.remind_date = data['remind_date'] if data['remind_date']!="" else None

        record.remind_invited_open = 0 if data['remind_invited_num']=="" else 1
        record.remind_request_open = 0 if data['remind_request_num']=="" else 1
        record.remind_date_open = 0 if data['remind_date']=="" else 1

        record.sended_remind_date_message = 0
        record.sended_remind_invite_message = 0
        record.sended_remind_request_message = 0
        db.session.commit()
    @staticmethod
    def get_one_right(user_id, record_type:int):
        record = MobileUserRight.query.filter(and_(MobileUserRight.user_id == user_id, MobileUserRight.type == record_type)).first()
        return record
    @staticmethod
    def set_remind_by_user_id(data):
        print(data)
        item = MobileUserRight.get_one_right(data['admin_user_id'], data['type'])
        if data['keyName_num'] == 'remind_date' and data['remind_num']=="0":
            data['remind_num'] = None
        setattr(item,data['keyName_num'],data['remind_num'])
        setattr(item,data['keyName_open'],data['open'])
        db.session.commit()
    @staticmethod
    def set_right(item, key, val):
        setattr(item,key,val)
        db.session.commit()

    @staticmethod
    def check_request_right(mobileUserRightRecord, type="request",invite_num =None):
        if type =="request":
            if mobileUserRightRecord.request_num - mobileUserRightRecord.requested_num <=0:
                return {'msg': '你剩余的提问次数已为0', "code": -2, 'items': [], "record_id": 0}, -1
        if type =="invite":
            if mobileUserRightRecord.user_total_num-mobileUserRightRecord.invited_user_num<=0:
                return {'msg': '你邀请的同事的数量已达上限', "code": -1}, -1
        if mobileUserRightRecord.state!=0:
            if mobileUserRightRecord.to_date!=None:
                timestamp = time.mktime(time.strptime(str(mobileUserRightRecord.to_date), "%Y-%m-%d %H:%M:%S"))
                if time.time()>timestamp:
                    return {'msg': '你的账号有效期已到', "code": -1, 'items': [], "record_id": 0}, -1
        if invite_num is not None:
            rest_num = mobileUserRightRecord.user_total_num - mobileUserRightRecord.invited_user_num
            if  rest_num - invite_num  <0:
                return {'msg': f'当前你要邀请的同事的数量为：{invite_num}，你剩余的邀请数量为：{rest_num},剩余邀请机会不足', "code": -1}, -1
        return {},1

    @staticmethod
    def get_user_type_right(user_type, user_id, admin_user_id, record_type):
        record = MobileUserRight.get_one_right(admin_user_id, record_type)
        if user_type=='mobile':
            if record.state==1:
                return 1
            else:
                return 0
        if user_type=='email':
            if record.state==1:
                item = EmailUserRight.get_one(user_id)
                rs = getattr(item,'type_' + str(record_type))
                if rs==1:
                    return 1
                else:
                    return 0
            else:
                return 0
        return None

    @staticmethod
    def ai_val_sms(mobile_user_right_record, admin_user_id, type):
        if mobile_user_right_record.remind_request_num >= (mobile_user_right_record.request_num - mobile_user_right_record.requested_num) and mobile_user_right_record.sended_remind_request_message == 0:
            record = User.get_user_by_id(admin_user_id)
            e1 = 0
            e2 = 0
            rs1 = aliSms.sendRemind(record.mobile, record.real_name, template=str(type), remind_type="余额不足")
            try:
                if rs1.body.code == 'OK':
                    print(rs1.body)
                    MobileUserRight.set_right(mobile_user_right_record, 'sended_remind_request_message', 1)
            except:
                print("短信发送失败1")
                e1 =1
            rs2 = aliSms.sendAdminRemind(name=record.real_name, serve_type=str(type), remind_type="余额不足")
            try:
                if rs2.body.code == 'OK':
                    print(rs2.body)
            except:
                print("短信发送失败2")
                e2 = 1
            if e1==1 or e2==1:
                data = {}
                data['admin_user_id'] = admin_user_id
                data['type'] = int(type)
                data['module'] = "aiVal"
                data['e1'] = e1
                data['e2'] = e2
                Smsqueue.add_one(data)

    @staticmethod
    def inner_user_sms(mobile_user_right_record, admin_user_id, type):
        if mobile_user_right_record.remind_invited_num >= (mobile_user_right_record.user_total_num - mobile_user_right_record.invited_user_num) and mobile_user_right_record.sended_remind_invite_message == 0:
            record = User.get_user_by_id(admin_user_id)
            rs1 = aliSms.sendRemind(record.mobile, record.real_name, template=str(type), remind_type="余额不足")
            e1 = 0
            e2 = 0
            try:
                if rs1.body.code == 'OK':
                    print(rs1.body)
                    MobileUserRight.set_right(mobile_user_right_record, 'sended_remind_invite_message', 1)
            except:
                print("短信发送失败3")
                e1 =1
            rs2 = aliSms.sendAdminRemind(name= record.real_name,serve_type=str(type),remind_type="余额不足")
            try:
                if rs2.body.code == 'OK':
                    print(rs2.body)
            except:
                print("短信发送失败4")
                e2 = 1
            if e1==1 or e2==1:
                data = {'admin_user_id': admin_user_id, 'type': int(type), 'module': "innerUser", 'e1': e1, 'e2': e2}
                Smsqueue.add_one(data)

    @staticmethod
    def get_right_style(admin_user_id, record_type):
        rights = MobileUserRight.get_one_right(admin_user_id, record_type)
        date_end = 0
        request_font_red = 0
        invite_font_red = 0
        if rights is None:
            return date_end, request_font_red, invite_font_red, rights
        if rights.to_date != None:
            date_to_check = time.mktime(time.strptime(str(rights.to_date), "%Y-%m-%d %H:%M:%S"))
            current_time_timestamp = time.time()
            if date_to_check > current_time_timestamp:
                date_end = 0
            else:
                date_end = 1
        if rights.request_num <= rights.requested_num:
            request_font_red = 1
        if rights.user_total_num <= rights.invited_user_num:
            invite_font_red = 1
        return date_end,request_font_red,invite_font_red,rights
