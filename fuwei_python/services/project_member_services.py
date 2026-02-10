from functools import wraps

from flask import current_app, g, jsonify, request, session
from sqlalchemy import or_, and_

from models.defect_level.model import db
from sqlalchemy.exc import IntegrityError
from typing import List, Optional, Dict, Any, Tuple

from models.product_line.model import Version, Product, ProductLine
# 删除 RoleType 导入，直接使用 ProjectMember
from models.project_member.model import ProjectMember, role_dict
from models.tech_group.model import Project, Platform, TechGroup
from models.users.models import User
from services.role_services import UserRoleService


class ProjectMemberService:
    @staticmethod
    def create_member(project_id: Optional[int], version_id: Optional[int], user_id: int,
                      role_type: str) -> ProjectMember:
        """添加项目/版本成员"""
        if not (project_id or version_id):
            raise ValueError("必须提供 project_id 或 version_id")

        # 验证角色类型是否有效
        if role_type not in role_dict:
            raise ValueError(f"无效的角色类型: {role_type}")

        # 验证用户是否存在且未删除
        user = User.query.filter_by(user_id=user_id, is_delete=0).first()
        if not user:
            raise ValueError("用户不存在或已被删除")

        # 首先检查成员是否已存在（现在按角色类型检查）
        existing_member = ProjectMemberService.find_member(project_id, version_id, user_id, role_type)
        if existing_member:
            raise ValueError(f"用户 {user.real_name} 在此项目/版本中已存在相同角色: {role_type}")

        member = ProjectMember(
            project_id=project_id,
            version_id=version_id,
            user_id=user_id,
            role_type=role_type
        )
        db.session.add(member)
        try:
            db.session.commit()
        except IntegrityError as e:
            db.session.rollback()
            current_app.logger.error(f"创建成员时发生完整性错误: {str(e)}")
            raise ValueError("创建成员时发生数据库完整性错误")
        return member

    @staticmethod
    def create_members_batch(project_id: Optional[int], version_id: Optional[int],
                             user_roles: List[Tuple[int, str]]) -> Tuple[List[ProjectMember], List[Dict]]:
        """
        批量添加项目/版本成员

        Args:
            project_id: 项目ID（可选）
            version_id: 版本ID（可选）
            user_roles: 用户ID和角色类型的元组列表，例如 [(user_id1, 'role1'), (user_id2, 'role2')]

        Returns:
            Tuple: (成功添加的成员列表, 失败信息列表)
        """
        if not (project_id or version_id):
            raise ValueError("必须提供 project_id 或 version_id")

        if not user_roles:
            raise ValueError("用户角色列表不能为空")

        # 验证所有角色类型是否有效
        invalid_roles = [role for _, role in user_roles if role not in role_dict]
        if invalid_roles:
            raise ValueError(f"无效的角色类型: {set(invalid_roles)}")

        # 获取所有用户ID
        user_ids = [user_id for user_id, _ in user_roles]

        # 批量验证用户是否存在且未删除
        valid_users = User.query.filter(
            User.user_id.in_(user_ids),
            User.is_delete == 0
        ).all()

        valid_user_ids = {user.user_id for user in valid_users}
        valid_user_map = {user.user_id: user for user in valid_users}

        # 检查不存在的用户
        invalid_user_ids = set(user_ids) - valid_user_ids
        if invalid_user_ids:
            raise ValueError(f"以下用户不存在或已被删除: {list(invalid_user_ids)}")

        # 批量检查已存在的成员（现在按角色类型检查）
        existing_members = ProjectMember.query.filter(
            or_(
                and_(ProjectMember.project_id == project_id, ProjectMember.version_id.is_(None)),
                and_(ProjectMember.version_id == version_id, ProjectMember.project_id.is_(None))
            ),
            ProjectMember.user_id.in_(user_ids)
        ).all()

        # 修改为按 (project_id, version_id, user_id, role_type) 组合检查
        existing_user_role_map = {
            (member.project_id, member.version_id, member.user_id, member.role_type): member
            for member in existing_members
        }

        success_members = []
        failed_records = []

        # 准备批量添加的成员对象
        members_to_add = []
        added_user_roles = []  # 记录成功添加的用户ID和角色类型组合

        for user_id, role_type in user_roles:
            # 检查是否已存在相同角色的成员
            key = (project_id, version_id, user_id, role_type)
            if key in existing_user_role_map:
                existing_member = existing_user_role_map[key]
                user_name = valid_user_map[user_id].real_name
                failed_records.append({
                    'user_id': user_id,
                    'role_type': role_type,
                    'error': f"用户 {user_name} 在此项目/版本中已存在相同角色: {role_type}"
                })
                continue

            member = ProjectMember(
                project_id=project_id,
                version_id=version_id,
                user_id=user_id,
                role_type=role_type
            )
            members_to_add.append(member)
            added_user_roles.append((user_id, role_type))  # 记录成功添加的组合

        if not members_to_add:
            return [], failed_records

        # 批量添加成员
        try:
            db.session.bulk_save_objects(members_to_add)
            db.session.commit()

            # 修复：重新查询时考虑 role_type 字段
            if added_user_roles:
                # 构建查询条件：匹配所有成功添加的用户ID和角色类型组合
                conditions = []
                for user_id, role_type in added_user_roles:
                    condition = and_(
                        ProjectMember.user_id == user_id,
                        ProjectMember.role_type == role_type
                    )
                    if project_id:
                        condition = and_(condition, ProjectMember.project_id == project_id)
                    if version_id:
                        condition = and_(condition, ProjectMember.version_id == version_id)
                    conditions.append(condition)

                # 使用 OR 条件查询所有匹配的成员
                success_members = ProjectMember.query.filter(or_(*conditions)).all()
            else:
                success_members = []

        except IntegrityError as e:
            db.session.rollback()
            current_app.logger.error(f"批量创建成员时发生完整性错误: {str(e)}")
            raise ValueError("批量创建成员时发生数据库完整性错误")
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"批量创建成员时发生未知错误: {str(e)}")
            raise ValueError(f"批量创建成员失败: {str(e)}")

        return success_members, failed_records

    @staticmethod
    def delete_member(member_id: int) -> None:
        """根据成员ID删除成员"""
        member = ProjectMember.query.get(member_id)
        if not member:
            raise ValueError("成员不存在")
        db.session.delete(member)
        db.session.commit()

    @staticmethod
    def get_members_by_project(project_id: int) -> List[ProjectMember]:
        """获取项目的所有成员"""
        return ProjectMember.query.filter_by(project_id=project_id).all()

    @staticmethod
    def get_members_by_version(version_id: int) -> List[ProjectMember]:
        """获取版本的所有成员"""
        return ProjectMember.query.filter_by(version_id=version_id).all()

    @staticmethod
    def update_member_role(member_id: int, new_role: str) -> ProjectMember:
        """更新成员角色"""
        # 验证角色类型是否有效
        if new_role not in role_dict:
            raise ValueError(f"无效的角色类型: {new_role}")

        member = ProjectMember.query.get(member_id)
        if not member:
            raise ValueError("成员不存在")
        member.role_type = new_role
        db.session.commit()
        return member

    @staticmethod
    def find_member(project_id: Optional[int], version_id: Optional[int], user_id: int,
                    role_type: Optional[str] = None) -> Optional[ProjectMember]:
        """
        查找特定用户在某项目/版本中的角色

        Args:
            project_id: 项目ID
            version_id: 版本ID
            user_id: 用户ID
            role_type: 角色类型（可选），如果提供则按角色类型过滤

        Returns:
            ProjectMember对象或None
        """
        query = ProjectMember.query.filter_by(
            project_id=project_id,
            version_id=version_id,
            user_id=user_id
        )

        if role_type is not None:
            query = query.filter_by(role_type=role_type)

        return query.first()

    @staticmethod
    def find_members_by_role(project_id: Optional[int], version_id: Optional[int],
                             role_type: str) -> List[ProjectMember]:
        """
        查找项目/版本中具有特定角色的所有成员

        Args:
            project_id: 项目ID
            version_id: 版本ID
            role_type: 角色类型

        Returns:
            成员列表
        """
        return ProjectMember.query.filter_by(
            project_id=project_id,
            version_id=version_id,
            role_type=role_type
        ).all()

    @staticmethod
    def get_user_ids_by_role(project_id=None, version_id=None, role_type=None) -> List[int]:
        """
        根据 project_id 或 version_id 获取指定 role_type 的 user_id 列表

        Args:
            project_id (int, optional): 项目ID
            version_id (int, optional): 版本ID
            role_type (str): 角色类型

        Returns:
            list: user_id 列表
        """
        try:
            # 构建查询条件
            conditions = []

            if project_id is not None:
                conditions.append(ProjectMember.project_id == project_id)

            if version_id is not None:
                conditions.append(ProjectMember.version_id == version_id)

            # 必须指定至少一个ID和角色类型
            if not conditions or role_type is None:
                return []

            # 添加角色类型条件
            conditions.append(ProjectMember.role_type == role_type)

            # 执行查询
            members = ProjectMember.query.filter(*conditions).all()

            # 提取user_id列表
            user_ids = [member.user_id for member in members]
            return list(set(user_ids))  # 去重

        except Exception as e:
            current_app.logger.error(f"查询用户ID失败: {str(e)}")
            return []

    @staticmethod
    def get_member_list(page: int = 1, per_page: int = 20, **filters) -> Dict[str, Any]:
        """
        获取成员列表数据，支持分页和过滤
        即使ProjectMember中没有成员信息，也会构建完整的角色记录

        Args:
            page: 页码，从1开始
            per_page: 每页数量
            filters: 过滤条件，可包含：
                - type_filter: 类型过滤 ('product_line' 或 'tech_group')
                - entity_id: 项目ID或版本ID
                - role_type: 角色类型过滤
                - user_status: 用户状态
                - search_keyword: 搜索关键词（匹配名称、邮箱等）
                - defect_type: simplified2 或者为空

        Returns:
            包含分页信息和数据的字典
        """
        try:
            # 获取当前用户ID
            admin_user_id = g.admin_user_id
            current_app.logger.debug(f'get_member_list, 公司管理员ID: {admin_user_id}')
            # all_role_types = ['project_admin', 'project_viewer', 'dev_manager',
            #                   'test_manager', 'developer', 'tester']

            # 定义所有可能的角色类型
            defect_type = filters.get('defect_type', '')
            if defect_type == 'simplified2':
                all_role_types = ['project_admin', 'project_viewer']
            else:
                all_role_types = ['project_admin', 'project_viewer', 'dev_manager', 'test_manager']

            # 应用角色类型过滤
            role_type_filter = filters.get('role_type')
            if role_type_filter:
                if isinstance(role_type_filter, list):
                    valid_roles = [rt for rt in role_type_filter if rt in all_role_types]
                else:
                    valid_roles = [role_type_filter] if role_type_filter in all_role_types else []
            else:
                valid_roles = all_role_types

            # 获取搜索关键词
            search_keyword = filters.get('search_keyword', '')

            # 第一步：获取所有符合条件的实体（项目或版本）
            entities = []

            # 类型过滤
            type_filter = filters.get('type_filter', 'all')

            # 获取项目实体（tech_group）
            if type_filter in ['all', 'tech_group']:
                projects_query = Project.query.join(
                    Platform, Project.platform_id == Platform.id
                ).join(
                    TechGroup, Platform.tech_group_id == TechGroup.id
                ).filter(
                    TechGroup.user_id == admin_user_id
                )

                # 应用实体ID过滤
                entity_id = filters.get('entity_id')
                if entity_id:
                    projects_query = projects_query.filter(Project.id == entity_id)

                projects = projects_query.all()
                for project in projects:
                    entities.append({
                        'type': 'tech_group',
                        'entity_id': project.id,
                        'entity_obj': project
                    })

            # 获取版本实体（product_line）
            if type_filter in ['all', 'product_line']:
                versions_query = Version.query.join(
                    Product, Version.product_id == Product.id
                ).join(
                    ProductLine, Product.product_line_id == ProductLine.id
                ).filter(
                    ProductLine.user_id == admin_user_id
                )

                # 应用实体ID过滤
                entity_id = filters.get('entity_id')
                if entity_id:
                    versions_query = versions_query.filter(Version.id == entity_id)

                versions = versions_query.all()
                for version in versions:
                    entities.append({
                        'type': 'product_line',
                        'entity_id': version.id,
                        'entity_obj': version
                    })

            # 第二步：为每个实体生成所有角色类型的记录
            all_entity_role_combinations = []

            for entity in entities:
                for role_type in valid_roles:
                    all_entity_role_combinations.append({
                        'type': entity['type'],
                        'entity_id': entity['entity_id'],
                        'entity_obj': entity['entity_obj'],
                        'role_type': role_type
                    })

            # 第三步：应用搜索过滤（如果有搜索关键词）
            filtered_combinations = []

            if search_keyword:
                for combo in all_entity_role_combinations:
                    # 检查该实体-角色组合是否有匹配搜索关键词的成员
                    has_matching_members = ProjectMemberService._check_has_matching_members(
                        combo['type'],
                        combo['entity_id'],
                        combo['role_type'],
                        search_keyword,
                        filters.get('user_status')
                    )

                    if has_matching_members:
                        filtered_combinations.append(combo)
            else:
                filtered_combinations = all_entity_role_combinations

            # 第四步：构建返回数据（应用权限过滤）
            result_data = []
            for combo in filtered_combinations:
                member_data = ProjectMemberService._build_complete_member_data(
                    combo['type'],
                    combo['entity_id'],
                    combo['entity_obj'],
                    combo['role_type'],
                    search_keyword,
                    filters.get('user_status')
                )

                if member_data:  # 只添加有权限的数据
                    result_data.append(member_data)

            # 第五步：重新计算分页（基于权限过滤后的数据）
            total = len(result_data)
            total_pages = (total + per_page - 1) // per_page if total > 0 else 1

            # 获取当前页的数据
            start_index = (page - 1) * per_page
            end_index = start_index + per_page
            paginated_data = result_data[start_index:end_index]

            return {
                'data': paginated_data,
                'pagination': {
                    'page': page,
                    'per_page': per_page,
                    'total': total,
                    'pages': total_pages
                }
            }

        except Exception as e:
            current_app.logger.error(f"获取成员列表失败: {str(e)}")
            raise

    @staticmethod
    def _check_has_matching_members(entity_type: str, entity_id: int, role_type: str,
                                    search_keyword: str, user_status: Optional[int]) -> bool:
        """
        检查实体-角色组合是否有匹配搜索关键词的成员

        Args:
            entity_type: 实体类型
            entity_id: 实体ID
            role_type: 角色类型
            search_keyword: 搜索关键词
            user_status: 用户状态过滤

        Returns:
            bool: 是否有匹配的成员
        """
        try:
            # 构建查询条件
            if entity_type == 'tech_group':
                query_condition = and_(
                    ProjectMember.project_id == entity_id,
                    ProjectMember.role_type == role_type
                )
            else:
                query_condition = and_(
                    ProjectMember.version_id == entity_id,
                    ProjectMember.role_type == role_type
                )

            # 查询成员
            members_query = ProjectMember.query.filter(query_condition)

            # 应用用户过滤
            members_query = ProjectMemberService._apply_user_filters(members_query, {
                'search_keyword': search_keyword,
                'user_status': user_status
            })

            # 检查是否有成员
            return members_query.count() > 0

        except Exception as e:
            current_app.logger.error(f"检查匹配成员失败: {str(e)}")
            return False

    @staticmethod
    def _build_complete_member_data(entity_type: str, entity_id: int, entity_obj: Any,
                                    role_type: str, search_keyword: str = '',
                                    user_status: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """
        构建完整的成员数据，即使没有成员信息也会返回基本结构

        Args:
            entity_type: 实体类型
            entity_id: 实体ID
            entity_obj: 实体对象
            role_type: 角色类型
            search_keyword: 搜索关键词
            user_status: 用户状态过滤

        Returns:
            成员数据字典
        """
        try:
            # 构建路径名称
            path_name = ProjectMemberService._get_entity_path_name(entity_type, entity_obj)

            # 获取该角色下的成员
            if entity_type == 'tech_group':
                query_condition = and_(
                    ProjectMember.project_id == entity_id,
                    ProjectMember.role_type == role_type
                )
            else:
                query_condition = and_(
                    ProjectMember.version_id == entity_id,
                    ProjectMember.role_type == role_type
                )

            members_query = ProjectMember.query.filter(query_condition)

            # 应用用户过滤
            if search_keyword or user_status is not None:
                members_query = ProjectMemberService._apply_user_filters(members_query, {
                    'search_keyword': search_keyword,
                    'user_status': user_status
                })

            members = members_query.all()

            # 构建用户列表
            users_list = []
            for member in members:
                if member.user and member.user.is_delete == 0:
                    users_list.append({
                        'member_id': member.id,
                        'user_id': member.user.user_id,
                        'real_name': member.user.real_name or '未设置',
                        'email': member.user.email or '未设置',
                        'mobile': member.user.mobile or '未设置',
                        'company_name': member.user.company_name or '未设置',
                        'status': member.user.status,
                        'status_text': '已加入' if member.user.status == 1 else '未加入'
                    })

            # 获取项目管理员用户ID列表
            project_admin_user_ids = ProjectMemberService.get_project_admin_user_ids(
                entity_type, entity_id
            )
            # 只获取 当前用户作为项目管理员的 数据（项目管理员才有权限管理项目成员）
            if g.user_id not in project_admin_user_ids:
                return None

            return {
                'type': entity_type,
                'entity_id': entity_id,
                'path_name': path_name,
                'role_type': role_type,
                'role_name': ProjectMemberService._get_role_name(role_type),
                'users': users_list,
                'user_count': len(users_list),
                'project_admin_user_ids': project_admin_user_ids
            }

        except Exception as e:
            current_app.logger.error(f"构建完整成员数据失败: {str(e)}")
            return None

    @staticmethod
    def _get_entity_path_name(entity_type: str, entity_obj: Any) -> str:
        """
        获取实体的完整路径名称

        Args:
            entity_type: 实体类型
            entity_obj: 实体对象

        Returns:
            路径名称字符串
        """
        try:
            if entity_type == 'tech_group':
                # 项目类型：技术族-平台-项目
                project = entity_obj
                if project and project.platform and project.platform.tech_group:
                    return f"{project.platform.tech_group.name}-{project.platform.name}-{project.name}"
                elif project:
                    return project.name or f"项目({project.id})"
                else:
                    return "未知项目"
            else:
                # 版本类型：产品线-产品-版本
                version = entity_obj
                if version and version.product and version.product.product_line:
                    return f"{version.product.product_line.name}-{version.product.name}-{version.version_number}"
                elif version:
                    return version.version_number or f"版本({version.id})"
                else:
                    return "未知版本"

        except Exception as e:
            current_app.logger.error(f"获取实体路径名称失败: {str(e)}")
            return "未知路径"

    @staticmethod
    def get_project_admin_user_ids(entity_type: str, entity_id: int) -> List[int]:
        """
        获取对应项目或版本的 project_admin 用户ID列表

        Args:
            entity_type: 实体类型 ('tech_group' 或 'product_line')
            entity_id: 实体ID（项目ID或版本ID）

        Returns:
            List[int]: project_admin 用户的ID列表
        """
        try:
            if entity_type == 'tech_group':
                # 项目类型：查询该项目的 project_admin
                project_admin_members = ProjectMember.query.filter_by(
                    project_id=entity_id,
                    role_type='project_admin'
                ).all()
            else:
                # 版本类型：查询该版本的 project_admin
                project_admin_members = ProjectMember.query.filter_by(
                    version_id=entity_id,
                    role_type='project_admin'
                ).all()

            # 提取用户ID列表
            project_admin_user_ids = []
            for member in project_admin_members:
                if member.user and member.user.is_delete == 0:
                    project_admin_user_ids.append(member.user.user_id)

            return project_admin_user_ids

        except Exception as e:
            current_app.logger.error(f"获取 project_admin 用户ID列表失败: {str(e)}")
            return []

    @staticmethod
    def _build_member_data(member: ProjectMember) -> Optional[Dict[str, Any]]:
        """构建单个成员的数据"""
        if not member.user:
            return None

        # 确定类型和路径信息
        member_type, path_name, entity_id = ProjectMemberService._get_entity_info(member)

        if not member_type:
            return None

        # 获取该角色下的所有用户（相同项目/版本、相同角色）
        same_role_members = ProjectMemberService._get_same_role_members(
            member.project_id, member.version_id, member.role_type
        )

        # 构建用户列表
        users_list = []
        for same_member in same_role_members:
            if same_member.user and same_member.user.is_delete == 0:
                users_list.append({
                    'member_id': same_member.id,  # 添加 project_members.id
                    'user_id': same_member.user.user_id,
                    'real_name': same_member.user.real_name or '未设置',
                    'email': same_member.user.email or '未设置',
                    'mobile': same_member.user.mobile or '未设置',
                    'company_name': same_member.user.company_name or '未设置',
                    'status': same_member.user.status,
                    'status_text': '已加入' if same_member.user.status == 1 else '未加入'
                })

        # 新增：获取对应项目或版本的 project_admin 用户ID列表
        project_admin_user_ids = ProjectMemberService.get_project_admin_user_ids(
            member_type, entity_id
        )

        return {
            'type': member_type,
            'entity_id': entity_id,
            'path_name': path_name,
            'role_type': member.role_type,
            'role_name': ProjectMemberService._get_role_name(member.role_type),
            'users': users_list,
            'user_count': len(users_list),
            'project_admin_user_ids': project_admin_user_ids  # 新增字段
        }

    @staticmethod
    def _apply_entity_filters(query, filters: Dict[str, Any]):
        """应用实体级别的过滤条件"""
        # 类型过滤
        type_filter = filters.get('type_filter')
        if type_filter == 'product_line':
            query = query.filter(ProjectMember.version_id.isnot(None))
        elif type_filter == 'tech_group':
            query = query.filter(ProjectMember.project_id.isnot(None))

        # 实体ID过滤
        entity_id = filters.get('entity_id')
        if entity_id:
            query = query.filter(
                or_(
                    ProjectMember.project_id == entity_id,
                    ProjectMember.version_id == entity_id
                )
            )

        return query

    @staticmethod
    def _apply_user_filters(query, filters: Dict[str, Any]):
        """应用用户级别的过滤条件"""
        # 修复：显式指定 User 表的连接条件，避免歧义
        query = query.join(User, ProjectMember.user_id == User.user_id)

        # 用户状态过滤
        user_status = filters.get('user_status')
        if user_status is not None:
            query = query.filter(User.status == user_status)

        # 搜索关键词过滤
        search_keyword = filters.get('search_keyword')
        if search_keyword:
            query = query.filter(
                or_(
                    User.real_name.ilike(f'%{search_keyword}%'),
                    User.email.ilike(f'%{search_keyword}%'),
                    User.mobile.ilike(f'%{search_keyword}%')
                )
            )

        # 始终排除已删除的用户
        query = query.filter(User.is_delete == 0)

        return query


    @staticmethod
    def _get_entity_info(member: ProjectMember) -> tuple:
        """获取实体类型和路径信息"""

        if member.project_id and member.project:
            # 技术族-平台-项目路径
            project = member.project
            platform = project.platform
            tech_group = platform.tech_group if platform else None

            if tech_group and platform:
                path_name = f"{tech_group.name}-{platform.name}-{project.name}"
                return 'tech_group', path_name, member.project_id

        elif member.version_id and member.version:
            # 产品线-产品-版本路径
            version = member.version
            product = version.product
            product_line = product.product_line if product else None

            if product_line and product:
                path_name = f"{product_line.name}-{product.name}-{version.version_number}"
                return 'product_line', path_name, member.version_id

        return None, '未知路径', None

    @staticmethod
    def _get_same_role_members(project_id: Optional[int], version_id: Optional[int],
                               role_type: str) -> List[ProjectMember]:
        """获取相同项目/版本、相同角色的所有成员"""

        query = ProjectMember.query.filter_by(
            project_id=project_id,
            version_id=version_id,
            role_type=role_type
        ).join(User, ProjectMember.user_id == User.user_id).filter(User.is_delete == 0)

        # 预先加载用户关系以提高性能
        query = query.options(db.joinedload(ProjectMember.user))

        return query.all()

    @staticmethod
    def _get_role_name(role_type: str) -> str:
        """获取角色名称"""
        return role_dict.get(role_type, role_type)

    @staticmethod
    def get_member_summary() -> Dict[str, Any]:
        """获取成员统计摘要"""
        try:
            # 使用子查询避免重复连接
            from sqlalchemy import distinct

            # 按类型统计（去重计数）
            tech_group_count = db.session.query(
                distinct(ProjectMember.project_id)
            ).filter(
                ProjectMember.project_id.isnot(None)
            ).count()

            product_line_count = db.session.query(
                distinct(ProjectMember.version_id)
            ).filter(
                ProjectMember.version_id.isnot(None)
            ).count()

            # 按角色统计用户数（连接一次user表）
            role_stats = db.session.query(
                ProjectMember.role_type,
                db.func.count(distinct(ProjectMember.user_id))
            ).join(User, ProjectMember.user_id == User.user_id).filter(User.is_delete == 0).group_by(
                ProjectMember.role_type).all()

            # 构建角色统计字典
            role_stats_dict = {}
            for role_type, count in role_stats:
                role_stats_dict[role_type] = count

            return {
                'tech_group_count': tech_group_count,
                'product_line_count': product_line_count,
                'role_stats': role_stats_dict
            }
        except Exception as e:
            current_app.logger.error(f"获取成员统计摘要失败: {str(e)}")
            raise

    @staticmethod
    def get_user_related_ids_for_global(admin_user_id: int):
        """
        company_admin 、 global_admin 和 global_viewer 角色, 根据 admin_user_id 获取用户关联的本公司所有project_id和version_id
        Args:
            admin_user_id: 手机账号用户ID

        Returns:
            Dict: 包含 project_ids 和 version_ids 的字典
        """
        try:
            # 使用子查询或连接查询一次性获取所有数据
            # 获取项目ID
            project_query = db.session.query(Project.id). \
                join(Platform, Project.platform_id == Platform.id). \
                join(TechGroup, Platform.tech_group_id == TechGroup.id). \
                filter(TechGroup.user_id == admin_user_id)

            project_ids = [row[0] for row in project_query.all()]

            # 获取版本ID
            version_query = db.session.query(Version.id). \
                join(Product, Version.product_id == Product.id). \
                join(ProductLine, Product.product_line_id == ProductLine.id). \
                filter(ProductLine.user_id == admin_user_id)

            version_ids = [row[0] for row in version_query.all()]

            return {
                'project_ids': project_ids,
                'version_ids': version_ids,
            }

        except Exception as e:
            current_app.logger.error(f"获取用户关联ID失败: {str(e)}")
            return {'project_ids': [], 'version_ids': []}

    @staticmethod
    def get_related_entities_by_user_id(user_id: int) -> Dict[str, List[int]]:
        """
        - 全局用户 company_admin 、 global_admin 和 global_viewer 角色不会配置到 project_members 表中，只配置到 user_roles表，
        因此需要通过 tech_groups、product_lines 来获取 project_id 列表和 version_id 列表。

        - 非全局用户 根据 user_id 获取其关联的所有 project_id 列表和 version_id 列表,

        Args:
            user_id: 用户ID

        Returns:
            Dict: 包含 project_ids 和 version_ids 的字典
        """
        # 全局用户获取本公司 project_id 列表和 version_id 列表
        # success, user_info = UserRoleService.get_user_roles_info(g.user_id)
        # if not success:
        #     current_app.logger.error('获取全局角色失败')
        # elif success:
        #     if g.is_company_admin  or g.is_global_admin or g.is_global_viewer:
        #         return ProjectMemberService.get_user_related_ids_for_global(g.admin_user_id)
        print(f"role_select:{session['role_select']}")
        if session['role_select'] == "全板块查阅人" or session['role_select'] == "全板块管理员" or session['role_select'] =='流程使用者':
            return ProjectMemberService.get_user_related_ids_for_global(g.admin_user_id)

        # 非全局用户 根据 user_id 获取其关联的所有 project_id 列表和 version_id 列表
        try:
            print(f"user_id:{user_id}")
            # 查询该用户的所有项目成员记录
            members = ProjectMember.query.filter(and_(ProjectMember.user_id==user_id,ProjectMember.role_type=='project_viewer')).all()

            # 提取所有非空的 project_id 和 version_id
            project_ids = []
            version_ids = []

            for member in members:
                if member.project_id is not None:
                    project_ids.append(member.project_id)
                if member.version_id is not None:
                    version_ids.append(member.version_id)

            # 去重并排序
            project_ids = sorted(list(set(project_ids)))
            version_ids = sorted(list(set(version_ids)))

            return {
                'project_ids': project_ids,
                'version_ids': version_ids
            }

        except Exception as e:
            current_app.logger.error(f"获取用户 {user_id} 关联实体失败: {str(e)}")
            return {'project_ids': [], 'version_ids': []}

    @staticmethod
    def get_user_menu_project_versions(user_id):
        menu_roles  = ProjectMemberService.get_show_user_roles(user_id)
        # if "全板块查阅人" in menu_roles or "全板块管理员" in menu_roles:
        #     return ProjectMemberService.get_user_related_ids_for_global(g.admin_user_id)
        try:
            # 查询该用户的所有项目成员记录
            #members = ProjectMember.query.filter(and_(ProjectMember.user_id==user_id,ProjectMember.role_type.in_(['project_viewer']))).all()
            query = ProjectMember.query.filter(and_(ProjectMember.user_id==user_id,ProjectMember.role_type.in_(['project_viewer'])))
            members = query.all()
            sql = query.statement.compile(compile_kwargs={"literal_binds": True})
            current_app.logger.info(f"树最终SQL查询: {sql}")

            project_ids = []
            version_ids = []
            for member in members:
                if member.project_id is not None:
                    project_ids.append(member.project_id)
                if member.version_id is not None:
                    version_ids.append(member.version_id)
            return {
                'project_ids': sorted(list(set(project_ids))),
                'version_ids': sorted(list(set(version_ids)))
            }
        except Exception as e:
            return {'project_ids': [], 'version_ids': []}

    @staticmethod
    def get_show_user_roles(user_id) -> list[str]:
        menu_user_roles = ["公司管理员", "全板块管理员", "全板块查阅人", "项目管理员", "项目查阅人", "流程使用者"]
        _, res = UserRoleService.get_user_roles_by_user_id(user_id)
        print(f"menu_user_roles_res:{res}")
        user_roles = res['data']
        show_user_roles = []
        for role in user_roles:
            if role['role_description'] in menu_user_roles:
                show_user_roles.append(role['role_description'])
        if "公司管理员" in show_user_roles:
            show_user_roles = ['公司管理员']
        else:
            show_user_roles.append("流程使用者")
        order_dict = {elem: idx for idx, elem in enumerate(menu_user_roles)}
        show_user_roles = sorted(show_user_roles, key=lambda x: order_dict[x])
        return show_user_roles


class ProjectMemberAuthService:
    """项目成员权限验证服务"""

    @staticmethod
    def get_entity_name(project_id: Optional[int], version_id: Optional[int]) -> str:
        """
        获取项目/版本的名称

        Args:
            project_id: 项目ID
            version_id: 版本ID

        Returns:
            str: 实体名称
        """
        try:
            if project_id:
                # 查询项目信息
                project = Project.query.get(project_id)
                if project and project.platform and project.platform.tech_group:
                    return f"{project.platform.tech_group.name}-{project.platform.name}-{project.name}"
                elif project:
                    return project.name or f"项目({project_id})"
                else:
                    return f"项目({project_id})"

            elif version_id:
                # 查询版本信息
                version = Version.query.get(version_id)
                if version and version.product and version.product.product_line:
                    return f"{version.product.product_line.name}-{version.product.name}-{version.version_number}"
                elif version:
                    return version.version_number or f"版本({version_id})"
                else:
                    return f"版本({version_id})"

            return "未知实体"

        except Exception as e:
            current_app.logger.error(f"获取实体名称失败: {str(e)}")
            entity_type = "项目" if project_id else "版本"
            entity_id = project_id if project_id else version_id
            return f"{entity_type}({entity_id})"

    @staticmethod
    def check_project_admin_access(project_id: Optional[int], version_id: Optional[int]) -> bool:
        """
        检查当前用户是否有项目/版本的管理员权限

        Args:
            project_id: 项目ID
            version_id: 版本ID

        Returns:
            bool: 是否有权限
        """
        try:
            # 公司管理员和全局管理员有所有权限 ——Since 2025-10-20: 只有项目管理员才能进行项目成员管理
            # if getattr(g, 'is_company_admin', False):
            #     return True
            # if getattr(g, 'is_global_admin', False):
            #     return True

            current_user_id = getattr(g, 'user_id', None)
            if not current_user_id:
                return False

            # 检查是否是项目/版本的 project_admin
            if project_id:
                # 检查项目管理员权限
                admin_member = ProjectMemberService.find_member(
                    project_id=project_id,
                    version_id=None,
                    user_id=current_user_id,
                    role_type='project_admin'
                )
                return admin_member is not None

            elif version_id:
                # 检查版本管理员权限
                admin_member = ProjectMemberService.find_member(
                    project_id=None,
                    version_id=version_id,
                    user_id=current_user_id,
                    role_type='project_admin'
                )
                return admin_member is not None

            return False

        except Exception as e:
            current_app.logger.error(f"权限检查失败: {str(e)}")
            return False

    @staticmethod
    def require_project_admin_access(project_id: Optional[int], version_id: Optional[int]) -> None:
        """
        要求项目/版本管理员权限，如果没有权限则抛出异常

        Args:
            project_id: 项目ID
            version_id: 版本ID

        Raises:
            ValueError: 没有权限时抛出
        """
        if not ProjectMemberAuthService.check_project_admin_access(project_id, version_id):
            # 获取实体名称
            entity_name = ProjectMemberAuthService.get_entity_name(project_id, version_id)
            entity_type = "项目" if project_id else "版本"
            entity_id = project_id if project_id else version_id

            raise ValueError(f"没有{entity_type}『{entity_name}』(ID:{entity_id})的管理员权限")


    @staticmethod
    def check_user_project_admin(user_id):
        project_admin_member = ProjectMember.query.filter(and_(ProjectMember.user_id==user_id,ProjectMember.role_type=='project_admin')).first()
        return project_admin_member

    def require_project_admin(f):
        """
        装饰器：要求用户是项目/版本的管理员
        """

        @wraps(f)
        def decorated_function(*args, **kwargs):
            try:
                UserRoleService.get_user_roles_info(g.user_id)  # 检查用户是否为 全板块管理员
                # 对于不同的请求方法，获取项目/版本ID的方式不同
                if request.method in ['POST', 'PUT']:
                    # POST/PUT 请求从请求体中获取
                    data = request.get_json() or {}
                    project_id = data.get('project_id')
                    version_id = data.get('version_id')
                else:
                    # GET/DELETE 请求从查询参数或URL参数中获取
                    project_id = request.args.get('project_id', type=int)
                    version_id = request.args.get('version_id', type=int)

                # 检查权限
                ProjectMemberAuthService.require_project_admin_access(project_id, version_id)

                return f(*args, **kwargs)

            except ValueError as e:
                return jsonify({'code': 403, 'message': str(e)}), 403
            except Exception as e:
                current_app.logger.error(f"权限验证失败: {str(e)}")
                return jsonify({'code': 500, 'message': '权限验证失败'}), 500

        return decorated_function

