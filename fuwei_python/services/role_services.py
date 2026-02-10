from functools import wraps
from http.client import HTTPException

from flask import request, jsonify, current_app, flash, render_template, g
from sqlalchemy.exc import SQLAlchemyError
from conf.db import db
from models.project_member.model import ProjectMember, role_dict
from models.role.model import UserRole, Role
from datetime import datetime
from typing import List, Optional, Dict, Union, Tuple, Any

from models.users.models import User, EmailUserRight


class RoleService:
    """角色服务类"""

    @staticmethod
    def get_all_roles() -> List[Role]:
        """获取所有角色"""
        try:
            return Role.query.all()
        except SQLAlchemyError as e:
            db.session.rollback()
            raise Exception(f"获取角色列表失败: {str(e)}")

    @staticmethod
    def get_role_by_id(role_id: int) -> Optional[Role]:
        """根据ID获取角色"""
        try:
            return Role.query.filter_by(id=role_id).first()
        except SQLAlchemyError as e:
            db.session.rollback()
            raise Exception(f"获取角色失败: {str(e)}")

    @staticmethod
    def get_role_by_name(name: str) -> Optional[Role]:
        """根据名称获取角色"""
        try:
            return Role.query.filter_by(name=name).first()
        except SQLAlchemyError as e:
            db.session.rollback()
            raise Exception(f"获取角色失败: {str(e)}")

    @staticmethod
    def create_role(name: str, description: str = None, create_user_id: int = 1) -> Role:
        """创建新角色"""
        try:
            # 检查角色名是否已存在
            if RoleService.get_role_by_name(name):
                raise Exception(f"角色名称 '{name}' 已存在")

            role = Role(
                name=name,
                description=description,
                create_user_id=create_user_id,
                create_time=datetime.now()
            )

            db.session.add(role)
            db.session.commit()
            return role
        except SQLAlchemyError as e:
            db.session.rollback()
            raise Exception(f"创建角色失败: {str(e)}")

    @staticmethod
    def update_role(role_id: int, name: str = None, description: str = None) -> Optional[Role]:
        """更新角色信息"""
        try:
            role = RoleService.get_role_by_id(role_id)
            if not role:
                return None

            if name and name != role.name:
                # 检查新名称是否已被其他角色使用
                existing_role = RoleService.get_role_by_name(name)
                if existing_role and existing_role.id != role_id:
                    raise Exception(f"角色名称 '{name}' 已被使用")
                role.name = name

            if description is not None:
                role.description = description

            db.session.commit()
            return role
        except SQLAlchemyError as e:
            db.session.rollback()
            raise Exception(f"更新角色失败: {str(e)}")

    @staticmethod
    def delete_role(role_id: int) -> bool:
        """删除角色"""
        try:
            role = RoleService.get_role_by_id(role_id)
            if not role:
                return False

            # 删除前检查是否有用户关联此角色
            user_roles = UserRoleService.get_user_roles_by_role_id(role_id)
            if user_roles:
                raise Exception("无法删除角色，仍有用户关联此角色")

            db.session.delete(role)
            db.session.commit()
            return True
        except SQLAlchemyError as e:
            db.session.rollback()
            raise Exception(f"删除角色失败: {str(e)}")


