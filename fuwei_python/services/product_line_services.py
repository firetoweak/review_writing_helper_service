from flask import current_app

from conf.db import db
from models.defect.model import Defect
from models.product_line.model import ProductLine, Product, Version
from models.project_member.model import ProjectMember
from models.users.models import User
from sqlalchemy import and_, or_
from flask_paginate import  get_page_args,Pagination

from services.project_member_services import ProjectMemberService


class ProductLineService:
    """产品服务类，封装所有数据库操作"""

    @staticmethod
    def create_product_line(data):
        """创建产品线"""
        try:
            # 检查产品线名称是否已存在
            existing_line = ProductLine.query.filter(and_(ProductLine.name == data.get('name'),ProductLine.user_id == data.get('admin_user_id'))).first()
            if existing_line:
                return {'error': '产品线名称已存在'}, 400
            product_line = ProductLine(
                name=data.get('name'),
                user_id = data.get('admin_user_id'),
            )
            db.session.add(product_line)
            db.session.commit()
            return {'message': '产品线创建成功', 'data': product_line.to_dict()}, 201
        except Exception as e:
            db.session.rollback()
            return {'error': f'创建产品线失败: {str(e)}'}, 500

    @staticmethod
    def get_product_lines(filters=None):
        """获取产品线列表，支持过滤"""
        try:
            query = ProductLine.query.filter(ProductLine.user_id==filters['admin_user_id'])

            # 应用过滤条件
            if filters and filters.get('name'):
                query = query.filter(ProductLine.name.ilike(f"%{filters['name']}%"))  # 不区分大小写（case-insensitive）

            product_lines = query.all()
            return {'data': [line.to_dict() for line in product_lines]}, 200
        except Exception as e:
            return {'error': f'获取产品线失败: {str(e)}'}, 500

    @staticmethod
    def get_product_line_by_id(line_id):
        """根据ID获取产品线详情"""
        try:
            product_line = ProductLine.query.get(line_id)
            if not product_line:
                return {'error': '产品线不存在'}, 404

            return {'data': product_line.to_dict()}, 200
        except Exception as e:
            return {'error': f'获取产品线详情失败: {str(e)}'}, 500

    @staticmethod
    def update_product_line(data):
        """更新产品线"""
        try:
            product_line = ProductLine.query.filter(ProductLine.id==data['id'],ProductLine.user_id==data['admin_user_id']).first()
            if not product_line:
                return {'error': '产品线不存在'}, 404
            # 检查名称是否与其他产品线冲突
            if 'name' in data and data['name'] != product_line.name:
                existing_line = ProductLine.query.filter(
                    and_(ProductLine.name == data['name'],
                         ProductLine.id != data['id'])
                ).first()
                if existing_line:
                    return {'error': '产品线名称已存在'}, 400
            # 更新字段
            if 'name' in data:
                product_line.name = data['name']
            db.session.commit()
            return {'message': '产品线更新成功', 'data': product_line.to_dict()}, 200
        except Exception as e:
            db.session.rollback()
            return {'error': f'更新产品线失败: {str(e)}'}, 500

    @staticmethod
    def delete_product_line(admin_user_id,line_id):
        """删除产品线"""
        try:
            product_line = ProductLine.query.filter(ProductLine.id==line_id,ProductLine.user_id==admin_user_id).first()
            if not product_line:
                return {'error': '产品线不存在'}, 404
            product = Product.query.filter(Product.product_line_id==line_id).first()
            if product:
                return {'error': '产品线下还存在产品不可以删除'}, 404
            db.session.delete(product_line)
            db.session.commit()
            return {'message': '产品线删除成功'}, 200
        except Exception as e:
            db.session.rollback()
            return {'error': f'删除产品线失败: {str(e)}'}, 500

    @staticmethod
    def create_product(data):
        """创建产品"""
        try:
            product_line = ProductLine.query.filter(ProductLine.id ==data.get('level1_id')).first()
            if not product_line:
                return {'error': '产品线不存在'}, 400
            # 检查同一产品线下产品名称是否唯一
            existing_product_name = Product.query.filter(
                and_(Product.product_line_id == data.get('level1_id'),
                     Product.name == data.get('name'))
            ).first()
            if existing_product_name:
                return {'error': '同一产品线下产品名称必须唯一'}, 400

            product = Product(
                product_line_id=data.get('level1_id'),
                name=data.get('name'),
                code=data.get('code',""),
            )
            db.session.add(product)
            db.session.commit()
            return {'message': '产品创建成功', 'data': product.to_dict()}, 201
        except Exception as e:
            db.session.rollback()
            return {'error': f'创建产品失败: {str(e)}'}, 500

    @staticmethod
    def get_products(filters=None):
        """获取产品列表，支持按产品线名称和产品名过滤"""
        try:
            query = Product.query.join(ProductLine).filter(ProductLine.user_id==filters['admin_user_id'])
            # 应用过滤条件
            if filters:
                if filters.get('product_line_name'):
                    query = query.filter(ProductLine.name.ilike(f"%{filters['product_line_name']}%"))
                if filters.get('product_name'):
                    query = query.filter(Product.name.ilike(f"%{filters['product_name']}%"))
                if filters.get('is_active') is not None:
                    query = query.filter(Product.is_active == filters['is_active'])
            products = query.all()
            return {'data': [product.to_dict() for product in products]}, 200
        except Exception as e:
            return {'error': f'获取产品列表失败: {str(e)}'}, 500

    @staticmethod
    def get_product_by_id(product_id):
        """根据ID获取产品详情"""
        try:
            product = Product.query.get(product_id)
            if not product:
                return {'error': '产品不存在'}, 404

            return {'data': product.to_dict()}, 200
        except Exception as e:
            return {'error': f'获取产品详情失败: {str(e)}'}, 500

    @staticmethod
    def update_product(data):
        """更新产品"""
        try:
            product = Product.query.join(ProductLine).filter(and_(Product.id==data['id'],ProductLine.user_id == data['admin_user_id'])).first()
            if not product:
                return {'error': '产品线/产品不存在'}, 404
            # 检查同一产品线下产品名称是否唯一
            if 'name' in data and data['name'] != product.name:
                existing_product_name = Product.query.filter(
                    and_(Product.product_line_id == data.get('product_line_id', product.product_line_id),
                         Product.name == data['name'],
                         Product.id != data['id'])
                ).first()
                if existing_product_name:
                    return {'error': '同一产品线下产品名称必须唯一'}, 400
            # 更新字段
            if 'product_line_id' in data:
                product.product_line_id = data['product_line_id']
            if 'name' in data:
                product.name = data['name']
            db.session.commit()
            return {'message': '产品更新成功', 'data': product.to_dict()}, 200
        except Exception as e:
            db.session.rollback()
            return {'error': f'更新产品失败: {str(e)}'}, 500

    @staticmethod
    def delete_product(admin_user_id,product_id):
        """删除产品"""
        try:
            product = Product.query.join(ProductLine).filter(and_(Product.id==product_id,ProductLine.user_id == admin_user_id)).first()
            if not product:
                return {'error': '产品不存在'}, 404
            version = Version.query.filter(Version.product_id==product_id).first()
            if version:
                return {'error': '产品下存在版本，不可删除'}, 404
            db.session.delete(product)
            db.session.commit()
            return {'message': '产品删除成功'}, 200
        except Exception as e:
            db.session.rollback()
            return {'error': f'删除产品失败: {str(e)}'}, 500

    @staticmethod
    def create_version(data):
        """创建版本"""
        version_id = None
        version = None
        try:
            if data['desc']=="":
                return {'error': '请输入描述'}, 400
            if data['level3']=="":
                return {'error': '请输入版本名称'}, 400
            # 检查产品是否存在
            product = Product.query.join(ProductLine).filter(and_(Product.id==data.get('level2'),ProductLine.user_id == data.get('admin_user_id'))).first()
            if not product:
                return {'error': '产品线/产品不存在'}, 400

            # 检查同一产品下版本号是否唯一
            existing_version = Version.query.filter(
                and_(Version.product_id == data.get('level2'),
                     Version.version_number == data.get('level3'))
            ).first()
            if existing_version:
                return {'error': '同一产品下版本号必须唯一'}, 400
            version = Version(
                product_id=data.get('level2'),
                version_number=data.get('level3'),
                release_notes=data.get('desc'),
            )
            db.session.add(version)
            db.session.commit()
            version_id = version.id
            ProjectMemberService.create_member(project_id=None, version_id=version_id, user_id=data.get('user_id'), role_type="project_admin")
            db.session.commit()
            return {'message': '版本创建成功', 'data': version.to_dict()}, 200
        except Exception as e:
            db.session.rollback()
            if version_id is not None  and version is not None:
                db.session.delete(version)
            return {'error': f'创建版本失败: {str(e)}'}, 500

    @staticmethod
    def get_versions(filters=None, paginate=True):
        """获取版本列表，支持按产品线名称、产品名和版本号过滤"""
        try:
            # 构建基础查询 - 修改过滤逻辑
            query = Version.query.join(Product).join(ProductLine)

            # 应用过滤条件
            if filters:
                # 修改：使用更宽松的过滤条件
                if filters.get('admin_user_id'):
                    # 改为：产品线的用户ID等于admin_user_id，或者有其他访问权限
                    query = query.filter(ProductLine.user_id == filters['admin_user_id'])

                if filters.get('product_line_name'):
                    query = query.filter(ProductLine.name.ilike(f"%{filters['product_line_name']}%"))
                if filters.get('product_name'):
                    query = query.filter(Product.name.ilike(f"%{filters['product_name']}%"))

            # 调试：记录查询条件
            current_app.logger.debug(f"Versions query filters: {filters}")

            # 生成SQL语句用于调试
            sql = query.statement.compile(compile_kwargs={"literal_binds": True})
            current_app.logger.debug(f"Generated SQL: {sql}")

            if paginate:
                # 分页逻辑
                page, per_page, offset = get_page_args(page_parameter='page', per_page_parameter='per_page')
                total = query.count()
                versions = query.offset(offset).limit(per_page).all()

                # 优化成员查询 - 使用字典预先分组
                version_ids = [version.id for version in versions]
                version_members = {}
                if version_ids:
                    members = (ProjectMember.query
                               .join(User)
                               .filter(and_(
                        ProjectMember.version_id.in_(version_ids),
                        ProjectMember.role_type == "project_admin"
                    )).all())

                    for member in members:
                        if member.version_id not in version_members:
                            version_members[member.version_id] = []
                        version_members[member.version_id].append(member)

                # 设置成员信息
                for version in versions:
                    version.member_real_name = ""
                    version.member_email = ""
                    version.member_dept = ""

                    if version.id in version_members:
                        # 如果有多个管理员，可以连接他们的信息
                        members = version_members[version.id]
                        if members:
                            member = members[0]  # 取第一个管理员
                            version.member_real_name = member.user.real_name
                            version.member_email = member.user.email
                            version.member_dept = member.user.dept

                pagination = Pagination(
                    page=page,
                    per_page=per_page,
                    total=total,
                    css_framework='bootstrap5',
                    alignment='right',
                    prev_label='<',
                    next_label='>',
                )
                return {'data': versions, 'pagination': pagination}, 200
            else:
                # 不分页的情况 - 用于get_hierarchy
                versions = query.all()

                # 同样优化成员查询
                version_ids = [version.id for version in versions]
                version_members = {}
                if version_ids:
                    members = (ProjectMember.query
                               .join(User)
                               .filter(and_(
                        ProjectMember.version_id.in_(version_ids),
                        ProjectMember.role_type == "project_admin"
                    )).all())

                    for member in members:
                        if member.version_id not in version_members:
                            version_members[member.version_id] = []
                        version_members[member.version_id].append(member)

                # 设置成员信息
                for version in versions:
                    version.member_real_name = ""
                    version.member_email = ""
                    version.member_dept = ""

                    if version.id in version_members:
                        members = version_members[version.id]
                        if members:
                            member = members[0]
                            version.member_real_name = member.user.real_name
                            version.member_email = member.user.email
                            version.member_dept = member.user.dept

                return {'data': versions}, 200

        except Exception as e:
            current_app.logger.error(f"获取版本列表失败: {str(e)}")
            return {'error': f'获取版本列表失败: {str(e)}'}, 500


    @staticmethod
    def get_version_by_id(version_id):
        """根据ID获取版本详情"""
        try:
            version = Version.query.get(version_id)
            if not version:
                return {'error': '版本不存在'}, 404

            return {'data': version.to_dict()}, 200
        except Exception as e:
            return {'error': f'获取版本详情失败: {str(e)}'}, 500

    @staticmethod
    def get_versions_by_ids(version_ids):
        results = Version.query.join(Product).join(ProductLine).filter(Version.id.in_(version_ids)).all()
        versions_data = {}
        for result in results:
            versions_data[result.id] = f"{result.product.product_line.name}/{result.product.name}/{result.version_number}"
        return versions_data, 200

    @staticmethod
    def delete_version_ids(version_ids,admin_user_id):
        try:
            versions = Version.query.join(Product).join(ProductLine).filter(Version.id.in_(version_ids),ProductLine.user_id==admin_user_id).all()
            version_ids = []
            for version in versions:
                version_ids.append(version.id)
            if Defect.query.filter(Defect.version_id.in_(version_ids)).count()>0:
                return {'error': f'删除失败！你选中要删除的版本已经有缺陷记录关联'}, 500
            for version in versions:
                Version.query.filter(Version.id==version.id).delete()
                db.session.commit()
            return {'message': '批量删除成功', 'data': ''}, 200

        except Exception as e:
            print(f"{e}")
            return {'error': f'删除失败！'}, 500

    @staticmethod
    def update_version(version_id, data):
        user_id = int(data['user_id'])
        """更新版本"""
        try:
            if data['desc']=="":
                return {'error': '请输入描述'}, 400
            if data['level3']=="":
                return {'error': '请输入'}, 400
            version = Version.query.join(Product).join(ProductLine).filter(and_(ProductLine.user_id==data['admin_user_id'],Version.id ==version_id)).first()
            if not version:
                return {'error': '版本不存在'}, 404
            # 检查同一产品下版本号是否唯一
            if 'version_number' in data and data['version_number'] != version.version_number:
                existing_version = Version.query.filter(
                    and_(Version.product_id == data.get('product_id', version.product_id),
                         Version.version_number == data['version_number'],
                         Version.id != version_id)
                ).first()
                if existing_version:
                    return {'error': '同一产品下版本号必须唯一'}, 400
            project_admin_users = ProjectMemberService.find_members_by_role(project_id=None,version_id=version_id,role_type="project_admin")
            project_admin_user = project_admin_users[0] if project_admin_users else None
            if project_admin_user is not None:
                if project_admin_user.user_id != user_id:
                    project_member = ProjectMemberService.find_member(project_id=None,version_id=version_id,user_id=project_admin_user.user_id,role_type="project_admin")
                    project_member.user_id = user_id
            else:
                ProjectMemberService.create_member(project_id=None,version_id=version_id,user_id=user_id,role_type="project_admin")
            # 更新字段
            if 'level2' in data:
                version.product_id = data['level2']
            if 'level3' in data:
                version.version_number = data['level3']
            if 'desc' in data:
                version.release_notes = data['desc']
            db.session.commit()
            return {'message': '版本更新成功', 'data': version.to_dict()}, 200
        except Exception as e:
            print(f"{e}")
            db.session.rollback()
            return {'error': f'更新版本失败: {str(e)}'}, 500

    @staticmethod
    def delete_version(admin_user_id,version_id):
        """删除版本"""
        try:
            version = Version.query.join(Product).join(ProductLine).filter(and_(ProductLine.user_id==admin_user_id,Version.id ==version_id)).first()
            if not version:
                return {'error': '版本不存在'}, 404
            if Defect.query.filter(Defect.version_id==version.id).count()>0:
                return {'error': f'删除失败！你选中要删除的版本已经有缺陷记录关联'}, 500
            Version.query.filter(Version.id == version.id).delete()
            #db.session.delete(version)
            db.session.commit()
            return {'message': '版本删除成功'}, 200
        except Exception as e:
            db.session.rollback()
            return {'error': f'删除版本失败: {str(e)}'}, 500

    @staticmethod
    def validate_version_exists(version_id):
        """
        验证指定ID的版本是否存在

        Args:
            version_id (int): 版本
        Returns:
            bool: 如果项目存在返回True，否则返回False
        """
        try:
            # 查询数据库中是否存在指定ID的版本
            version = Version.query.get(version_id)
            return version is not None
        except Exception as e:
            # 记录错误日志（实际项目中可以添加日志记录）
            print(f"验证项目存在时出错: {str(e)}")
            return False

    @staticmethod
    def get_hierarchy(admin_user_id):
        product_lines_result, _ = ProductLineService.get_product_lines(filters={'admin_user_id': admin_user_id})
        product_lines = product_lines_result['data'] if 'data' in product_lines_result else []
        # 获取所有产品
        products_result, _ = ProductLineService.get_products(filters={'admin_user_id': admin_user_id})
        products = products_result['data'] if 'data' in products_result else []
        # 获取所有版本
        versions_result, _ = ProductLineService.get_versions(filters={'admin_user_id': admin_user_id}, paginate=False)
        versions = versions_result['data'] if 'data' in versions_result else []
        versions = [version.to_dict() for version in versions]
        # 构建层级结构
        hierarchy = []
        for line in product_lines:
            line_data = {
                'id': line['id'],
                'name': line['name'],
                'description': line.get('description', ''),
                'products': []
            }
            # 添加产品
            product_data = {}
            for product in products:
                if product['product_line_id'] == line['id']:
                    product_data = {
                        'id': product['id'],
                        'name': product['name'],
                        'description': product.get('description', ''),
                        'versions': []
                    }
                    # 添加版本
                    for version in versions:
                        if version['product_id'] == product['id']:
                            version_data = {
                                'id': version['id'],
                                'version_number': version['version_number'],
                            }
                            product_data['versions'].append(version_data)
                    line_data['products'].append(product_data)
            hierarchy.append(line_data)
        return hierarchy

    @staticmethod
    def get_hierarchy_by_version_id(version_id):
        """
        根据版本ID获取完整层级名称：产品线-产品-版本

        Args:
            version_id (int): 版本ID

        Returns:
            tuple: (字典数据, 状态码) 格式为 {'product_line_name': '', 'product_name': '', 'version_number': ''}
        """
        try:
            # 使用连接查询一次性获取所有相关信息
            result = (db.session.query(
                ProductLine.name.label('product_line_name'),
                Product.name.label('product_name'),
                Version.version_number.label('version_number')
            )
                      .select_from(Version)
                      .join(Product, Version.product_id == Product.id)
                      .join(ProductLine, Product.product_line_id == ProductLine.id)
                      .filter(Version.id == version_id)
                      .first())

            if not result:
                return {'error': '版本不存在或层级信息不完整'}, 404

            # 构建返回数据
            hierarchy_data = {
                'product_line_name': result.product_line_name,
                'product_name': result.product_name,
                'version_number': result.version_number,
                'full_path': f"{result.product_line_name}/{result.product_name}/{result.version_number}"
            }

            return {'data': hierarchy_data}, 200

        except Exception as e:
            return {'error': f'获取层级信息失败: {str(e)}'}, 500

    @staticmethod
    def get_hierarchy_by_version_ids(version_ids):
        """
        根据版本ID列表批量获取完整层级名称

        Args:
            version_ids (list): 版本ID列表

        Returns:
            tuple: (字典数据, 状态码) 格式为 {version_id: {'product_line_name': '', 'product_name': '', 'version_number': ''}}
        """
        try:
            if not version_ids:
                return {'data': {}}, 200

            # 使用连接查询批量获取信息
            results = (db.session.query(
                Version.id.label('version_id'),
                ProductLine.name.label('product_line_name'),
                Product.name.label('product_name'),
                Version.version_number.label('version_number')
            )
                       .select_from(Version)
                       .join(Product, Version.product_id == Product.id)
                       .join(ProductLine, Product.product_line_id == ProductLine.id)
                       .filter(Version.id.in_(version_ids))
                       .all())

            hierarchy_data = {}
            for result in results:
                hierarchy_data[result.version_id] = {
                    'product_line_name': result.product_line_name,
                    'product_name': result.product_name,
                    'version_number': result.version_number,
                    'full_path': f"{result.product_line_name}/{result.product_name}/{result.version_number}"
                }

            # 处理未找到的版本ID
            for vid in version_ids:
                if vid not in hierarchy_data:
                    hierarchy_data[vid] = {
                        'product_line_name': '未知',
                        'product_name': '未知',
                        'version_number': '未知',
                        'full_path': '未知/未知/未知'
                    }

            return {'data': hierarchy_data}, 200

        except Exception as e:
            return {'error': f'批量获取层级信息失败: {str(e)}'}, 500