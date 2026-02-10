# constants/message_types.py
class MessageTypes:
    """消息类型常量"""
    # 简化版相关
    DEFECT_STATUS_CHANGED = "DEFECT_STATUS_CHANGED"
    DESCRIPTION_CHANGED = "DESCRIPTION_CHANGED"
    ANALYSIS_CHANGED = "ANALYSIS_CHANGED"
    SOLUTION_CHANGED = "SOLUTION_CHANGED"
    REGRESSION_CHANGED = "REGRESSION_CHANGED"
    # 审核相关
    REVIEW_DEFECT_DESCRIPTION = "review_defect_description"
    REVIEW_REASON_ANALYSIS = "review_reason_analysis"
    REVIEW_SOLUTION_MEASURES = "review_solution_measures"
    REVIEW_REGRESSION_TEST = "review_regression_test"

    # 驳回相关
    REJECT_DEFECT_DESCRIPTION = "reject_defect_description"
    REJECT_REASON_ANALYSIS = "reject_reason_analysis"
    REJECT_SOLUTION_MEASURES = "reject_solution_measures"
    REJECT_REGRESSION_TEST = "reject_regression_test"
    TEST_MANAGER_REVIEW_REGRESSION = "test_manager_review_regression"

    # 指定和邀请相关
    ASSIGN_RETEST = "assign_retest"
    REASON_ANALYSIS = "reason_analysis"
    INVITE_REASON_ANALYSIS = "invite_reason_analysis"
    REJECT_INVITATION = "reject_invitation"
    ASSIGN_SOLUTION = "assign_solution"

    # 跟催相关
    URGE_REASON_ANALYSIS = "urge_reason_analysis"
    URGE_SOLUTION_MEASURES = "urge_solution_measures"

    # 其他
    REGRESSION_TEST = "regression_test"
    DEFECT_CLOSE_CONFIRM = "defect_close_confirm"
    TRANSFER_TO_OTHER = "transfer_to_other"


# 消息类型与内容模板映射
MESSAGE_TEMPLATES = {
    # 审核相关
    MessageTypes.REVIEW_DEFECT_DESCRIPTION: "【请审核】缺陷描述",
    MessageTypes.REVIEW_REASON_ANALYSIS: "【请审核】原因分析",
    MessageTypes.REVIEW_SOLUTION_MEASURES: "【请审核】解决措施",
    MessageTypes.REVIEW_REGRESSION_TEST: "【请审核】回归测试",

    # 驳回相关
    MessageTypes.REJECT_DEFECT_DESCRIPTION: "【被驳回】请处理缺陷描述",
    MessageTypes.REJECT_REASON_ANALYSIS: "【被驳回】请处理原因分析",
    MessageTypes.REJECT_SOLUTION_MEASURES: "【被驳回】请处理解决措施",
    MessageTypes.REJECT_REGRESSION_TEST: "【被驳回】请继续处理",
    MessageTypes.TEST_MANAGER_REVIEW_REGRESSION: "【被驳回】请重新审核",

    # 指定和邀请相关
    MessageTypes.ASSIGN_RETEST: "【指定再测试】请确认缺陷描述",
    MessageTypes.REASON_ANALYSIS: "【原因分析】请处理原因分析",
    MessageTypes.INVITE_REASON_ANALYSIS: "【邀请共同分析】请处理原因分析",
    MessageTypes.REJECT_INVITATION: "【驳回邀请】邀请被驳回",
    MessageTypes.ASSIGN_SOLUTION: "【解决措施分工】请处理解决措施",

    # 跟催相关
    MessageTypes.URGE_REASON_ANALYSIS: "【原因分析跟催】请尽快处理",
    MessageTypes.URGE_SOLUTION_MEASURES: "【解决措施跟催】请尽快处理",

    # 其他
    MessageTypes.REGRESSION_TEST: "【回归测试】请处理回归测试",
    MessageTypes.DEFECT_CLOSE_CONFIRM: "【缺陷单关闭确认】缺陷已解决，关闭",
    MessageTypes.TRANSFER_TO_OTHER: "【缺陷单转处理】请处理",
    # 简化版
    MessageTypes.DESCRIPTION_CHANGED: f"【缺陷描述已提交，请处理原因分析】",
    MessageTypes.ANALYSIS_CHANGED: f"【原因分析已提交，请处理解决措施】",
    MessageTypes.SOLUTION_CHANGED: f"【解决措施已提交，请处理回归测试】",
    MessageTypes.REGRESSION_CHANGED: f"【回归测试已提交，请确认关闭】",
    MessageTypes.DEFECT_STATUS_CHANGED: f"【缺陷单状态发生了变更】",
}

