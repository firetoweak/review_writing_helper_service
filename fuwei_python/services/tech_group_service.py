from conf.db import db
from models.defect.model import Defect
from models.tech_group.model import TechGroup, Project, Platform
from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy import and_, or_
from models.project_member.model import ProjectMember
from flask_paginate import  get_page_args,Pagination
from models.users.models import User
from services.project_member_services import ProjectMemberService


class TechGroupService:
    """技术族类，封装所有数据库操作"""

    @staticmethod
    def create_tech_group(data):
        """创建产品线"""
        try:
            # 检查产品线名称是否已存在
            tech_group = TechGroup.query.filter(and_(TechGroup.name==data.get('name'),TechGroup.user_id==data['admin_user_id'])).first()
            if tech_group:
                return {'error': '技术族名称已存在'}, 400
            tech_group = TechGroup(
                name=data.get('name'),
                user_id=data.get('admin_user_id'),
            )
            db.session.add(tech_group)
            db.session.commit()
            return {'message': '技术族创建成功', 'data': tech_group.to_dict()}, 201
        except Exception as e:
            db.session.rollback()
            return {'error': f'创建技术族失败: {str(e)}'}, 500

    @staticmethod
    def get_tech_groups(filters=None):
        """获取产品线列表，支持过滤"""
        try:
            query = TechGroup.query.filter(TechGroup.user_id==filters['admin_user_id'])

            # 应用过滤条件
            if filters and filters.get('name'):
                query = query.filter(TechGroup.name.ilike(f"%{filters['name']}%"))  # 不区分大小写（case-insensitive）

            tech_groups = query.all()
            return {'data': [tech_group.to_dict() for tech_group in tech_groups]}, 200
        except Exception as e:
            return {'error': f'获取技术族失败: {str(e)}'}, 500

    @staticmethod
    def get_tech_group_by_id(group_id):
        """根据ID获取产品线详情"""
        try:
            tech_group = TechGroup.query.get(group_id)
            if not tech_group:
                return {'error': '技术族不存在'}, 404

            return {'data': tech_group.to_dict()}, 200
        except Exception as e:
            return {'error': f'获取产品线详情失败: {str(e)}'}, 500

    @staticmethod
    def update_tech_group(data):
        """更新技术族"""
        try:
            tech_group = TechGroup.query.filter(TechGroup.id==data['id'],TechGroup.user_id==data['admin_user_id']).first()
            if not tech_group:
                return {'error': '技术族不存在'}, 404

            # 检查名称是否与其他产品线冲突
            if 'name' in data and data['name'] != tech_group.name:
                existing_group = TechGroup.query.filter(
                    and_(TechGroup.name == data['name'],
                         TechGroup.id != data['id'])
                ).first()
                if existing_group:
                    return {'error': '技术族名称已存在'}, 400

            # 更新字段
            if 'name' in data:
                tech_group.name = data['name']
            db.session.commit()
            return {'message': '技术族更新成功', 'data': tech_group.to_dict()}, 200
        except Exception as e:
            db.session.rollback()
            return {'error': f'更新产品线失败: {str(e)}'}, 500

    @staticmethod
    def delete_tech_group(admin_user_id,group_id):
        """删除产品线"""
        try:
            tech_group = TechGroup.query.filter(and_(TechGroup.user_id==admin_user_id,TechGroup.id == group_id)).first()
            if not tech_group:
                return {'error': '技术族不存在'}, 404
            db.session.delete(tech_group)
            db.session.commit()
            return {'message': '技术族删除成功'}, 200
        except Exception as e:
            db.session.rollback()
            return {'error': f'删除技术族失败: {str(e)}'}, 500

    @staticmethod
    def create_platform(data):
        """创建产品"""
        try:
            # 检查技术族是否存在get({"user_id": data.get('admin_user_id'), "group_id": data.get('tech_group_id')})
            tech_group = TechGroup.query.filter(and_(TechGroup.user_id==data.get('admin_user_id'),TechGroup.id == data.get('level1_id'))).first()
            if not tech_group:
                return {'error': '技术族不存在'}, 400
            # 检查同一产品线下产品名称是否唯一
            existing_platform_name = Platform.query.filter(
                and_(Platform.tech_group_id == data.get('level1_id'),
                     Platform.name == data.get('name'))
            ).first()
            if existing_platform_name:
                return {'error': '同一技术族下平台名称必须唯一'}, 400

            platform = Platform(
                tech_group_id=data.get('level1_id'),
                name=data.get('name'),
                type= ''
            )
            db.session.add(platform)
            db.session.commit()
            return {'message': '平台创建成功', 'data': platform.to_dict()}, 201
        except Exception as e:
            db.session.rollback()
            return {'error': f'创建平台失败: {str(e)}'}, 500

    @staticmethod
    def get_platforms(filters=None):
        """获取平台列表"""
        try:
            query = Platform.query.join(TechGroup).filter(TechGroup.user_id==filters['admin_user_id'])
            # 应用过滤条件
            if filters:
                if filters.get('tech_group_name'):
                    query = query.filter(TechGroup.name.ilike(f"%{filters['tech_group_name']}%"))
                if filters.get('platform_name'):
                    query = query.filter(Platform.name.ilike(f"%{filters['platform_name']}%"))
                if filters.get('is_active') is not None:
                    query = query.filter(Platform.is_active == filters['is_active'])
            platforms = query.all()
            return {'data': [platform.to_dict() for platform in platforms]}, 200
        except Exception as e:
            return {'error': f'获取产品列表失败: {str(e)}'}, 500

    @staticmethod
    def get_platform_by_id(platform_id):
        """根据ID获取平台详情"""
        try:
            platform = Platform.query.get(platform_id)
            if not platform:
                return {'error': '平台不存在'}, 404

            return {'data': platform.to_dict()}, 200
        except Exception as e:
            return {'error': f'获取产品详情失败: {str(e)}'}, 500

    @staticmethod
    def update_platform(data):
        """更新产品"""
        try:
            platform = Platform.query.join(TechGroup).filter(and_(Platform.id==data['id'],TechGroup.user_id == data['admin_user_id'])).first()
            if not platform:
                return {'error': '不存在'}, 404
            # 检查产品线是否存在
            if 'tech_group_id' in data:
                tech_group = TechGroup.query.filter({"user_id": data.get('user_id'), "group_id": data.get('tech_group_id')})
                if not tech_group:
                    return {'error': '技术族不存在'}, 400
            # 检查同一技术族下平台名称是否唯一
            if 'name' in data and data['name'] != platform.name:
                existing_platform_name = TechGroup.query.filter(
                    and_(Platform.tech_group_id == data.get('tech_group_id', platform.tech_group_id),
                         Platform.name == data['name'],
                         Platform.id != data['id'])
                ).first()
                if existing_platform_name:
                    return {'error': '同一技术族下平台名称必须唯一'}, 400
            platform.name = data['name']
            db.session.commit()
            return {'message': '产品更新成功', 'data': platform.to_dict()}, 200
        except Exception as e:
            db.session.rollback()
            return {'error': f'更新产品失败: {str(e)}'}, 500

    @staticmethod
    def delete_platform(platform_id,admin_user_id):
        """删除产品"""
        try:
            platform = Platform.query.join(TechGroup).filter(and_(Platform.id==platform_id,TechGroup.user_id == admin_user_id)).first()
            if not platform:
                return {'error': '平台不存在'}, 404
            db.session.delete(platform)
            db.session.commit()
            return {'message': '平台删除成功'}, 200
        except Exception as e:
            db.session.rollback()
            return {'error': f'删除平台失败: {str(e)}'}, 500

    @staticmethod
    def create_project(data):
        """创建版本"""
        try:
            if data['desc']=="":
                return {'error': '请输入描述'}, 400
            if data['level3']=="":
                return {'error': '请输入项目名称'}, 400
            # 检查平台是否存在
            platform = Platform.query.join(TechGroup).filter(and_(Platform.id==data.get('level2'),TechGroup.user_id==data['admin_user_id'])).first()
            if not platform:
                return {'error': '技术族/平台不存在'}, 400

            # 检查同一平台下版本号是否唯一
            existing_project = Project.query.filter(
                and_(Project.platform_id == data.get('level2'),
                     Project.name == data.get('name'))
            ).first()
            if existing_project:
                return {'error': '同一平台下项目名称必须唯一'}, 400
            project = Project(
                platform_id=data.get('level2'),
                name=data.get('level3'),
                code=data.get('level3', ""),
                description =data.get('desc', ""),
            )
            db.session.add(project)
            db.session.commit()
            project_id = project.id
            ProjectMemberService.create_member(project_id=project_id, version_id=None, user_id=data.get('user_id'),role_type="project_admin")
            db.session.commit()
            return {'message': '项目创建成功', 'data': project.to_dict()}, 201
        except Exception as e:
            db.session.rollback()
            return {'error': f'项目版本失败: {str(e)}'}, 500

    @staticmethod
    def get_projects(filters=None):
        """获取项目列表"""
        try:
            #query = Project.query.join(Platform).join(TechGroup).join(User).filter(TechGroup.user_id==filters['admin_user_id'])
            query = Project.query.join(Platform).join(TechGroup).join(User).filter(TechGroup.user_id==filters['admin_user_id'])
            page, per_page, offset = get_page_args(page_parameter='page', per_page_parameter='per_page')
            # 应用过滤条件
            if filters:
                if filters.get('tech_group_name'):
                    query = query.filter(TechGroup.name.ilike(f"%{filters['tech_group_name']}%"))
                if filters.get('platform_name'):
                    query = query.filter(Platform.name.ilike(f"%{filters['platform_name']}%"))
                if filters.get('project_name'):
                    query = query.filter(Project.name.ilike(f"%{filters['project_name']}%"))
            # 生成SQL语句
            # sql = query.statement.compile(compile_kwargs={"literal_binds": True})
            # print(f"Generated SQL: {sql}")  # 实际开发中可用日志记录
            total = query.count()
            projects = query.offset(offset).limit(per_page).all()
            project_ids = []
            for project in projects:
                project_ids.append(project.id)
            project_members = ProjectMember.query.join(User).filter(and_(ProjectMember.project_id.in_(project_ids),ProjectMember.role_type=="project_admin")).all()
            for project in projects:
                project.member_real_name = ""
                project.member_email = ""
                project.member_dept = ""
                for member in project_members:
                    if member.project_id == project.id:
                        project.member_real_name = member.user.real_name
                        project.member_email = member.user.email
                        project.member_dept = member.user.dept
            pagination = Pagination(
                page=page,
                per_page=per_page,
                total=total,
                css_framework='bootstrap5',  # 支持 bootstrap4/bootstrap5/foundation 等
                alignment='right',  # 分页居中
                prev_label='<',  # 自定义上一页文本
                next_label='>',  # 自定义下一页文本
            )
            return {'data': projects,'pagination':pagination}, 200
        except Exception as e:
            return {'error': f'获取版本列表失败: {str(e)}'}, 500

    @staticmethod
    def get_project_by_id(project_id):
        """根据ID获取版本详情"""
        try:
            version = Project.query.get(project_id)
            if not version:
                return {'error': '版本不存在'}, 404

            return {'data': version.to_dict()}, 200
        except Exception as e:
            return {'error': f'获取版本详情失败: {str(e)}'}, 500

    @staticmethod
    def get_projects_by_ids(project_ids):
        results = Project.query.join(Platform).join(TechGroup).filter(Project.id.in_(project_ids)).all()
        projects_data = {}
        for result in results:
            projects_data[result.id] = f"{result.platform.tech_group.name}/{result.platform.name}/{result.name}"
        return projects_data, 200

    @staticmethod
    def update_project(project_id, data):
        user_id = data.get('user_id')
        """更新项目"""
        try:
            project = Project.query.join(Platform).join(TechGroup).filter(and_(TechGroup.user_id==data['admin_user_id'],Project.id ==project_id)).first()
            if not project:
                return {'error': '项目/平台/技术族不存在'}, 404
            if 'level3' in data and data['level3'] != project.name:
                existing_project = Project.query.filter(
                    and_(Project.platform_id == project.platform_id,
                         Project.name == data['level3'],
                         Project.id != project_id)
                ).first()
                if existing_project:
                    return {'error': '同一平台下的存在相同的项目名称'}, 400
            # 更新字段
            project.name = data['level3']
            project.description = data['desc']


            project_admin_users = ProjectMemberService.find_members_by_role(project_id=project_id,version_id=None,role_type="project_admin")
            project_admin_user = project_admin_users[0] if project_admin_users else None
            if project_admin_user is not None:
                if project_admin_user.user_id != user_id:
                    project_member = ProjectMemberService.find_member(project_id=project_id,version_id=None,user_id=project_admin_user.user_id,role_type="project_admin")
                    print(user_id)
                    print(project_member.to_dict())
                    project_member.user_id = user_id
            else:
                ProjectMemberService.create_member(project_id=project_id,version_id=None,user_id=user_id,role_type="project_admin")
            db.session.commit()
            return {'message': '项目更新成功', 'data': project.to_dict()}, 200
        except Exception as e:
            print(f'{e}')
            db.session.rollback()
            return {'error': f'更新项目失败: {str(e)}'}, 500

    @staticmethod
    def delete_project(project_id,admin_user_id):
        """删除版本"""
        try:
            query = Project.query.join(Platform).join(TechGroup).filter(and_(TechGroup.user_id==admin_user_id,Project.id ==project_id))
            project =query.first()
            sql = query.statement.compile(compile_kwargs={"literal_binds": True})
            print(f"Generated SQL: {sql}")  # 实际开发中可用日志记录

            if not project:
                return {'error': '项目不存在'}, 404
            if Defect.query.filter(Defect.project_id==project.id).count()>0:
                return {'error': f'删除失败！你选中要删除的项目已经有缺陷记录关联'}, 500
            db.session.delete(project)
            db.session.commit()
            return {'message': '项目删除成功'}, 200
        except Exception as e:
            db.session.rollback()
            return {'error': f'项目删除失败: {str(e)}'}, 500

    @staticmethod
    def delete_project_ids(project_ids,admin_user_id):
        try:
            projects = Project.query.join(Platform).join(TechGroup).filter(Project.id.in_(project_ids),TechGroup.user_id==admin_user_id).all()
            project_ids = []
            for project in projects:
                project_ids.append(project.id)
            if Defect.query.filter(Defect.project_id.in_(project_ids)).count()>0:
                return {'error': f'删除失败！你选中要删除的项目已经有缺陷记录关联'}, 500
            for project in projects:
                Project.query.filter(Project.id ==project.id).delete()
                db.session.commit()
            return {'message': '批量删除成功', 'data': ''}, 200
        except Exception as e:
            print(f"{e}")
            return {'error': f'删除失败！'}, 500


    @staticmethod
    def validate_project_exists(project_id):
        """
        验证指定ID的版本是否存在

        Args:
            project_id (int): 版本

        Returns:
            bool: 如果项目存在返回True，否则返回False
        """
        try:
            # 查询数据库中是否存在指定ID的版本
            project = Project.query.get(project_id)
            return project is not None
        except Exception as e:
            # 记录错误日志（实际项目中可以添加日志记录）
            print(f"验证项目存在时出错: {str(e)}")
            return False

    @staticmethod
    def get_hierarchy(admin_user_id):
        filter={}
        filter['admin_user_id'] = admin_user_id
        tech_groups_result, _ = TechGroupService.get_tech_groups(filter)
        tech_groups = tech_groups_result['data'] if 'data' in tech_groups_result else []

        # 获取所有平台
        platform_result, _ = TechGroupService.get_platforms(filter)
        platforms = platform_result['data'] if 'data' in platform_result else []
        # 获取所有版本
        projects_result, _ = TechGroupService.get_projects(filter)
        projects = projects_result['data'] if 'data' in projects_result else []
        projects = [project.to_dict() for project in projects]
        # 构建层级结构
        hierarchy = []
        for group in tech_groups:
            group_data = {
                'id': group['id'],
                'name': group['name'],
                'description': group.get('description', ''),
                'platforms': []
            }
            for platform in platforms:
                if platform['tech_group_id'] == group['id']:
                    platform_data = {
                        'id': platform['id'],
                        'name': platform['name'],
                        'description': platform.get('description', ''),
                        'projects': []
                    }
                    # 添加版本
                    for project in projects:
                        if project['platform_id'] == platform['id']:
                            project_data = {
                                'id': project['id'],
                                'name': project['name'],
                                'description': project.get('description', ''),
                            }
                            platform_data['projects'].append(project_data)
                    group_data['platforms'].append(platform_data)
            hierarchy.append(group_data)
        return hierarchy

    @staticmethod
    def get_hierarchy_by_project_id(project_id):
        """
        根据项目ID获取完整层级名称：技术族-平台-项目

        Args:
            project_id (int): 项目ID

        Returns:
            tuple: (字典数据, 状态码) 格式为 {'tech_group_name': '', 'platform_name': '', 'project_name': ''}
        """
        try:
            # 使用连接查询一次性获取所有相关信息
            result = (db.session.query(
                TechGroup.name.label('tech_group_name'),
                Platform.name.label('platform_name'),
                Project.name.label('project_name')
            )
                      .select_from(Project)
                      .join(Platform, Project.platform_id == Platform.id)
                      .join(TechGroup, Platform.tech_group_id == TechGroup.id)
                      .filter(Project.id == project_id)
                      .first())

            if not result:
                return {'error': '项目不存在或层级信息不完整'}, 404

            # 构建返回数据
            hierarchy_data = {
                'tech_group_name': result.tech_group_name,
                'platform_name': result.platform_name,
                'project_name': result.project_name,
                'full_path': f"{result.tech_group_name}/{result.platform_name}/{result.project_name}"
            }

            return {'data': hierarchy_data}, 200

        except Exception as e:
            return {'error': f'获取层级信息失败: {str(e)}'}, 500

    @staticmethod
    def get_hierarchy_by_project_ids(project_ids):
        """
        根据项目ID列表批量获取完整层级名称

        Args:
            project_ids (list): 项目ID列表

        Returns:
            tuple: (字典数据, 状态码) 格式为 {project_id: {'tech_group_name': '', 'platform_name': '', 'project_name': ''}}
        """
        try:
            if not project_ids:
                return {'data': {}}, 200

            # 使用连接查询批量获取信息
            results = (db.session.query(
                Project.id.label('project_id'),
                TechGroup.name.label('tech_group_name'),
                Platform.name.label('platform_name'),
                Project.name.label('project_name')
            )
                       .select_from(Project)
                       .join(Platform, Project.platform_id == Platform.id)
                       .join(TechGroup, Platform.tech_group_id == TechGroup.id)
                       .filter(Project.id.in_(project_ids))
                       .all())

            hierarchy_data = {}
            for result in results:
                hierarchy_data[result.project_id] = {
                    'tech_group_name': result.tech_group_name,
                    'platform_name': result.platform_name,
                    'project_name': result.project_name,
                    'full_path': f"{result.tech_group_name}/{result.platform_name}/{result.project_name}"
                }

            # 处理未找到的项目ID
            for pid in project_ids:
                if pid not in hierarchy_data:
                    hierarchy_data[pid] = {
                        'tech_group_name': '未知',
                        'platform_name': '未知',
                        'project_name': '未知',
                        'full_path': '未知/未知/未知'
                    }

            return {'data': hierarchy_data}, 200

        except Exception as e:
            return {'error': f'批量获取层级信息失败: {str(e)}'}, 500



