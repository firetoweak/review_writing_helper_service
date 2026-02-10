from conf.db import db
from sqlalchemy import Column, Integer, String, Float, and_, DateTime, Text, Date, Boolean, ForeignKey, UniqueConstraint
from datetime import datetime

class ProductLine(db.Model):
    """产品线模型"""
    __tablename__ = 'product_lines'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    # 添加外键关联到user表的user_id字段
    user_id = Column(Integer, ForeignKey('user.user_id'), nullable=True)  # 根据实际情况调整nullable
    created_time = Column(DateTime, default=datetime.now())
    updated_time = Column(DateTime, default=datetime.now(), onupdate=datetime.now())
    # 添加与User的关系
    user = db.relationship('User', backref='product_lines')

    # 关系定义: 'Product' 指定关联的模型类，表示当前模型（ProductLine）与 Product 是一对多关系
    # backref='product_line' 在 Product 模型中自动创建反向引用属性，可通过 product.product_line 访问父模型实例
    # cascade='all, delete-orphan' 实现级联删除：当父模型（如 ProductLine）删除时，关联的所有子模型（Product）自动删除；若子模型与父模型解除关联（如设为 None），子模型也会被删除
    # lazy='dynamic' 将返回一个未执行的查询对象（AppenderQuery），允许后续追加过滤条件（如 product_line.products.filter_by(active=True)），避免立即加载全部数据
    products = db.relationship('Product', backref='product_line', cascade='all, delete-orphan', lazy='dynamic')

    def __repr__(self):
        return f'<ProductLine {self.name}>'

    def to_dict(self):
        """转换为字典格式，便于JSON序列化"""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'user_id': self.user_id,  # 添加user_id到字典
            'created_time': self.created_time.isoformat(),
            'updated_time': self.updated_time.isoformat(),
            'product_count': self.products.count()  # 该产品线下产品的个数
        }

class Product(db.Model):
    """产品模型"""
    __tablename__ = 'products'

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_line_id = Column(Integer, ForeignKey('product_lines.id', ondelete='CASCADE'), nullable=False)
    name = Column(String(100), nullable=False)
    code = Column(String(50), nullable=False, unique=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_time = Column(DateTime, default=datetime.now())

    # 关系定义
    versions = db.relationship('Version', backref='product', cascade='all, delete-orphan', lazy='dynamic')

    # 同一产品线下产品名称唯一
    __table_args__ = (
        UniqueConstraint('product_line_id', 'name', name='unique_product_name_per_line'),
    )


    def __repr__(self):
        return f'<Product {self.code} - {self.name}>'

    def to_dict(self):
        """转换为字典格式"""
        return {
            'id': self.id,
            'product_line_id': self.product_line_id,
            'name': self.name,
            'code': self.code,
            'description': self.description,
            'is_active': self.is_active,
            'created_time': self.created_time.isoformat(),
            'version_count': self.versions.count()
        }


class Version(db.Model):
    """版本模型"""
    __tablename__ = 'versions'

    id = (Column(Integer, primary_key=True, autoincrement=True))
    product_id = Column(Integer, ForeignKey('products.id', ondelete='CASCADE'), nullable=False)
    version_number = Column(String(20), nullable=False)
    code_name = Column(String(100), nullable=True)
    release_notes = Column(Text, nullable=True)
    release_date = Column(Date, nullable=True)
    is_supported = Column(Boolean, default=True)
    created_time = Column(DateTime, default=datetime.now())

    # 关系定义
    user_roles = db.relationship('UserRole', back_populates='version', cascade='all, delete-orphan')

    # 唯一约束：同一个产品下版本号不能重复
    __table_args__ = (
        UniqueConstraint('product_id', 'version_number', name='unique_product_version'),
    )

    def __repr__(self):
        return f'<Version {self.version_number} of Product {self.product_id}>'

    def to_dict(self):
        """转换为字典格式"""
        return {
            'id': self.id,
            'product_id': self.product_id,
            'version_number': self.version_number,
            'code_name': self.code_name,
            'release_notes': self.release_notes,
            'release_date': self.release_date.isoformat() if self.release_date else None,
            'is_supported': self.is_supported,
            'created_time': self.created_time.isoformat()
        }