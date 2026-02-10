from sqlalchemy.orm import relationship

from conf.db import db
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from datetime import datetime


class UserImage(db.Model):
    __tablename__ = 'user_images'  # 表名也可以相应更新

    # 自增主键
    id = db.Column(Integer, primary_key=True, autoincrement=True)

    # 外键关联到 user 表的 user_id 字段
    user_id = db.Column(Integer, ForeignKey('user.user_id'), nullable=False, index=True)

    url = db.Column(Text, nullable=False)

    ai_evaluate = db.Column(Text)  # AI 评估结果

    created_time = db.Column(DateTime, nullable=False, default=datetime.now())

    evaluate_time = db.Column(DateTime)  # 评估完成时间

    # 定义与 User 模型的关系
    user = relationship("User", backref="images")

    def __init__(self, user_id, url, ai_evaluate=None, evaluate_time=None):
        self.user_id = user_id
        self.url = url
        self.ai_evaluate = ai_evaluate
        self.evaluate_time = evaluate_time

    def to_dict(self):
        """将模型转换为字典，便于 JSON 序列化"""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'url': self.url,
            'ai_evaluate': self.ai_evaluate,
            'created_time': self.created_time.isoformat() if self.created_time else None,
            'evaluate_time': self.evaluate_time.isoformat() if self.evaluate_time else None
        }

    def __repr__(self):
        return f'<UserImage {self.id}>'
