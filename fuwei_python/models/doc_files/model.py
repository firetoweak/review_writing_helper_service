from sqlalchemy.dialects.mysql import LONGTEXT

from conf.db import db
from sqlalchemy import  Column, Integer, String ,Float,and_,DateTime,delete, Text
from datetime import datetime
from flask_paginate import  get_page_args,Pagination

class DocFiles(db.Model):

    __tablename__ = 'doc_files'
    id = Column(Integer, primary_key=True)
    type = Column(Integer, default=0)
    markdown = Column(LONGTEXT, default="")
    html = Column(LONGTEXT, default="")
    html_content = Column(LONGTEXT, default="")
    markdown_content = Column(LONGTEXT, default="")
    file_key = Column(String(128), default="")
    file_name = Column(String(256), default="")
    cammand = Column(Text, default="")
    title_show = Column(String(255), default="")
    big_title_show = Column(String(255), default="")
    child_type_1 = Column(Integer, default=0)
    child_type_2 = Column(Integer, default=0)
    step = Column(Integer, default=0)
    create_time = Column(db.DateTime, default=datetime.now())
    update_time = Column(DateTime, default=datetime.now(), onupdate=datetime.now())
    standarFile= {"0":{"name":"","content":""},"1":{"name":"","content":""},"2":{"name":"","content":""}}
    @staticmethod
    def addOne(data):
        db.session.add(DocFiles(file_name=data['file_name'], type=data['type'], markdown=data['markdown'], cammand=data['cammand'], step=data['step']))
        db.session.commit()

    @staticmethod
    def getList(type=0,child_type_1=0,child_type_2=0,file_name=""):
        page, per_page, offset = get_page_args(page_parameter='page', per_page_parameter='per_page')
        per_page = 10
        offset = (page-1)*per_page
        query = DocFiles.query
        if type>=0:
            if type == 0 or type ==1:
                typeArr = [type,(type+100)]
                query  = query.filter(DocFiles.type.in_(typeArr))
            else:
                query  = query.filter(DocFiles.type == type)
        if child_type_1>=0 and child_type_1<100:
            query  = query.filter(DocFiles.child_type_1 == child_type_1)
        if child_type_2>=0 and  child_type_1<100:
            query  = query.filter(DocFiles.child_type_2 == child_type_2)
        if file_name!="":
            query  = DocFiles.query.filter(DocFiles.file_name == file_name)
        items = query.offset(offset).limit(per_page).all()
        total = query.count()
        pagination = Pagination(
            page=page,
            per_page=per_page,
            total=total,
            css_framework='bootstrap'  # 支持 bootstrap4/bootstrap5/foundation 等
        )
        return pagination,items

    @staticmethod
    def delOne(id):
        item = DocFiles.query.filter(and_(DocFiles.id == id)).first()
        txDocId = item.tx_doc_id
        DocFiles.query.filter(and_(DocFiles.id == id)).delete()
        db.session.commit()
        return txDocId

    @staticmethod
    def editOneUpload(id,html,markdown,key,upload_type):
        item =  DocFiles.getOneById(id)
        if upload_type == "val":
            item.markdown = markdown
            item.html = html
            item.file_key = key
        else:
            item.markdown_content = markdown
            item.html_content = html
            item.file_key = key
        db.session.commit()

    @staticmethod
    def editOne01(data):
        item =  DocFiles.getOneById(data['id'])
        item.markdown = data['markdown']
        item.cammand = data['cammand']
        db.session.commit()

    @staticmethod
    def editOne2(data):
        item = DocFiles.getOneById(data['id'])
        item.html = data['html']
        item.markdown = data['markdown']
        item.cammand = data['cammand']
        item.markdown_content = data['markdown_content']
        item.html_content = data['html_content']
        item.title_show = data['title_show']
        item.big_title_show = data['big_title_show']
        item.file_name = data['file_name']
        db.session.commit()

    @staticmethod
    def editOneCammand(data):
        item =  DocFiles.getOneById(data['id'])
        item.cammand = data['cammand']
        db.session.commit()



    @staticmethod
    def getOne(type,child_type_1=0,child_type_2=0,step=0):
        item =  DocFiles.query.filter(and_(DocFiles.type == type, DocFiles.child_type_1 == child_type_1, DocFiles.child_type_2 == child_type_2, DocFiles.step == step)).first()
        print(item)
        return item

    @staticmethod
    def getOneById(id):
        item =  DocFiles.query.filter(and_(DocFiles.id == id)).first()
        return item

    @staticmethod
    def getAll():
        items =  DocFiles.query.all()
        return items
    @staticmethod
    def getStandarFile(type:str,child_type_1=0,child_type_2=0,step=0):
        '''
        获取缺陷管理/产品管理的标准文档
        '''
        item = DocFiles.getOne(type, child_type_1, child_type_2, step)
        return item

    @staticmethod
    def getChildType1Data(child_type_1=100):
        items = DocFiles.query.filter(and_(DocFiles.child_type_1 == child_type_1)).all()
        return items

    @staticmethod
    def getReportTitles(child_type_1,child_type_2):
        items = DocFiles.query.filter(and_(DocFiles.child_type_1 == child_type_1, DocFiles.child_type_2 == child_type_2, DocFiles.type == 2)).order_by(DocFiles.step.asc()).all()
        titles = []
        for item in items:
            title = [item.big_title_show,item.title_show]
            titles.append(title)
        return titles

    @staticmethod
    def getReportCase(child_type_2):
        try:
            item = DocFiles.query.filter(and_(DocFiles.child_type_1 == 101, DocFiles.child_type_2 == child_type_2, DocFiles.type == 2)).first()
            return item.cammand
        except:
            return ''

    @staticmethod
    def getReportCaseArr():
        try:
            items = DocFiles.query.filter(and_(DocFiles.child_type_1 == 101, DocFiles.type == 2)).order_by(DocFiles.child_type_2.asc()).all()
            dic = {}
            i = 1
            for item in items:
                dic[i] = item.cammand
                i = i+1
            return dic
        except:
            return {}

    @staticmethod
    def getSumarizeDesCase(child_type_2):
        print(child_type_2)
        try:
            item = DocFiles.query.filter(and_(DocFiles.child_type_1 == 102, DocFiles.child_type_2 == child_type_2, DocFiles.type == 2)).first()
            print(item)
            return item.cammand
        except:
            return ''

    @staticmethod
    def getTwiceScoreCammand(step):
        print(f"step:{step}")
        try:
            item = DocFiles.query.filter(and_(DocFiles.child_type_1 == 103, DocFiles.step == step, DocFiles.type == 2)).first()
            #item = docFiles.query.filter(and_(docFiles.child_type_1 == 103)).first()
            return item.cammand
        except:
            return ''


