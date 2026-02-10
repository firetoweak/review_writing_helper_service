import json

from flask import current_app

from conf.config import app_config
from models.defect.model import Defect
from models.users.models import User


class DefectEmailService:
    @staticmethod
    def get_formated_defect_description(defect: Defect) -> str:
        """从 defect 的描述字段获取格式化的描述信息"""
        ret_str = defect.description
        try:
            description_list = json.loads(defect.description)
            current_app.logger.debug(f'len(description_list):{description_list}')
            ret_str = ''
            for item in description_list:
                ret_str += f"{item.get('title')}: {item.get('description')}\n"
        except Exception as e:
            current_app.logger.info('简化版DTS，缺陷描述非JSON格式')
        return ret_str

    @staticmethod
    def get_urge_defect_email_content(defect: Defect, urge_reason: str, action_type: str) -> str:
        """
        构建跟催类缺陷邮件内容
        """
        des_str = DefectEmailService.get_formated_defect_description(defect)
        part_link = 'defect'
        if defect.defect_type == 'simplified':
            part_link = 'defect/simplified'
        if defect.defect_type == 'simplified2':
            part_link = 'defect/simplified2'
        content = f'''请尽快处理缺陷单的{action_type}<br>
        【单号】：{defect.defect_number} <br>
        【链接】：<a href="http://{app_config["domain"]}/{part_link}/{defect.id}"> http://{app_config["domain"]}/{part_link}/{defect.id} </a> <br>
        【跟催原因】：{urge_reason} <br>
        【缺陷描述】：<br> {des_str}'''
        return content



    @staticmethod
    def get_general_defect_email_content(defect: Defect, message: str, action_type: str) -> str:
        """
        构建通用缺陷邮件内容
        """
        from services.defect_services import DefectWorkflowService
        current_app.logger.debug(f'----------')
        workflow_service = DefectWorkflowService()
        current_stage_name = workflow_service.get_current_stage_name(defect)
        des_str = DefectEmailService.get_formated_defect_description(defect)
        current_app.logger.debug(f'des_str: {des_str}')
        pre_content = ''
        if action_type!='':
            pre_content = f'请尽快处理缺陷单的{action_type}<br>'
        if action_type == '关闭确认':
            pre_content = '缺陷单已关闭，请查看<br>'
        part_link = 'defect'
        if defect.defect_type == 'simplified':
            part_link = 'defect/simplified'
        if defect.defect_type == 'simplified2':
            part_link = 'defect/simplified2'
        content = f'''{pre_content}
        【单号】：{defect.defect_number} <br>
        【链接】：<a href="http://{app_config["domain"]}/{part_link}/{defect.id}"> http://{app_config["domain"]}/{part_link}/{defect.id} </a> <br>
        【说明】：{message} <br>
        【缺陷描述】：<br> {des_str}'''
        return content

    @staticmethod
    def get_general_defect_email_content2(defect_id, message: str, action_type: str) -> str:
        """
        构建通用缺陷邮件内容
        """
        defect = Defect.query.get(defect_id)
        from services.defect_services import DefectWorkflowService
        current_app.logger.debug(f'----------')
        workflow_service = DefectWorkflowService()
        current_stage_name = "测试人员回归测试"
        des_str = DefectEmailService.get_formated_defect_description(defect)
        current_app.logger.debug(f'des_str: {des_str}')
        pre_content = f'请尽快处理缺陷单的{action_type}<br>'
        if action_type == '关闭确认':
            pre_content = '缺陷单已关闭，请查看<br>'
        part_link = 'defect'
        if defect.defect_type == 'simplified':
            part_link = 'defect/simplified'
        if defect.defect_type == 'simplified2':
            part_link = 'defect/simplified2'
        content = f'''{pre_content}
        【单号】：{defect.defect_number} <br>
        【流程阶段】：{current_stage_name} <br>
        【链接】：<a href="http://{app_config["domain"]}/{part_link}/{defect.id}"> http://{app_config["domain"]}/{part_link}/{defect.id} </a> <br>
        【说明】：{message} <br>
        【缺陷描述】：<br> {des_str}'''
        return content




    @staticmethod
    def _get_user_display_info(user_id: int) -> str:
        """
        根据用户ID获取用户显示信息
        """
        if not user_id:
            return "系统"

        user = User.get_user_by_id(user_id)
        if user:
            return f"{user.real_name}/{user.email}"
        else:
            return f"未知用户(ID:{user_id})"

    @staticmethod
    def get_review_email_content(defect: Defect, review_type: str, submitter_id: int = None) -> str:
        """
        构建审核邮件内容
        """
        review_type_map = {
            'defect_description': '缺陷描述',
            'reason_analysis': '原因分析',
            'solution_measures': '解决措施',
            'regression_test': '回归测试'
        }

        action_type = review_type_map.get(review_type, '内容')

        if submitter_id:
            user_info = DefectEmailService._get_user_display_info(submitter_id)
            message = f"提交人：{user_info} 已提交，请及时审核"
        else:
            message = "请及时审核"

        return DefectEmailService.get_general_defect_email_content(defect, message, f"{action_type}审核")

    @staticmethod
    def get_reject_email_content(defect: Defect, reject_type: str, reject_reason: str, reviewer_id: int = None) -> str:
        """
        构建驳回邮件内容
        """
        reject_type_map = {
            'defect_description': '缺陷描述',
            'reason_analysis': '原因分析',
            'solution_measures': '解决措施',
            'regression_test': '回归测试',
            'test_manager_review_regression': '审核回归测试',
        }

        action_type = reject_type_map.get(reject_type, '内容')

        if reviewer_id:
            user_info = DefectEmailService._get_user_display_info(reviewer_id)
            message = f"审核人：{user_info} 已驳回，驳回原因：{reject_reason}"
        else:
            message = f"驳回原因：{reject_reason}"

        return DefectEmailService.get_general_defect_email_content(defect, message, f"{action_type}驳回")

    @staticmethod
    def get_assign_email_content(defect: Defect, assign_type: str, assigner_id: int = None, reason: str = None) -> str:
        """
        构建指派邮件内容
        """
        assign_type_map = {
            'retest': '再测试',
            'solution': '解决措施'
        }

        action_type = assign_type_map.get(assign_type, '任务')

        message_parts = []
        if assigner_id:
            user_info = DefectEmailService._get_user_display_info(assigner_id)
            message_parts.append(f"指定人：{user_info}")
        if reason:
            message_parts.append(f"原因：{reason}")

        message = "，".join(message_parts) if message_parts else "请及时处理"

        return DefectEmailService.get_general_defect_email_content(defect, message, f"{action_type}指派")

    @staticmethod
    def get_invite_email_content(defect: Defect, invite_type: str, inviter_id: int = None, reason: str = None) -> str:
        """
        构建邀请邮件内容
        """
        invite_type_map = {
            'reason_analysis': '原因分析',
            'common_analysis': '共同分析'
        }

        action_type = invite_type_map.get(invite_type, '分析')

        message_parts = []
        if inviter_id:
            user_info = DefectEmailService._get_user_display_info(inviter_id)
            message_parts.append(f"邀请人：{user_info}")
        if reason:
            message_parts.append(f"原因：{reason}")

        message = "，".join(message_parts) if message_parts else "邀请您参与分析"
        return DefectEmailService.get_general_defect_email_content(defect, message, f"{action_type}邀请")

    @staticmethod
    def get_urge_email_content(defect: Defect, urge_type: str, urge_reason: str, urger_id: int = None) -> str:
        """
        构建跟催邮件内容
        """
        urge_type_map = {
            'reason_analysis': '原因分析',
            'solution_measures': '解决措施'
        }

        action_type = urge_type_map.get(urge_type, '处理')

        if urger_id:
            user_info = DefectEmailService._get_user_display_info(urger_id)
            message = f"跟催人：{user_info}"
        else:
            message = "系统跟催"

        return DefectEmailService.get_urge_defect_email_content(defect, urge_reason, f"{action_type}跟催")

    @staticmethod
    def get_close_confirm_email_content(defect: Defect, closer_id: int = None, is_closed: bool = True) -> str:
        """
        构建关闭确认邮件内容
        """
        if closer_id:
            user_info = DefectEmailService._get_user_display_info(closer_id)
            if is_closed:
                result_message = '缺陷已解决'
            else:
                result_message = '缺陷未解决'
            message = f"操作人：{user_info} 确认{result_message}，请查看"
        else:
            message = "缺陷已关闭，请查看"

        return DefectEmailService.get_general_defect_email_content(defect, message, "关闭确认")

    @staticmethod
    def get_reject_invitation_email_content(defect: Defect, reject_reason: str, rejecter_id: int = None) -> str:
        """
        构建邀请驳回邮件内容
        """
        if rejecter_id:
            user_info = DefectEmailService._get_user_display_info(rejecter_id)
            message = f"操作人：{user_info} 驳回了邀请，驳回原因：{reject_reason}"
        else:
            message = f"邀请被驳回，驳回原因：{reject_reason}"

        return DefectEmailService.get_general_defect_email_content(defect, message, "邀请驳回")

    @staticmethod
    def get_email_content_by_message_type(defect: Defect, message_type: str, extra_params: dict = None,
                                          from_user_id: int = None) -> str:
        """
        根据消息类型自动构建邮件内容
        """
        from constants.message_types import MessageTypes

        # 审核相关
        if message_type == MessageTypes.REVIEW_DEFECT_DESCRIPTION:
            return DefectEmailService.get_review_email_content(defect, 'defect_description', from_user_id)
        elif message_type == MessageTypes.REVIEW_REASON_ANALYSIS:
            return DefectEmailService.get_review_email_content(defect, 'reason_analysis', from_user_id)
        elif message_type == MessageTypes.REVIEW_SOLUTION_MEASURES:
            return DefectEmailService.get_review_email_content(defect, 'solution_measures', from_user_id)
        elif message_type == MessageTypes.REVIEW_REGRESSION_TEST:
            return DefectEmailService.get_review_email_content(defect, 'regression_test', from_user_id)

        # 驳回相关
        elif message_type in [MessageTypes.REJECT_DEFECT_DESCRIPTION, MessageTypes.REJECT_REASON_ANALYSIS,
                              MessageTypes.REJECT_SOLUTION_MEASURES, MessageTypes.REJECT_REGRESSION_TEST]:
            reject_type = message_type.split('_')[1]  # 提取类型部分
            reject_reason = extra_params.get('reason', '') if extra_params else ''
            return DefectEmailService.get_reject_email_content(defect, reject_type, reject_reason, from_user_id)

        # 指派相关
        elif message_type == MessageTypes.ASSIGN_RETEST:
            return DefectEmailService.get_assign_email_content(defect, 'retest', from_user_id)
        elif message_type == MessageTypes.ASSIGN_SOLUTION:
            return DefectEmailService.get_assign_email_content(defect, 'solution', from_user_id)

        # 邀请相关
        elif message_type == MessageTypes.REASON_ANALYSIS:
            return DefectEmailService.get_invite_email_content(defect, 'reason_analysis', from_user_id)
        elif message_type == MessageTypes.INVITE_REASON_ANALYSIS:
            return DefectEmailService.get_invite_email_content(defect, 'common_analysis', from_user_id)

        # 跟催相关 - 使用专门的跟催函数
        elif message_type == MessageTypes.URGE_REASON_ANALYSIS:
            urge_reason = extra_params.get('reason', '') if extra_params else ''
            return DefectEmailService.get_urge_email_content(defect, 'reason_analysis', urge_reason, from_user_id)
        elif message_type == MessageTypes.URGE_SOLUTION_MEASURES:
            urge_reason = extra_params.get('reason', '') if extra_params else ''
            return DefectEmailService.get_urge_email_content(defect, 'solution_measures', urge_reason, from_user_id)

        # 其他
        elif message_type == MessageTypes.REGRESSION_TEST:
            return DefectEmailService.get_general_defect_email_content(defect, '请及时进行', "回归测试")
        elif message_type == MessageTypes.DEFECT_CLOSE_CONFIRM:
            return DefectEmailService.get_close_confirm_email_content(defect, from_user_id)
        elif message_type == MessageTypes.REJECT_INVITATION:
            reject_reason = extra_params.get('reason', '') if extra_params else ''
            return DefectEmailService.get_reject_invitation_email_content(defect, reject_reason, from_user_id)

        # 默认情况
        else:
            return DefectEmailService.get_general_defect_email_content(defect, "请及时处理", "相关操作")

    @staticmethod
    def get_email_subject_by_message_type(defect: Defect, message_type: str) -> str:
        """
        根据消息类型获取邮件主题
        """
        from constants.message_types import MessageTypes

        subject_map = {
            # 审核相关
            MessageTypes.REVIEW_DEFECT_DESCRIPTION: f"【请审核缺陷描述】缺陷单 {defect.defect_number} - {defect.title}",
            MessageTypes.REVIEW_REASON_ANALYSIS: f"【请审核原因分析】缺陷单 {defect.defect_number} - {defect.title}",
            MessageTypes.REVIEW_SOLUTION_MEASURES: f"【请审核解决措施】缺陷单 {defect.defect_number} - {defect.title}",
            MessageTypes.REVIEW_REGRESSION_TEST: f"【请审核回归测试】缺陷单 {defect.defect_number} - {defect.title}",

            # 驳回相关
            MessageTypes.REJECT_DEFECT_DESCRIPTION: f"【缺陷描述被驳回】缺陷单 {defect.defect_number} - {defect.title}",
            MessageTypes.REJECT_REASON_ANALYSIS: f"【原因分析被驳回】缺陷单 {defect.defect_number} - {defect.title}",
            MessageTypes.REJECT_SOLUTION_MEASURES: f"【解决措施被驳回】缺陷单 {defect.defect_number} - {defect.title}",
            MessageTypes.REJECT_REGRESSION_TEST: f"【回归测试被驳回】缺陷单 {defect.defect_number} - {defect.title}",
            MessageTypes.TEST_MANAGER_REVIEW_REGRESSION: f"【审核回归测试被驳回】缺陷单 {defect.defect_number} - {defect.title}",

            # 指派相关
            MessageTypes.ASSIGN_RETEST: f"【指定再测试】缺陷单 {defect.defect_number} - {defect.title}",
            MessageTypes.ASSIGN_SOLUTION: f"【解决措施分工】缺陷单 {defect.defect_number} - {defect.title}",

            # 邀请相关
            MessageTypes.REASON_ANALYSIS: f"【原因分析邀请】缺陷单 {defect.defect_number} - {defect.title}",
            MessageTypes.INVITE_REASON_ANALYSIS: f"【邀请共同分析】缺陷单 {defect.defect_number} - {defect.title}",

            # 跟催相关
            MessageTypes.URGE_REASON_ANALYSIS: f"【原因分析跟催】缺陷单 {defect.defect_number} - {defect.title}",
            MessageTypes.URGE_SOLUTION_MEASURES: f"【解决措施跟催】缺陷单 {defect.defect_number} - {defect.title}",

            # 其他
            MessageTypes.REGRESSION_TEST: f"【回归测试】缺陷单 {defect.defect_number} - {defect.title}",
            MessageTypes.DEFECT_CLOSE_CONFIRM: f"【缺陷关闭确认】缺陷单 {defect.defect_number} - {defect.title}",
            MessageTypes.REJECT_INVITATION: f"【邀请被驳回】缺陷单 {defect.defect_number} - {defect.title}",
            MessageTypes.TRANSFER_TO_OTHER: f"【转处理】缺陷单 {defect.defect_number} - {defect.title}"
        }

        return subject_map.get(message_type, f"缺陷单通知 - {defect.defect_number} - {defect.title}")



