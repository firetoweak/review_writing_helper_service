from conf.db import db
from sqlalchemy import  Column, Integer, String ,Float,and_,DateTime,func
class UploadFiles(db.Model):
    __tablename__ = 'upload_files'
    id = Column(Integer, primary_key=True)
    file_name = Column(String(255), default="")
    file_key_url = Column(String(255), default="")
    ai_sug_score_id = Column(String(128), default="")
    user_id = Column(Integer, default=0)
    create_time = Column(db.DateTime, server_default=func.now(),nullable=False)
    update_time = Column(DateTime,server_default=func.now(), onupdate=func.now(),nullable=False)

    @staticmethod
    def bulkInsert(urls,ai_sug_score_id,user_id):
        arr = []
        for url in urls:
            arr.append({"file_name":"","file_key_url":url,"ai_sug_score_id":ai_sug_score_id,"user_id":user_id})
        UploadFiles.query.filter(and_(UploadFiles.ai_sug_score_id == ai_sug_score_id)).delete()
        db.session.bulk_insert_mappings(UploadFiles, arr)
        db.session.commit()

    @staticmethod
    def getUserAllPic(ai_sug_score_ids):
        items = UploadFiles.query.filter(and_(UploadFiles.ai_sug_score_id.in_(ai_sug_score_ids))).all()
        pics = []
        for item in items:
            pics.append(item.file_key_url)
        return pics
