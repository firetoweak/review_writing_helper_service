from flask import Blueprint, request, render_template, jsonify, flash, redirect, url_for, g, current_app

from models.defect_level.model import DEFECT_LEVEL_FIELD_DISPLAY_NAMES
from models.users.models import User
from services.defect_level_services import DefectLevelsService
from services.role_services import UserRoleService

defect_level_bp = Blueprint('defect_level', __name__)


@defect_level_bp.route('/levels', methods=['GET'])
@UserRoleService.check_global_roles(
    allowed_roles=['global_admin', 'global_viewer'],
    template='defect/defect_levels.html'
)
def get_defect_levels():
    """获取缺陷级别配置页面"""
    try:
        # 获取当前用户的缺陷级别配置
        defect_levels = DefectLevelsService.get_all_defect_levels()
        # 如果用户还没有配置，创建默认配置
        if not defect_levels:
            DefectLevelsService.create_default_defect_level(g.admin_user_id)  # 创建人为 admin_user_id
            defect_levels = DefectLevelsService.get_all_defect_levels()

        # 使用to_dict()方法转换数据格式
        defect_levels_data = defect_levels.to_dict()

        # 获取当前用户的修改日志
        logs = DefectLevelsService.get_modification_logs()

        return render_template('defect/defect_levels.html',
                               is_global_admin=g.is_global_admin,
                               is_global_viewer=g.is_global_viewer,
                               defect_levels=defect_levels_data,
                               logs=logs)
    except Exception as e:
        current_app.logger.error(f"获取缺陷级别配置失败: {str(e)}")
        flash('获取缺陷级别配置失败，请稍后重试', 'error')
        return render_template('defect/defect_levels.html',
                               error_message='获取数据失败'), 500


@defect_level_bp.route('/api/logs', methods=['GET'])
@UserRoleService.check_global_roles(
    allowed_roles=['global_admin', 'global_viewer'],
    json_response=True
)
def get_defect_level_logs():
    """API接口：获取缺陷级别修改日志"""
    try:
        logs = DefectLevelsService.get_modification_logs()
        # 将日志对象转换为字典格式
        logs_data = []
        for log in logs:
            logs_data.append({
                'modifier': log.modifier,
                'field_name': log.field_name,
                'old_value': log.old_value,
                'new_value': log.new_value,
                'modified_time': log.modified_time.strftime('%Y-%m-%d %H:%M:%S')  # 格式化时间
            })

        return jsonify({
            'success': True,
            'logs': logs_data
        })
    except Exception as e:
        current_app.logger.error(f"获取修改日志失败: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'获取日志失败: {str(e)}'
        }), 500


@defect_level_bp.route('/levels/update', methods=['POST'])
@UserRoleService.check_global_roles(
    allowed_roles=['global_admin'],
    template='defect/defect_levels.html'
)
def update_defect_level():
    """更新缺陷级别分数（表单提交）"""
    try:
        current_app.logger.debug('modify levels score...')
        modifier_id = g.user_id
        oper_user = User.get_user_by_id(modifier_id)
        user_name = oper_user.real_name
        email = oper_user.email
        modifier = user_name
        if email:
            modifier = user_name + '/' + email
        current_app.logger.debug(f'modifier: {modifier}')

        # 验证参数
        level_id = request.form.get('level_id')
        field_name = request.form.get('field_name')
        new_score = request.form.get('new_score')

        if not all([level_id, field_name, new_score]):
            flash('参数不完整，请检查填写内容', 'error')
            return redirect(url_for('defect_level.get_defect_levels'))

        level_id = int(level_id)
        new_score = float(new_score)

        # 调用更新服务
        result, message = DefectLevelsService.update_defect_level_score(
            level_id, field_name, new_score, modifier
        )

        if result:
            flash(message, 'success')
            current_app.logger.info(f'用户 {modifier} 成功更新缺陷级别 {level_id} 的 {field_name} 为 {new_score}')
        else:
            flash(message, 'error')
            current_app.logger.warning(f'用户 {modifier} 更新缺陷级别失败: {message}')

    except (ValueError, TypeError) as e:
        error_msg = f'参数格式错误: {str(e)}'
        flash(error_msg, 'error')
        current_app.logger.error(f"参数错误: {str(e)}")
    except Exception as e:
        error_msg = f'更新失败: {str(e)}'
        flash(error_msg, 'error')
        current_app.logger.error(f"更新缺陷级别失败: {str(e)}")
    return redirect(url_for('defect_level.get_defect_levels',defect_type=request.values.get("defect_type")))


@defect_level_bp.route('/api/levels', methods=['GET'])
@UserRoleService.check_global_roles(
    allowed_roles=['global_admin', 'global_viewer'],
    json_response=True
)
def api_get_defect_levels():
    """API接口：获取缺陷级别配置"""
    try:
        defect_levels = DefectLevelsService.get_all_defect_levels()

        # 如果没有配置，创建默认配置
        if not defect_levels:
            DefectLevelsService.create_default_defect_level(g.admin_user_id)
            defect_levels = DefectLevelsService.get_all_defect_levels()

        # 转换为字典格式
        defect_levels_dict = [level.to_dict() for level in defect_levels]

        return jsonify({
            'success': True,
            'data': defect_levels_dict
        })
    except Exception as e:
        current_app.logger.error(f"API获取缺陷级别失败: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'获取数据失败: {str(e)}'
        }), 500


@defect_level_bp.route('/api/levels/update', methods=['POST'])
@UserRoleService.check_global_roles(
    allowed_roles=['global_admin'],
    json_response=True
)
def api_update_defect_level():
    """API接口：更新缺陷级别分数"""
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'success': False,
                'message': '请求数据不能为空'
            }), 400

        # 验证必需参数
        required_fields = ['level_id', 'field_name', 'new_score']
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            return jsonify({
                'success': False,
                'message': f'缺少必需参数: {", ".join(missing_fields)}'
            }), 400

        level_id = int(data.get('level_id'))
        field_name = data.get('field_name')
        new_score = float(data.get('new_score'))

        # 获取修改者信息
        modifier_id = g.user_id
        oper_user = User.get_user_by_id(modifier_id)
        user_name = oper_user.real_name
        email = oper_user.email
        modifier = data.get('modifier', user_name)
        if email and modifier == user_name:
            modifier = user_name + '/' + email

        # 调用更新服务
        result, message = DefectLevelsService.update_defect_level_score(
            level_id, field_name, new_score, modifier
        )

        if result:
            current_app.logger.info(f'API用户 {modifier} 成功更新缺陷级别 {level_id} 的 {field_name} 为 {new_score}')
            return jsonify({
                'success': True,
                'message': message,
                'data': result.to_dict() if hasattr(result, 'to_dict') else str(result)
            })
        else:
            current_app.logger.warning(f'API用户 {modifier} 更新缺陷级别失败: {message}')
            return jsonify({
                'success': False,
                'message': message
            }), 400

    except (ValueError, TypeError) as e:
        current_app.logger.error(f"API参数错误: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'参数错误: {str(e)}'
        }), 400
    except Exception as e:
        current_app.logger.error(f"API更新缺陷级别失败: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'更新失败: {str(e)}'
        }), 500