class BaseService:
    """基础Service类，提供通用方法"""

    @staticmethod
    def commit_changes():
        """提交数据库更改"""
        try:
            db.session.commit()
            return True, None
        except (IntegrityError, SQLAlchemyError) as e:
            db.session.rollback()
            return False, str(e)



class ProjectService(BaseService):
    """项目服务类"""

    @staticmethod
    def get_all():
        """获取所有项目"""
        try:
            projects = Project.query.all()
            return {'data': [project.to_dict() for project in projects]}, 200
        except Exception as e:
            return {'error': f'获取项目列表失败: {str(e)}'}, 500

    @staticmethod
    def validate_project_exists(project_id):
        """
        验证指定ID的项目是否存在

        Args:
            project_id (int): 项目ID

        Returns:
            bool: 如果项目存在返回True，否则返回False
        """
        try:
            # 查询数据库中是否存在指定ID的项目
            project = Project.query.get(project_id)
            return project is not None
        except Exception as e:
            # 记录错误日志（实际项目中可以添加日志记录）
            print(f"验证项目存在时出错: {str(e)}")
            return False

    @staticmethod
    def get_by_id(project_id: int):
        """根据ID获取项目"""
        try:
            project = Project.query.get(project_id)
            if not project:
                return {'error': '项目不存在'}, 404
            return {'data': project.to_dict()}, 200
        except Exception as e:
            return {'error': f'获取项目详情失败: {str(e)}'}, 500

    @staticmethod
    def get_by_platform(platform_id: int):
        """根据平台ID获取所有项目"""
        try:
            projects = Project.query.filter_by(platform_id=platform_id).all()
            return {'data': [project.to_dict() for project in projects]}, 200
        except Exception as e:
            return {'error': f'获取平台项目列表失败: {str(e)}'}, 500

    @staticmethod
    def create(platform_id: int, name: str, code: str,
               description: Optional[str] = None,
               repo_url: Optional[str] = None,
               current_version: Optional[str] = None,
               status: str = 'PLANNING',
               start_date: Optional[datetime] = None,
               end_date: Optional[datetime] = None):
        """创建新项目"""
        try:
            # 检查平台是否存在
            platform = Platform.query.get(platform_id)
            if not platform:
                return {'error': '平台不存在'}, 400

            # 检查项目代码是否已存在
            existing_project_by_code = Project.query.filter_by(code=code).first()
            if existing_project_by_code:
                return {'error': '项目代码已存在'}, 400

            # 检查同一平台下项目名称是否唯一
            existing_project_by_name = Project.query.filter_by(
                platform_id=platform_id,
                name=name
            ).first()
            if existing_project_by_name:
                return {'error': '同一平台下项目名称必须唯一'}, 400

            project = Project(
                platform_id=platform_id,
                name=name,
                code=code,
                description=description,
                repo_url=repo_url,
                current_version=current_version,
                status=status,
                start_date=start_date,
                end_date=end_date
            )

            db.session.add(project)
            success, error = BaseService.commit_changes()
            if not success:
                return {'error': f'创建项目失败: {error}'}, 500

            return {'message': '项目创建成功', 'data': project.to_dict()}, 201
        except Exception as e:
            db.session.rollback()
            return {'error': f'创建项目失败: {str(e)}'}, 500

    @staticmethod
    def update(project_id: int, **kwargs):
        """更新项目信息"""
        try:
            project = Project.query.get(project_id)
            if not project:
                return {'error': '项目不存在'}, 404

            # 检查平台是否存在（如果更新了platform_id）
            if 'platform_id' in kwargs:
                platform = Platform.query.get(kwargs['platform_id'])
                if not platform:
                    return {'error': '平台不存在'}, 400

            # 检查项目代码是否与其他项目冲突
            if 'code' in kwargs and kwargs['code'] != project.code:
                existing_project = Project.query.filter(
                    Project.code == kwargs['code'],
                    Project.id != project_id
                ).first()
                if existing_project:
                    return {'error': '项目代码已存在'}, 400

            # 检查同一平台下项目名称是否唯一
            if 'name' in kwargs and kwargs['name'] != project.name:
                existing_project = Project.query.filter(
                    Project.platform_id == kwargs.get('platform_id', project.platform_id),
                    Project.name == kwargs['name'],
                    Project.id != project_id
                ).first()
                if existing_project:
                    return {'error': '同一平台下项目名称必须唯一'}, 400

            # 过滤允许更新的字段
            allowed_fields = ['platform_id', 'name', 'code', 'description', 'repo_url',
                              'current_version', 'status', 'start_date', 'end_date']
            for field, value in kwargs.items():
                if field in allowed_fields and hasattr(project, field):
                    setattr(project, field, value)

            success, error = BaseService.commit_changes()
            if not success:
                return {'error': f'更新项目失败: {error}'}, 500

            return {'message': '项目更新成功', 'data': project.to_dict()}, 200
        except Exception as e:
            db.session.rollback()
            return {'error': f'更新项目失败: {str(e)}'}, 500

    @staticmethod
    def delete(project_id: int):
        """删除项目"""
        try:
            project = Project.query.get(project_id)
            if not project:
                return {'error': '项目不存在'}, 404

            db.session.delete(project)
            success, error = BaseService.commit_changes()
            if not success:
                return {'error': f'删除项目失败: {error}'}, 500

            return {'message': '项目删除成功'}, 200
        except Exception as e:
            db.session.rollback()
            return {'error': f'删除项目失败: {str(e)}'}, 500