class UserRoleService:
    """用户角色关联服务类"""

    @staticmethod
    def get_all_user_roles() -> List[UserRole]:
        """获取所有用户角色关联"""
        try:
            return UserRole.query.all()
        except SQLAlchemyError as e:
            db.session.rollback()
            raise Exception(f"获取用户角色关联列表失败: {str(e)}")

    @staticmethod
    def get_user_roles_by_user_id(user_id: int) -> Tuple[bool, Dict[str, Any]]:
        """
        根据用户ID获取用户的角色列表

        参数:
            user_id (int): 用户ID

        返回:
            tuple: (success, result)
            - success: bool, 操作是否成功
            - result: dict, 成功时包含数据，失败时包含错误信息
        """
        try:
            # 参数验证
            if not user_id or not isinstance(user_id, int) or user_id <= 0:
                return False, {
                    'message': '无效的用户ID',
                    'error_code': 'INVALID_USER_ID',
                    'data': [],
                    'count': 0
                }

            # 执行联合查询获取用户角色信息
            results = db.session.query(
                UserRole.user_id,
                UserRole.role_id,
                Role.name,
                Role.description
            ).join(
                Role, UserRole.role_id == Role.id
            ).filter(
                UserRole.user_id == user_id
            ).all()

            # 将查询结果转换为字典列表
            roles_list = [{
                'user_id': result.user_id,
                'role_id': result.role_id,
                'role_name': result.name,
                'role_description': result.description
            } for result in results]
            # 从 project_members 表获取项目角色
            project_roles = UserRoleService.get_user_project_roles(user_id)
            project_roles_list = []

            for project_role in project_roles:
                a_role_obj = RoleService.get_role_by_name(project_role)
                if a_role_obj:
                    project_roles_list.append({
                        'user_id': user_id,
                        'role_id': a_role_obj.id,
                        'role_name': project_role,
                        'role_description': a_role_obj.description
                    })
            merged_list = [*roles_list, *project_roles_list]

            return True, {
                'data': merged_list,
                'count': len(merged_list),
                'message': '获取成功',
                'error_code': ''
            }

        except HTTPException:
            # 重新抛出HTTP异常，让Flask处理
            raise
        except Exception as e:
            current_app.logger.error(f"获取用户角色失败: {str(e)}", exc_info=True)
            return False, {
                'message': f'获取用户角色失败: {str(e)}',
                'error_code': 'USER_ROLE_QUERY_ERROR',
                'data': [],
                'count': 0
            }

    @staticmethod
    def get_user_ids_by_role(role_id: int) -> List[int]:
        """
        根据角色ID获取所有关联的用户ID列表

        Args:
            role_id: 角色ID

        Returns:
            用户ID列表，如果没有找到任何用户则返回空列表
        """
        try:
            # 查询所有具有该角色ID的用户角色关系
            user_roles = UserRole.query.filter_by(role_id=role_id).all()

            # 提取用户ID并返回列表
            user_ids = [ur.user_id for ur in user_roles]
            return user_ids

        except Exception as e:
            # 记录错误日志（实际项目中应该使用日志记录器）
            current_app.logger.error(f"Error fetching user IDs for role {role_id}: {str(e)}")
            return []

    @staticmethod
    def get_user_roles_by_role_id(role_id: int) -> List[UserRole]:
        """根据角色ID获取用户关联"""
        try:
            return UserRole.query.filter_by(role_id=role_id).all()
        except SQLAlchemyError as e:
            db.session.rollback()
            raise Exception(f"获取用户角色关联失败: {str(e)}")

    @staticmethod
    def get_user_role(user_id: int, role_id: int) -> Optional[UserRole]:
        """获取特定用户角色关联"""
        try:
            return UserRole.query.filter_by(user_id=user_id, role_id=role_id).first()
        except SQLAlchemyError as e:
            db.session.rollback()
            raise Exception(f"获取用户角色关联失败: {str(e)}")

    @staticmethod
    def assign_role_to_user(user_id: int, role_id: int, notes: str) -> UserRole:
        """为用户分配角色"""
        try:
            # 检查关联是否已存在
            existing_assignment = UserRoleService.get_user_role(user_id, role_id)
            if existing_assignment:
                return existing_assignment

            user_role = UserRole(
                user_id=user_id,
                role_id=role_id,
                notes=notes,
                created_time=datetime.now()
            )

            db.session.add(user_role)
            db.session.commit()
            return user_role
        except SQLAlchemyError as e:
            db.session.rollback()
            raise Exception(f"分配角色失败: {str(e)}")

    @staticmethod
    def remove_role_from_user(user_id: int, role_id: int) -> bool:
        """移除用户的角色"""
        try:
            user_role = UserRoleService.get_user_role(user_id, role_id)
            if not user_role:
                return False

            db.session.delete(user_role)
            db.session.commit()
            return True
        except SQLAlchemyError as e:
            db.session.rollback()
            raise Exception(f"移除角色失败: {str(e)}")

    @staticmethod
    def update_user_roles(user_id: int, role_ids: List[int]) -> Tuple[
        bool, Union[List[Dict[str, Any]], Dict[str, str]]]:
        """更新用户的角色列表（全量替换）"""
        try:
            # 获取当前角色
            success, current_roles_result = UserRoleService.get_user_roles_by_user_id(user_id)
            if not success:
                return False, current_roles_result

            current_roles_data = current_roles_result.get('data', [])
            current_role_ids = [role['role_id'] for role in current_roles_data]

            # 找出需要删除的角色
            roles_to_remove = set(current_role_ids) - set(role_ids)
            for role_id in roles_to_remove:
                remove_success, remove_result = UserRoleService.remove_role_from_user(user_id, role_id)
                if not remove_success:
                    return False, remove_result

            # 找出需要添加的角色
            roles_to_add = set(role_ids) - set(current_role_ids)
            for role_id in roles_to_add:
                add_success, add_result = UserRoleService.assign_role_to_user(user_id, role_id)
                if not add_success:
                    return False, add_result

            # 返回更新后的角色列表
            return UserRoleService.get_user_roles_by_user_id(user_id)
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"更新用户角色失败: {str(e)}", exc_info=True)
            return False, {
                'message': f'更新用户角色失败: {str(e)}',
                'error_code': 'USER_ROLE_UPDATE_ERROR'
            }

    @staticmethod
    def get_company_global_viewer_users(user_id: int) -> List[Dict[str, Union[int, str, None]]]:
        """
        根据用户 id 获取本公司  global_viewer 用户列表
        """
        company_user_list = User.get_company_users_by_user_id(user_id)
        # 获取 global_viewer 3 用户id列表
        global_viewer_user_ids = UserRoleService.get_user_ids_by_role(3)
        # 将 global_viewer 用户ID转换为集合以提高查找效率
        global_viewer_set = set(global_viewer_user_ids)
        # 筛选出本公司中具有 global_viewer 角色的用户
        company_global_viewer_users = [
            user for user in company_user_list
            if user['user_id'] in global_viewer_set  # 修改这里
        ]
        return company_global_viewer_users

    @staticmethod
    def get_company_global_admin_users(user_id: int) -> List[Dict[str, Union[int, str, None]]]:
        """
        根据用户 id 获取本公司  global_admin 用户列表 （一般只有1人）
        """
        company_user_list = User.get_company_users_by_user_id(user_id)
        # 获取 global_admin 2 用户id列表
        global_admin_user_ids = UserRoleService.get_user_ids_by_role(2)
        # 将 global_admin 用户ID转换为集合以提高查找效率
        global_admin_set = set(global_admin_user_ids)
        # 筛选出本公司中具有 global_admin 角色的用户
        company_global_admin_users = [
            user for user in company_user_list
            if user['user_id'] in global_admin_set  # 修改这里
        ]
        current_app.logger.debug(f'len(company_global_admin_users): {len(company_global_admin_users)}')
        return company_global_admin_users

    @staticmethod
    def check_global_roles(allowed_roles=None, template=None, json_response=False):
        """
        检查用户是否具有全局角色的装饰器（支持HTML和JSON响应）

        Args:
            allowed_roles: 允许的角色列表，默认为 ['global_admin', 'global_viewer']
            template: HTML错误时渲染的模板路径
            json_response: 是否返回JSON格式响应（针对API请求）

        Returns:
            装饰器函数
        """
        if allowed_roles is None:
            allowed_roles = ['global_admin', 'global_viewer']

        def decorator(f):
            @wraps(f)
            def decorated_function(*args, **kwargs):
                current_app.logger.debug('..................')
                try:
                    # 如果允许所有角色访问，则直接通过
                    if allowed_roles == ['all']:
                        current_app.logger.debug('允许所有角色访问，跳过权限检查')
                        return f(*args, **kwargs)
                    if  g.user_id != g.admin_user_id:  # 手机用户登录（公司管理员）则无需判断
                        item = EmailUserRight.get_one(g.user_id)
                        if not item or not getattr(item, 'type_0', None):
                            return UserRoleService._handle_error(
                                "你没有注册IT缺陷流管理的权限，请联系公司管理员邀请加入。",
                                template,
                                json_response,
                                403
                            )
                    # 初始化用户权限标志
                    g.is_company_admin = False
                    g.is_global_admin = False
                    g.is_global_viewer = False

                    current_app.logger.debug(f'user_id: {g.user_id}')
                    # 获取用户全局角色信息
                    success, user_info = UserRoleService.get_user_roles_info(g.user_id)

                    if not success:
                        return UserRoleService._handle_error(
                            user_info.get('message', '获取用户角色失败'),
                            template,
                            json_response,
                            500
                        )

                    user_roles = user_info['roles']
                    current_app.logger.debug(f'用户全局角色: {user_roles}')

                    # 从 project_members 表获取项目角色
                    project_roles = UserRoleService.get_user_project_roles(g.user_id)
                    current_app.logger.debug(f'用户项目角色: {project_roles}')

                    # 合并所有角色
                    all_user_roles = list(set(user_roles + project_roles))
                    current_app.logger.debug(f'用户所有角色: {all_user_roles}')

                    role_chinese_names = [role_dict[role] for role in allowed_roles if role in role_dict]
                    chinese_names_str = '、'.join(role_chinese_names)
                    addition_str = f'所需权限：{chinese_names_str}。'
                    current_app.logger.info(addition_str)
                    # 检查权限
                    message = f'权限不足，无法访问此页面。{addition_str}'
                    if json_response:
                        message = f'权限不足，禁止调用此接口。{addition_str}'

                    if not UserRoleService._has_required_roles(all_user_roles, allowed_roles):
                        return UserRoleService._handle_error(
                            message,
                            template,
                            json_response,
                            403
                        )

                    current_app.logger.info(addition_str)
                    return f(*args, **kwargs)

                except Exception as e:
                    current_app.logger.error(f"权限检查异常: {str(e)}")
                    return UserRoleService._handle_error(
                        '系统错误，请稍后重试',
                        template,
                        json_response,
                        500
                    )

            return decorated_function

        return decorator

    @staticmethod
    def get_user_roles_info(user_id):
        """获取用户角色信息，并设置全局角色标志"""
        try:
            # 检查是否为公司管理员
            g.is_company_admin = (user_id == g.admin_user_id)

            # 如果是公司管理员，自动分配角色
            if g.is_company_admin:
                user_role = UserRoleService.assign_role_to_user(
                    user_id, 1, '手机号登录用户自动设置为公司管理员'
                )
                if user_role:
                    current_app.logger.debug('手机账号登录用户已设置为公司管理员')

            # 获取用户角色
            success, result = UserRoleService.get_user_roles_by_user_id(user_id)
            if not success:
                return False, {'message': result.get('message', '获取用户角色失败')}

            user_roles = [role['role_name'] for role in result['data']]

            # 设置全局角色标志
            g.is_global_admin = 'global_admin' in user_roles
            g.is_global_viewer = 'global_viewer' in user_roles

            return True, {'roles': user_roles}

        except Exception as e:
            current_app.logger.error(f"获取用户角色信息失败: {str(e)}")
            return False, {'message': '获取用户角色信息失败'}

    @staticmethod
    def get_user_project_roles(user_id):
        """
        从 project_members 表获取用户的项目角色

        Args:
            user_id: 用户ID

        Returns:
            list: 用户在所有项目中的角色列表
        """
        try:
            # 查询用户在 project_members 表中的所有角色
            project_members = ProjectMember.query.filter_by(
                user_id=user_id
            ).all()

            # 提取所有不重复的角色类型
            project_roles = list(set([member.role_type for member in project_members if member.role_type]))
            return project_roles

        except Exception as e:
            current_app.logger.error(f"获取用户项目角色失败: {str(e)}")
            return []

    @staticmethod
    def _has_required_roles(user_roles, allowed_roles):
        """检查用户是否具有所需角色"""
        return any(role in allowed_roles for role in user_roles)

    @staticmethod
    def _handle_error(message, template, json_response, status_code):
        """统一错误处理"""
        current_app.logger.error(f"权限检查失败: {message}  user_id: {g.user_id}")
        # 如果指定了模板，始终使用模板渲染（适用于页面访问）
        if template:
            # flash(message, 'error')
            return render_template(template, error_message=message), status_code

        if json_response or request.is_json or request.accept_mimetypes.accept_json:
            return jsonify({
                'success': False,
                'message': message,
                'error_code': status_code
            }), status_code
        else:
            if template:
                flash(message, 'error')
                return render_template(template, error_message=message), status_code
            else:
                # 默认错误页面
                return render_template('user/welcome.html', error_message=message), status_code
