import json
from flask import Blueprint, request, jsonify, session, flash, redirect, url_for, g, render_template, current_app
from sqlalchemy import and_

from conf.db import db
from models.role.model import UserRole, Role
from services.role_services import UserRoleService
from models.users.models import User

# 创建蓝图
global_settings_bp = Blueprint('global_settings', __name__)


# 角色管理辅助函数
def _get_or_create_role(role_name, description):
    """获取或创建角色"""
    role = Role.query.filter_by(name=role_name).first()
    if not role:
        role = Role(name=role_name, description=description)
        db.session.add(role)
        db.session.commit()
        current_app.logger.info(f'创建新角色: {role_name}')
    return role


def _validate_user_request(form_data, required_fields):
    """验证用户请求数据"""
    missing_fields = [field for field in required_fields if not form_data.get(field)]
    if missing_fields:
        return False, f"缺少必填字段: {', '.join(missing_fields)}"
    return True, "验证成功"


# 全局查阅人管理
@global_settings_bp.route('/global_viewer/list', methods=['GET'])
@UserRoleService.check_global_roles(
    allowed_roles=['global_admin', 'global_viewer'],
    template='global_settings/global_viewer_configuration.html'
)
def global_viewer_list():
    """获取全板块查阅人列表"""
    try:
        company_user_list = User.get_company_users_by_user_id(g.user_id)
        company_global_viewer_users = UserRoleService.get_company_global_viewer_users(g.user_id)

        return render_template('global_settings/global_viewer_configuration.html',
                               company_user_list=company_user_list,
                               company_global_viewer_users=company_global_viewer_users,
                               is_company_admin=g.is_company_admin,
                               is_global_admin=g.is_global_admin,
                               is_global_viewer=g.is_global_viewer)

    except Exception as e:
        current_app.logger.error(f"获取查阅人列表失败: {str(e)}")
        flash('获取全板块查阅人用户列表失败，请稍后重试', 'error')
        return render_template('global_settings/global_viewer_configuration.html',
                               error_message='获取用户列表失败'), 500


@global_settings_bp.route('/global_viewer/add', methods=['POST'])
@UserRoleService.check_global_roles(
    allowed_roles=['company_admin', 'global_admin'],
    json_response=True  # 明确指定返回JSON格式
)
def add_global_viewer():
    """添加全局查阅人"""
    try:
        # 验证请求数据
        is_valid, message = _validate_user_request(
            request.form,
            ['email', 'name', 'userID']
        )
        if not is_valid:
            return jsonify({'success': False, 'message': message})

        email = request.form.get('email')
        name = request.form.get('name')
        user_id = request.form.get('userID')
        notes = request.form.get('notes', '')

        # 查找用户
        user = User.query.filter_by(user_id=user_id).first()
        if not user:
            return jsonify({
                'success': False,
                'message': f'用户 {name} 不存在'
            })

        # 获取全局查阅人角色
        role = _get_or_create_role('global_viewer', '全板块查阅人')

        # 检查是否已分配角色
        existing_role = UserRole.query.filter(
            and_(UserRole.user_id == user.user_id, UserRole.role_id == role.id)
        ).first()

        if existing_role:
            return jsonify({
                'success': False,
                'message': '该用户已经是全板块查阅人'
            })

        # 分配角色
        user_role = UserRoleService.assign_role_to_user(
            user_id=user.user_id,
            role_id=role.id,
            notes=notes
        )

        if user_role:
            current_app.logger.info(f'成功添加全局查阅人: {name}({email})')
            return jsonify({'success': True, 'message': '添加成功'})
        else:
            return jsonify({'success': False, 'message': '添加失败'})

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"添加全局查阅人失败: {str(e)}")
        return jsonify({'success': False, 'message': f'添加失败: {str(e)}'})


