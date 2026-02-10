# models/defect_message/model.py
from flask import current_app

from conf.db import db
from datetime import datetime
import json


class DefectMessage(db.Model):
    """
    缺陷消息模型
    """
    __tablename__ = 'defect_messages'

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True, comment='消息ID')
    send_to_user_id = db.Column(db.BigInteger, nullable=False, comment='接收用户ID')
    send_from_user_id = db.Column(db.BigInteger, nullable=True, comment='发送用户ID')
    send_time = db.Column(db.DateTime, nullable=False, default=datetime.now, comment='发送时间')
    defect_id = db.Column(db.BigInteger, db.ForeignKey('defects.id'), nullable=False, comment='缺陷单ID')  # 确保有外键约束
    message_type = db.Column(db.String(50), nullable=False, comment='消息类型')
    content = db.Column(db.Text, nullable=False, comment='消息内容模板')
    extra_params = db.Column(db.JSON, nullable=True, comment='额外参数（驳回原因、跟催原因等）')
    is_closed = db.Column(db.Boolean, default=False, comment='是否已关闭')
    created_time = db.Column(db.DateTime, default=datetime.now, comment='创建时间')
    updated_time = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')

    # 注释掉关系定义，暂时不使用，避免初始化问题
    # defect = db.relationship('Defect', backref=db.backref('messages', lazy='dynamic'))

    def __init__(self, send_to_user_id, send_from_user_id, defect_id, message_type,
                 content, extra_params=None, is_closed=False):
        self.send_to_user_id = send_to_user_id
        self.send_from_user_id = send_from_user_id
        self.send_time = datetime.now()
        self.defect_id = defect_id
        self.message_type = message_type
        self.content = content
        self.extra_params = extra_params
        self.is_closed = is_closed

    def to_dict(self):
        """
        将模型转换为字典
        """
        return {
            'id': self.id,
            'send_to_user_id': self.send_to_user_id,
            'send_from_user_id': self.send_from_user_id,
            'send_time': self.send_time.strftime('%Y-%m-%d %H:%M:%S') if self.send_time else None,
            'defect_id': self.defect_id,
            'message_type': self.message_type,
            'content': self.content,
            'extra_params': self.extra_params,
            'is_closed': self.is_closed,
            'created_time': self.created_time.strftime('%Y-%m-%d %H:%M:%S') if self.created_time else None,
            'updated_time': self.updated_time.strftime('%Y-%m-%d %H:%M:%S') if self.updated_time else None
        }

    @classmethod
    def get_user_messages(cls, user_id, include_closed=False):
        """
        获取用户的消息
        """
        query = cls.query.filter_by(send_to_user_id=user_id)
        if not include_closed:
            query = query.filter_by(is_closed=False)
        return query.order_by(cls.send_time.desc()).all()

    @classmethod
    def close_message(cls, message_id, user_id):
        """
        关闭单条消息
        """
        message = cls.query.filter_by(
            id=message_id,
            send_to_user_id=user_id
        ).first()

        if message:
            message.is_closed = True
            message.updated_time = datetime.now()
            db.session.commit()
            return True
        return False

    @classmethod
    def close_all_user_messages(cls, user_id):
        """
        关闭用户的所有消息
        """
        messages = cls.query.filter_by(
            send_to_user_id=user_id,
            is_closed=False
        ).all()

        count = 0
        for message in messages:
            message.is_closed = True
            message.updated_time = datetime.now()
            count += 1

        if count > 0:
            db.session.commit()

        return count

    @classmethod
    def create_message(cls, send_to_user_id, send_from_user_id, defect_id,
                       message_type, content, extra_params=None):
        """
        创建新消息
        """
        message = cls(
            send_to_user_id=send_to_user_id,
            send_from_user_id=send_from_user_id,
            defect_id=defect_id,
            message_type=message_type,
            content=content,
            extra_params=extra_params
        )

        db.session.add(message)
        current_app.logger.debug(f'message_type： {message_type}')
        # db.session.commit()
        db.session.flush()
        return message

    @classmethod
    def get_unread_count(cls, user_id):
        """
        获取用户未读消息数量
        """
        return cls.query.filter_by(
            send_to_user_id=user_id,
            is_closed=False
        ).count()

    def __repr__(self):
        return f'<DefectMessage {self.id} to:{self.send_to_user_id} defect:{self.defect_id}>'