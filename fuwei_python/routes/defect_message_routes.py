# defect_message_routes.py
from flask import Blueprint, request, jsonify, current_app, g, render_template
from models.defect_message.model import DefectMessage
from services.defect_message_service import DefectMessageService

defect_message_bp = Blueprint('defect_message', __name__)

@defect_message_bp.route('/list', methods=['GET'])
def get_defect_messages():
    return render_template('components/defect_message.html')

@defect_message_bp.route('/api/defect-messages', methods=['GET'])
def get_messages():
    """
    获取当前用户的消息列表
    """
    try:
        user_id = g.user_id
        if not user_id:
            return jsonify({'code': 401, 'message': '未登录', 'data': []})

        messages = DefectMessageService.get_user_messages(user_id)

        return jsonify({
            'code': 200,
            'message': '成功',
            'data': messages
        })

    except Exception as e:
        current_app.logger.error(f"获取消息列表接口异常: {str(e)}")
        return jsonify({'code': 500, 'message': '系统错误', 'data': []})


@defect_message_bp.route('/api/defect-messages/<int:message_id>/close', methods=['POST'])
def close_message(message_id):
    """
    关闭单条消息
    """
    try:
        user_id = g.user_id
        if not user_id:
            return jsonify({'code': 401, 'message': '未登录'})

        success = DefectMessageService.close_message(message_id, user_id)

        if success:
            return jsonify({'code': 200, 'message': '消息已关闭'})
        else:
            return jsonify({'code': 404, 'message': '消息不存在'})

    except Exception as e:
        current_app.logger.error(f"关闭消息接口异常: {str(e)}")
        return jsonify({'code': 500, 'message': '系统错误'})


@defect_message_bp.route('/api/defect-messages/close-all', methods=['POST'])
def close_all_messages():
    """
    关闭用户所有消息
    """
    try:
        user_id = g.user_id
        if not user_id:
            return jsonify({'code': 401, 'message': '未登录'})

        count = DefectMessage.close_all_user_messages(user_id)

        return jsonify({
            'code': 200,
            'message': f'成功关闭 {count} 条消息',
            'data': {'closed_count': count}
        })

    except Exception as e:
        current_app.logger.error(f"关闭所有消息接口异常: {str(e)}")
        return jsonify({'code': 500, 'message': '系统错误'})


@defect_message_bp.route('/api/defect-messages/unread-count', methods=['GET'])
def get_unread_count():
    """
    获取未读消息数量
    """
    try:
        user_id = g.user_id
        if not user_id:
            return jsonify({'code': 401, 'message': '未登录', 'data': {'count': 0}})

        count = DefectMessageService.get_unread_count(user_id)

        return jsonify({
            'code': 200,
            'message': '成功',
            'data': {'count': count}
        })

    except Exception as e:
        current_app.logger.error(f"获取未读消息数量接口异常: {str(e)}")
        return jsonify({'code': 500, 'message': '系统错误', 'data': {'count': 0}})


@defect_message_bp.route('/api/defect-messages', methods=['POST'])
def create_message():
    """
    创建新消息（供其他服务调用）
    """
    try:
        data = request.get_json()

        required_fields = ['send_to_user_id', 'defect_id', 'message_type']
        for field in required_fields:
            if field not in data:
                return jsonify({'code': 400, 'message': f'缺少必要字段: {field}'})

        success = DefectMessageService.save_message(
            send_to_user_id=data['send_to_user_id'],
            send_from_user_id=data.get('send_from_user_id'),
            defect_id=data['defect_id'],
            message_type=data['message_type'],
            extra_params=data.get('extra_params')
        )

        if success:
            return jsonify({'code': 200, 'message': '消息创建成功'})
        else:
            return jsonify({'code': 500, 'message': '消息创建失败'})

    except Exception as e:
        current_app.logger.error(f"创建消息接口异常: {str(e)}")
        return jsonify({'code': 500, 'message': '系统错误'})