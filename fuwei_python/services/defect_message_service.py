# services/defect_message_service.py
from flask import current_app
from conf.db import db

from constants.message_types import TIME_FIELD_MAP, OPERATOR_FIELD_MAP, MessageTypes, MESSAGE_TEMPLATES
from models.defect.model import Defect
from models.defect_message.model import DefectMessage
from models.users.models import User


class DefectMessageService:

    @staticmethod
    def save_message(send_to_user_id, send_from_user_id, defect_id, message_type, extra_params=None):
        """
        保存消息（使用Model方法）
        """
        try:
            # 检查缺陷单是否存在
            defect = Defect.query.get(defect_id)
            if not defect:
                current_app.logger.warning(f"缺陷单不存在: {defect_id}")
                return False

            # 获取消息模板
            content_template = MESSAGE_TEMPLATES.get(message_type, "【系统消息】")

            # 使用Model创建消息
            message = DefectMessage.create_message(
                send_to_user_id=send_to_user_id,
                send_from_user_id=send_from_user_id,
                defect_id=defect_id,
                message_type=message_type,
                content=content_template,
                extra_params=extra_params
            )

            current_app.logger.info(f"消息保存成功: {message.id}, 类型: {message_type}")
            return True

        except Exception as e:
            current_app.logger.error(f"保存消息失败: {str(e)}")
            db.session.rollback()
            return False

    @staticmethod
    def get_user_messages(user_id):
        """
        获取用户的消息列表（不使用join的替代方案）
        """
        try:
            # 先获取消息
            messages = DefectMessage.get_user_messages(user_id)

            result = []
            for msg in messages:
                # 单独查询每个缺陷的标题
                defect = Defect.query.get(msg.defect_id)
                if not defect:
                    # 如果缺陷不存在，标记消息为已关闭并跳过
                    msg.is_closed = True
                    db.session.commit()
                    continue

                # 构建完整消息内容
                full_content = DefectMessageService.build_message_content(msg, defect.title)
                part_link = 'defect'
                if defect.defect_type == 'simplified':
                    part_link = 'defect/simplified'
                if defect.defect_type == 'simplified2':
                    part_link = 'defect/simplified2'
                result.append({
                    'id': msg.id,
                    'defect_id': msg.defect_id,
                    'defect_number': defect.defect_number,
                    'part_link': part_link,
                    'defect_link': f'<a class="defect-link" href="/{part_link}/{defect.id}">{defect.defect_number}</a>',
                    'defect_title': defect.title,
                    'message_type': msg.message_type,
                    'content': full_content,
                    'send_time': msg.send_time.strftime('%Y-%m-%d %H:%M:%S'),
                    'send_from_user_id': msg.send_from_user_id,
                    'extra_params': msg.extra_params
                })

            return result

        except Exception as e:
            current_app.logger.error(f"获取用户消息失败: {str(e)}")
            return []

    @staticmethod
    def build_message_content(message, defect_title):
        """
        构建完整的消息内容
        注意：第二个参数是 defect_title 字符串，不是 Defect 对象
        """
        base_content = message.content

        # 获取时间字段和操作人字段
        time_field = TIME_FIELD_MAP.get(message.message_type, "提交时间")
        operator_field = OPERATOR_FIELD_MAP.get(message.message_type, "操作人")

        # 获取发送人信息
        from_user = User.get_user_by_id(message.send_from_user_id)
        from_user_name_email = '未知用户'
        if from_user:
            from_user_name_email = f'{from_user.real_name}/{from_user.email}'  # 修正了这里，应该是email

        # 构建基础消息 - 注意：defect_title 已经是字符串
        full_content = f"{base_content}。单号：{message.defect_id} {time_field}：{message.send_time.strftime('%Y-%m-%d %H:%M:%S')} {operator_field}：{from_user_name_email} 缺陷标题：{defect_title}"

        # 添加额外参数
        if message.extra_params:
            if 'reason' in message.extra_params:
                if message.message_type == MessageTypes.REJECT_INVITATION:
                    full_content += f" 驳回原因：{message.extra_params['reason']}"
                elif message.message_type in [MessageTypes.URGE_REASON_ANALYSIS, MessageTypes.URGE_SOLUTION_MEASURES]:
                    full_content += f" 跟催原因：{message.extra_params['reason']}"
                else:
                    full_content += f" 原因：{message.extra_params['reason']}"

        return full_content

    @staticmethod
    def close_message(message_id, user_id):
        """
        关闭单条消息（使用Model方法）
        """
        try:
            success = DefectMessage.close_message(message_id, user_id)

            if success:
                current_app.logger.info(f"消息已关闭: {message_id}")
            else:
                current_app.logger.warning(f"关闭消息失败，消息不存在或无权限: {message_id}")

            return success

        except Exception as e:
            current_app.logger.error(f"关闭消息失败: {str(e)}")
            return False

    @staticmethod
    def get_unread_count(user_id):
        """
        获取用户未读消息数量
        """
        try:
            return DefectMessage.get_unread_count(user_id)
        except Exception as e:
            current_app.logger.error(f"获取未读消息数量失败: {str(e)}")
            return 0


