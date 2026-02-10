import re
from datetime import datetime

from flask_paginate import get_page_args, Pagination
from sqlalchemy import Column, Integer, String, and_

from conf.db import db


class AdminUser(db.Model):
    __tablename__ = 'admin_user'
    user_id = Column(Integer, primary_key=True)
    user_name = Column(String(64), default="")
    password = Column(String(64), default="")
    mobile = Column(String(255), default="")
    real_name = Column(String(255), default="")
    rights = Column(String(512), default="")
    is_delete = Column(Integer, default=0)
    create_time = Column(db.DateTime, default=datetime.now())
    update_time = Column(db.DateTime, default=datetime.now())
    @staticmethod
    def addOne(data):
        db.session.add(AdminUser(user_name=data['user_name'], password=data['password'], mobile=data['mobile'], real_name=data['real_name'], rights=data['rights']))
        db.session.commit()
    @staticmethod
    def getLoginUser(data):
        item =  AdminUser.query.filter(and_(AdminUser.user_name == data['user_name'], AdminUser.password == data['password'])).first()
        return item
    @staticmethod
    def checkUser(data,user_id=0):
        item =  AdminUser.query.filter(and_(AdminUser.user_name == data['user_name'].strip())).first()
        if item ==None:
            return True
        else:
            if user_id!=0:
                print(item.user_id)
                if user_id==str(item.user_id):
                    return True
            return False
    @staticmethod
    def updateProfile(password:str,mobile):
        item =  AdminUser.query.filter(and_(AdminUser.user_name == "admin")).first()
        if password!="":
            item.password = password
        item.mobile = mobile
        db.session.commit()

    @staticmethod
    def getOne(admin_user_id):
        item =  AdminUser.query.filter(and_(AdminUser.user_id == admin_user_id)).first()
        return item

    @staticmethod
    def getUserList(search):
        page, per_page, offset = get_page_args(page_parameter='page', per_page_parameter='per_page')
        query = AdminUser.query.order_by(AdminUser.create_time.desc()).filter(and_(AdminUser.is_delete == 0))
        if search!="":
            pattern = r'^1\d{10}$'
            if  re.match(pattern, search):
                query =query.filter(and_(AdminUser.mobile == search))
            else:
                search = f'%{search}%'
                query = query.filter(AdminUser.user_name.like(search))
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
    def editAdminUser(data):
        item = AdminUser.query.filter(and_(AdminUser.user_id == data['user_id'])).first()
        item.user_name = data['user_name']
        item.mobile = data['mobile']
        item.rights = data['rights']
        if data['password']!="":
            item.password = data['password']
        db.session.commit()


class AdminRights(db.Model):
    __tablename__ = 'admin_rights'
    id = Column(Integer, primary_key=True)
    name = Column(String(255), default="")
    url = Column(String(255), default="")
    act = Column(String(255), default="")
    icon = Column(String(255), default="")
    menu =  Column(Integer, default=0)
    sort = Column(Integer, default=0)
    pid = Column(Integer, default=0)
    create_time = Column(db.DateTime, default=datetime.now())
    update_time = Column(db.DateTime, default=datetime.now())
    menuDatas = []
    @staticmethod
    def getMenu():
        # if len(adminRights.menuDatas)==0:
        menuPc = []
        allMenusData = AdminRights.query.filter(and_(AdminRights.icon != "")).order_by(AdminRights.sort.asc()).all()
        for data in allMenusData:
            node = {}
            node['id'] = str(data.id)
            node['name'] = data.name
            node['url'] = data.url+'?menu_id='+str(data.id)
            node['icon'] = data.icon
            node['child'] = []
            if data.pid==0:
                for child in allMenusData:
                    if child.pid == data.id:
                        nodeChild = {}
                        nodeChild['id'] = str(child.id)
                        nodeChild['name'] = child.name
                        nodeChild['url'] = child.url+'?menu_pid='+str(node['id'])+'&&menu_id='+str(child.id)
                        if child.act!="" and child.act!=None:
                            nodeChild['url'] = nodeChild['url']+'&' + child.act
                        nodeChild['icon'] = child.icon
                        node['child'].append(nodeChild)
            else:
                continue
            menuPc.append(node)
        AdminRights.menuDatas = menuPc
        return AdminRights.menuDatas
    @staticmethod
    def getAllRight():
        rights = AdminRights.query.all()
        return rights

    @staticmethod
    def getUserMenu(userRights,admin_user_id):
        AllMenuData = AdminRights.getMenu()
        if admin_user_id==1:
            return AllMenuData
        showMenu = []
        for data in AllMenuData:
            if len(data['child'])>0:
                childs = []
                for child in data['child']:
                    if child['id'] in userRights:
                        childs.append(child)
                if len(childs)>0:
                    data['child'] = childs
                    showMenu.append(data)
            else:
                if data['id'] in userRights:
                    showMenu.append(data)
        return  showMenu