# 时间字段映射（用于构建完整消息）
TIME_FIELD_MAP = {
    # 审核类 - 使用提交时间
    MessageTypes.REVIEW_DEFECT_DESCRIPTION: "提交时间",
    MessageTypes.REVIEW_REASON_ANALYSIS: "提交时间",
    MessageTypes.REVIEW_SOLUTION_MEASURES: "提交时间",
    MessageTypes.REVIEW_REGRESSION_TEST: "提交时间",
    MessageTypes.REGRESSION_TEST: "提交时间",
    MessageTypes.DEFECT_CLOSE_CONFIRM: "提交时间",

    # 驳回类 - 使用驳回时间
    MessageTypes.REJECT_DEFECT_DESCRIPTION: "驳回时间",
    MessageTypes.REJECT_REASON_ANALYSIS: "驳回时间",
    MessageTypes.REJECT_SOLUTION_MEASURES: "驳回时间",
    MessageTypes.REJECT_REGRESSION_TEST: "驳回时间",
    MessageTypes.REJECT_INVITATION: "驳回时间",

    # 指定邀请类 - 使用指定/邀请时间
    MessageTypes.ASSIGN_RETEST: "指定时间",
    MessageTypes.REASON_ANALYSIS: "邀请时间",
    MessageTypes.INVITE_REASON_ANALYSIS: "邀请时间",
    MessageTypes.ASSIGN_SOLUTION: "分工时间",

    # 跟催类 - 使用跟催时间
    MessageTypes.URGE_REASON_ANALYSIS: "跟催时间",
    MessageTypes.URGE_SOLUTION_MEASURES: "跟催时间"
}

# 操作人字段映射
OPERATOR_FIELD_MAP = {
    # 审核类 - 显示提交人
    MessageTypes.REVIEW_DEFECT_DESCRIPTION: "提交人",
    MessageTypes.REVIEW_REASON_ANALYSIS: "提交人",
    MessageTypes.REVIEW_SOLUTION_MEASURES: "提交人",
    MessageTypes.REVIEW_REGRESSION_TEST: "提交人",
    MessageTypes.REGRESSION_TEST: "提交人",
    MessageTypes.DEFECT_CLOSE_CONFIRM: "提交人",

    # 驳回类 - 显示审核人/操作人
    MessageTypes.REJECT_DEFECT_DESCRIPTION: "审核人",
    MessageTypes.REJECT_REASON_ANALYSIS: "审核人",
    MessageTypes.REJECT_SOLUTION_MEASURES: "审核人",
    MessageTypes.REJECT_REGRESSION_TEST: "审核人",
    MessageTypes.REJECT_INVITATION: "操作人",

    # 指定邀请类 - 显示指定人/邀请人/分工人
    MessageTypes.ASSIGN_RETEST: "指定人",
    MessageTypes.REASON_ANALYSIS: "邀请人",
    MessageTypes.INVITE_REASON_ANALYSIS: "邀请人",
    MessageTypes.ASSIGN_SOLUTION: "分工人",

    # 跟催类 转处理类 - 显示操作人
    MessageTypes.URGE_REASON_ANALYSIS: "操作人",
    MessageTypes.URGE_SOLUTION_MEASURES: "操作人",
    MessageTypes.TRANSFER_TO_OTHER: "操作人"
}