# 便捷的消息创建方法
class MessageCreator:
    """消息创建工具类"""

    @staticmethod
    def create_review_message(defect_id, reviewer_id, submitter_id, review_type):
        """创建审核消息"""
        message_type_map = {
            'defect_description': MessageTypes.REVIEW_DEFECT_DESCRIPTION,
            'reason_analysis': MessageTypes.REVIEW_REASON_ANALYSIS,
            'solution_measures': MessageTypes.REVIEW_SOLUTION_MEASURES,
            'regression_test': MessageTypes.REVIEW_REGRESSION_TEST
        }

        message_type = message_type_map.get(review_type)
        if not message_type:
            raise ValueError(f"未知的审核类型: {review_type}")

        return DefectMessageService.save_message(
            send_to_user_id=reviewer_id,
            send_from_user_id=submitter_id,
            defect_id=defect_id,
            message_type=message_type
        )

    @staticmethod
    def create_reject_message(defect_id, submitter_id, reviewer_id, reject_type, reason=None):
        """创建驳回消息"""
        message_type_map = {
            'defect_description': MessageTypes.REJECT_DEFECT_DESCRIPTION,
            'reason_analysis': MessageTypes.REJECT_REASON_ANALYSIS,
            'solution_measures': MessageTypes.REJECT_SOLUTION_MEASURES,
            'regression_test': MessageTypes.REJECT_REGRESSION_TEST,
            'test_manager_review_regression': MessageTypes.TEST_MANAGER_REVIEW_REGRESSION
        }

        message_type = message_type_map.get(reject_type)
        if not message_type:
            raise ValueError(f"未知的驳回类型: {reject_type}")

        extra_params = {'reason': reason} if reason else None

        return DefectMessageService.save_message(
            send_to_user_id=submitter_id,
            send_from_user_id=reviewer_id,
            defect_id=defect_id,
            message_type=message_type,
            extra_params=extra_params
        )

    @staticmethod
    def create_urge_message(defect_id, target_user_id, operator_id, urge_type, reason=None):
        """创建跟催消息"""
        message_type_map = {
            'reason_analysis': MessageTypes.URGE_REASON_ANALYSIS,
            'solution_measures': MessageTypes.URGE_SOLUTION_MEASURES
        }

        message_type = message_type_map.get(urge_type)
        if not message_type:
            raise ValueError(f"未知的跟催类型: {urge_type}")

        extra_params = {'reason': reason} if reason else None

        return DefectMessageService.save_message(
            send_to_user_id=target_user_id,
            send_from_user_id=operator_id,
            defect_id=defect_id,
            message_type=message_type,
            extra_params=extra_params
        )

    @staticmethod
    def create_assign_message(defect_id, assignee_id, assigner_id, assign_type, extra_params=None):
        """创建指派消息"""
        message_type_map = {
            'retest': MessageTypes.ASSIGN_RETEST,
            'solution': MessageTypes.ASSIGN_SOLUTION
        }

        message_type = message_type_map.get(assign_type)
        if not message_type:
            raise ValueError(f"未知的指派类型: {assign_type}")

        return DefectMessageService.save_message(
            send_to_user_id=assignee_id,
            send_from_user_id=assigner_id,
            defect_id=defect_id,
            message_type=message_type,
            extra_params=extra_params
        )