@global_settings_bp.route('/global_viewer/delete', methods=['POST'])
@UserRoleService.check_global_roles(
    allowed_roles=['company_admin', 'global_admin'],
    json_response=True
)
def delete_global_viewer():
    """删除全局查阅人"""
    try:
        user_id = request.form.get('user_id')
        if not user_id:
            return jsonify({'success': False, 'message': '用户ID不能为空'})

        role = _get_or_create_role('global_viewer', '全板块查阅人')

        # 查找用户角色关系
        user_role = UserRole.query.filter(
            and_(UserRole.user_id == user_id, UserRole.role_id == role.id)
        ).first()

        if not user_role:
            return jsonify({'success': False, 'message': '该用户不是全板块查阅人'})

        result = UserRoleService.remove_role_from_user(
            user_id=int(user_id),
            role_id=role.id
        )

        if result:
            current_app.logger.info(f'成功删除全局查阅人: {user_id}')
            return jsonify({'success': True, 'message': '删除成功'})
        else:
            return jsonify({'success': False, 'message': '删除失败'})

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"删除全局查阅人失败: {str(e)}")
        return jsonify({'success': False, 'message': f'删除失败: {str(e)}'})


# 全局管理员管理
@global_settings_bp.route('/global_admin/list', methods=['GET'])
@UserRoleService.check_global_roles(
    allowed_roles=['company_admin', 'global_admin', 'global_viewer'],
    template='global_settings/global_admin_configuration.html'
)
def global_admin_list():
    """获取全板块管理员列表"""
    try:
        company_user_list = User.get_company_users_by_user_id(g.user_id)
        company_global_admin_users = UserRoleService.get_company_global_admin_users(g.user_id)

        return render_template('global_settings/global_admin_configuration.html',
                               company_user_list=company_user_list,
                               company_global_admin_users=company_global_admin_users,
                               is_company_admin=g.is_company_admin,
                               is_global_admin=g.is_global_admin,
                               is_global_viewer=g.is_global_viewer)

    except Exception as e:
        current_app.logger.error(f"获取管理员列表失败: {str(e)}")
        flash('获取全板块管理员用户列表失败，请稍后重试', 'error')
        return render_template('global_settings/global_admin_configuration.html',
                               error_message='获取用户列表失败'), 500


@global_settings_bp.route('/global_admin/add', methods=['POST'])
@UserRoleService.check_global_roles(
    allowed_roles=['company_admin'],
    json_response=True
)
def add_global_admin():
    """添加全局管理员"""
    try:
        is_valid, message = _validate_user_request(
            request.form,
            ['email', 'name', 'userID']
        )
        if not is_valid:
            return jsonify({'success': False, 'message': message})

        email = request.form.get('email')
        name = request.form.get('name')
        user_id = request.form.get('userID')
        notes = request.form.get('notes', '')

        user = User.query.filter_by(user_id=user_id).first()
        if not user:
            return jsonify({
                'success': False,
                'message': f'用户 {name} 不存在'
            })

        role = _get_or_create_role('global_admin', '全板块管理员')

        # 检查是否已分配角色
        existing_role = UserRole.query.filter(
            and_(UserRole.user_id == user.user_id, UserRole.role_id == role.id)
        ).first()

        if existing_role:
            return jsonify({
                'success': False,
                'message': '该用户已经是全板块管理员'
            })

        user_role = UserRoleService.assign_role_to_user(
            user_id=user.user_id,
            role_id=role.id,
            notes=notes
        )

        if user_role:
            current_app.logger.info(f'成功添加全局管理员: {name}({email})')
            return jsonify({'success': True, 'message': '添加成功'})
        else:
            return jsonify({'success': False, 'message': '添加失败'})

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"添加全局管理员失败: {str(e)}")
        return jsonify({'success': False, 'message': f'添加失败: {str(e)}'})


@global_settings_bp.route('/global_admin/delete', methods=['POST'])
@UserRoleService.check_global_roles(
    allowed_roles=['company_admin'],
    json_response=True
)
def delete_global_admin():
    """删除全局管理员"""
    try:
        user_id = request.form.get('user_id')
        if not user_id:
            return jsonify({'success': False, 'message': '用户ID不能为空'})

        role = _get_or_create_role('global_admin', '全板块管理员')

        user_role = UserRole.query.filter(
            and_(UserRole.user_id == user_id, UserRole.role_id == role.id)
        ).first()

        if not user_role:
            return jsonify({'success': False, 'message': '该用户不是全板块管理员'})

        result = UserRoleService.remove_role_from_user(
            user_id=int(user_id),
            role_id=role.id
        )

        if result:
            current_app.logger.info(f'成功删除全局管理员: {user_id}')
            return jsonify({'success': True, 'message': '删除成功'})
        else:
            return jsonify({'success': False, 'message': '删除失败'})

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"删除全局管理员失败: {str(e)}")
        return jsonify({'success': False, 'message': f'删除失败: {str(e)}'})

