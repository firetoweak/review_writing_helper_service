# services/project_document_services.py
from flask import current_app
from sqlalchemy import and_

from models.project_document.model import DocumentNode, ImprovementDraft, ProjectDocument, DocumentAttachment, Task, \
    ConversationMessage, IndustryList, OutlineRules, ReviewRules
from utils.markdown_converter import convert_markdown_to_html


class ProjectDocumentService:
    """产品立项报告服务类"""

    @staticmethod
    def get_complete_project_document(document_id, include_history=False):
        """
        获取完整的项目文档（产品立项报告）

        Args:
            document_id: 文档ID
            include_history: 是否包含历史任务记录

        Returns:
            dict: 完整的项目文档数据
        """
        try:
            # 获取项目文档基本信息
            project_doc = ProjectDocument.query.filter_by(id=document_id).first()
            if not project_doc:
                return None

            doc_guide_html = convert_markdown_to_html(project_doc.doc_guide)
            # 构建响应数据结构
            result = {
                'id': project_doc.id,
                'title': project_doc.title,
                'idea': project_doc.idea,
                'status': project_doc.status,
                'doc_guide': doc_guide_html,
                'industry': project_doc.industry,
                'created_at': project_doc.created_at.isoformat() if project_doc.created_at else None,
                'updated_at': project_doc.updated_at.isoformat() if project_doc.updated_at else None,
            }

            # 获取文档节点（章节结构）
            document_nodes = DocumentNode.query.filter_by(document_id=document_id) \
                .order_by(DocumentNode.level, DocumentNode.order_num, DocumentNode.node_id) \
                .all()

            # 构建树形结构
            node_dict = {}
            root_nodes = []

            # 第一遍：将所有节点存入字典
            for node in document_nodes:
                node_dict[node.id] = {
                    'id': node.id,
                    'node_id': node.node_id,
                    'level': node.level,
                    'title': node.title,
                    'key_point': node.key_point,
                    'content': node.content,
                    'parent_id': node.parent_id,
                    'order_num': node.order_num,
                    'review_score': node.review_score,
                    'review_detail': node.review_detail,
                    'status': node.status,
                    'created_at': node.created_at.isoformat() if node.created_at else None,
                    'updated_at': node.updated_at.isoformat() if node.updated_at else None,
                    'children': []
                }

            # 第二遍：建立父子关系
            for node_id, node_data in node_dict.items():
                parent_id = node_data['parent_id']
                if parent_id and parent_id in node_dict:
                    node_dict[parent_id]['children'].append(node_data)
                else:
                    root_nodes.append(node_data)

            # 按order_num和node_id对children排序
            for node_id, node_data in node_dict.items():
                node_data['children'].sort(key=lambda x: (x['order_num'], x['node_id']))

            # 对根节点排序
            root_nodes.sort(key=lambda x: (x['order_num'], x['node_id']))

            result['outline'] = root_nodes

            # 获取附件列表
            attachments = DocumentAttachment.query.filter_by(document_id=document_id).all()
            result['attachments'] = [
                {
                    'id': att.id,
                    'filename': att.filename,
                    'file_url': att.file_url,
                    'mime_type': att.mime_type,
                    'file_size': att.file_size,
                    'is_in_knowledge_base': att.is_in_knowledge_base,
                    'created_at': att.created_at.isoformat() if att.created_at else None
                }
                for att in attachments
            ]

            # 获取改进草稿（只获取未合并的）
            improvement_drafts = ImprovementDraft.query.filter_by(
                document_id=document_id,
                is_merged=False
            ).all()

            result['improvement_drafts'] = [
                {
                    'id': draft.id,
                    'node_id': draft.node_id,
                    'session_id': draft.session_id,
                    'source_type': draft.source_type,
                    'content': draft.content,
                    'help_text': draft.help_text,
                    'is_selected': draft.is_selected,
                    'is_merged': draft.is_merged,
                    'created_at': draft.created_at.isoformat() if draft.created_at else None
                }
                for draft in improvement_drafts
            ]

            # 如果需要包含历史任务记录
            if include_history:
                # 获取最近的任务记录
                recent_tasks = Task.query.filter_by(document_id=document_id) \
                    .order_by(Task.created_at.desc()) \
                    .limit(10) \
                    .all()

                result['recent_tasks'] = [
                    {
                        'id': task.id,
                        'task_uuid': task.task_uuid,
                        'task_type': task.task_type,
                        'status': task.status,
                        'progress': task.progress,
                        'started_at': task.started_at.isoformat() if task.started_at else None,
                        'completed_at': task.completed_at.isoformat() if task.completed_at else None,
                        'created_at': task.created_at.isoformat() if task.created_at else None
                    }
                    for task in recent_tasks
                ]

                # 获取最新的对话消息（用于恢复会话）
                recent_messages = ConversationMessage.query \
                    .join(Task, ConversationMessage.task_id == Task.id) \
                    .filter(Task.document_id == document_id) \
                    .order_by(ConversationMessage.created_at.desc()) \
                    .limit(20) \
                    .all()

                # 按会话分组
                session_messages = {}
                for msg in recent_messages:
                    if msg.session_id not in session_messages:
                        session_messages[msg.session_id] = []
                    session_messages[msg.session_id].append({
                        'message_id': msg.message_id,
                        'role': msg.role,
                        'message_type': msg.message_type,
                        'content': msg.content,
                        'attachment_paths': msg.attachment_paths,
                        'created_at': msg.created_at.isoformat() if msg.created_at else None
                    })

                # 反转每个会话的消息顺序，使其按时间正序排列
                for session_id, messages in session_messages.items():
                    session_messages[session_id] = sorted(messages, key=lambda x: x['created_at'])

                result['recent_conversations'] = session_messages

            return result

        except Exception as e:
            current_app.logger.error(f"获取项目文档失败: {str(e)}")
            return None

    @staticmethod
    def get_full_text_for_ai(document_id):
        """
        获取用于AI处理的完整文档文本

        Args:
            document_id: 文档ID

        Returns:
            list: 格式化的完整文档内容，用于AI处理
        """
        try:
            # 获取所有节点
            nodes = DocumentNode.query.filter_by(document_id=document_id) \
                .order_by(DocumentNode.level, DocumentNode.order_num, DocumentNode.node_id) \
                .all()

            # 构建层级结构
            chapter_nodes = {}
            section_nodes = {}

            for node in nodes:
                if node.level == 1:  # 一级章节
                    chapter_nodes[node.id] = {
                        'nodeId': str(node.node_id),
                        'title': node.title,
                        'level': node.level,
                        'children': []
                    }
                elif node.level == 2:  # 二级小节
                    section_nodes[node.id] = {
                        'nodeId': str(node.node_id),
                        'title': node.title,
                        'level': node.level,
                        'text': node.content or '',
                        'parent_id': node.parent_id
                    }

            # 将小节归入对应的章节
            for section_id, section_data in section_nodes.items():
                parent_id = section_data['parent_id']
                if parent_id in chapter_nodes:
                    chapter_nodes[parent_id]['children'].append(section_data)

            # 构建最终结构
            full_text = []
            for chapter_id, chapter_data in chapter_nodes.items():
                # 按nodeId排序子节点
                chapter_data['children'].sort(key=lambda x: x['nodeId'])
                full_text.append(chapter_data)

            # 按nodeId排序章节
            full_text.sort(key=lambda x: x['nodeId'])

            return full_text

        except Exception as e:
            current_app.logger.error(f"获取完整文档文本失败: {str(e)}")
            return []

    @staticmethod
    def get_section_content(document_id, node_id):
        """
        获取特定章节/小节的内容或全量节点信息

        Args:
            document_id: 文档ID
            node_id: 节点ID（如"1"或"1.1"），或"all"表示获取全量节点

        Returns:
            dict: 章节内容或全量节点信息
        """
        try:
            # 获取文档基本信息
            project_doc = ProjectDocument.query.filter_by(id=document_id).first()
            if not project_doc:
                return None

            # 如果是获取全量节点
            if node_id == 'all':
                # 获取所有一级节点（章节）
                chapter_nodes = DocumentNode.query.filter_by(
                    document_id=document_id,
                    level=1
                ).order_by(DocumentNode.order_num, DocumentNode.node_id).all()

                nodes_tree = []

                for chapter in chapter_nodes:
                    chapter_data = {
                        'nodeId': chapter.node_id,
                        'level': chapter.level,
                        'title': chapter.title,
                        'keyPoint': chapter.key_point,
                        'content': chapter.content,
                        'reviewScore': chapter.review_score,
                        'reviewDetail': chapter.review_detail,
                        'status': chapter.status,
                        'businessLevel': chapter.business_level,
                        'businessDescribe': chapter.business_describe,
                        'suggestion': chapter.suggestion,
                        'evaluate': chapter.evaluate,
                        'idealScore': chapter.ideal_score,
                        'children': []
                    }

                    # 获取该章节的所有子节点（小节）
                    child_nodes = DocumentNode.query.filter_by(
                        document_id=document_id,
                        parent_id=chapter.id
                    ).order_by(DocumentNode.order_num, DocumentNode.node_id).all()

                    for child in child_nodes:
                        child_data = {
                            'nodeId': child.node_id,
                            'level': child.level,
                            'title': child.title,
                            'keyPoint': child.key_point,
                            'content': child.content,
                            'reviewScore': child.review_score,
                            'reviewDetail': child.review_detail,
                            'status': child.status,
                            'businessLevel': child.business_level,
                            'businessDescribe': child.business_describe,
                            'suggestion': child.suggestion,
                            'evaluate': child.evaluate,
                            'idealScore': child.ideal_score
                        }
                        chapter_data['children'].append(child_data)

                    nodes_tree.append(chapter_data)

                # 返回全量节点结构
                return {
                    'document_id': document_id,
                    'title': project_doc.title,
                    'industry': project_doc.industry,
                    'is_full_document': True,  # 标记为全量节点
                    'total_review_score': project_doc.total_review_score,
                    'total_review_content': project_doc.total_review_content,
                    'nodes': nodes_tree  # 将节点树放在nodes字段中
                }

            # 原逻辑：获取指定单个节点
            node = DocumentNode.query.filter_by(document_id=document_id, node_id=node_id).first()
            if not node:
                return None

            result = {
                'document_id': document_id,
                'title': project_doc.title,
                'industry': project_doc.industry,
                'is_full_document': False,  # 标记为非全量节点
                'node': {
                    'nodeId': node.node_id,
                    'level': node.level,
                    'title': node.title,
                    'keyPoint': node.key_point,
                    'content': node.content,
                    'reviewScore': node.review_score,
                    'reviewDetail': node.review_detail,
                    'status': node.status,
                    'businessLevel': node.business_level,
                    'businessDescribe': node.business_describe,
                    'suggestion': node.suggestion,
                    'evaluate': node.evaluate,
                    'idealScore': node.ideal_score
                }
            }

            # 如果是章节，获取所有子节点
            if node.level == 1:
                child_nodes = DocumentNode.query.filter_by(document_id=document_id, parent_id=node.id) \
                    .order_by(DocumentNode.order_num, DocumentNode.node_id) \
                    .all()

                result['node']['children'] = [
                    {
                        'nodeId': child.node_id,
                        'level': child.level,
                        'title': child.title,
                        'keyPoint': child.key_point,
                        'content': child.content,
                        'reviewScore': child.review_score,
                        'reviewDetail': child.review_detail,
                        'status': child.status,
                        'businessLevel': child.business_level,
                        'businessDescribe': child.business_describe,
                        'suggestion': child.suggestion,
                        'evaluate': child.evaluate,
                        'idealScore': child.ideal_score
                    }
                    for child in child_nodes
                ]

            return result

        except Exception as e:
            current_app.logger.error(f"获取章节内容失败: {str(e)}")
            return None

    @staticmethod
    def get_reviews_and_suggestions(document_id):
        """
        获取文档的所有评审和改进建议

        Args:
            document_id: 文档ID

        Returns:
            dict: 评审和改进建议数据
        """
        try:
            # 获取所有已评审的节点
            reviewed_nodes = DocumentNode.query.filter_by(
                document_id=document_id,
                status='reviewed'
            ).filter(DocumentNode.review_score.isnot(None)).all()

            # 获取所有改进草稿
            improvement_drafts = ImprovementDraft.query.filter_by(
                document_id=document_id,
                is_merged=False
            ).all()

            # 按节点分组改进草稿
            drafts_by_node = {}
            for draft in improvement_drafts:
                if draft.node_id not in drafts_by_node:
                    drafts_by_node[draft.node_id] = []

                drafts_by_node[draft.node_id].append({
                    'id': draft.id,
                    'session_id': draft.session_id,
                    'source_type': draft.source_type,
                    'content': draft.content,
                    'help_text': draft.help_text,
                    'is_selected': draft.is_selected,
                    'created_at': draft.created_at.isoformat() if draft.created_at else None
                })

            # 构建响应
            result = {
                'reviews': [],
                'suggestions': []
            }

            for node in reviewed_nodes:
                # 添加评审结果
                review_info = {
                    'node_id': node.node_id,
                    'title': node.title,
                    'level': node.level,
                    'score': node.review_score,
                    'detail': node.review_detail,
                    'status': node.status,
                    'updated_at': node.updated_at.isoformat() if node.updated_at else None
                }
                result['reviews'].append(review_info)

                # 添加该节点的改进建议
                if node.id in drafts_by_node:
                    for draft in drafts_by_node[node.id]:
                        suggestion = {
                            'node_id': node.node_id,
                            'node_title': node.title,
                            'draft_id': draft['id'],
                            'content': draft['content'],
                            'help_text': draft['help_text'],
                            'source_type': draft['source_type'],
                            'is_selected': draft['is_selected'],
                            'created_at': draft['created_at']
                        }
                        result['suggestions'].append(suggestion)

            return result

        except Exception as e:
            current_app.logger.error(f"获取评审和建议失败: {str(e)}")
            return {'reviews': [], 'suggestions': []}

    @staticmethod
    def get_industry_list():
        """
        获取行业列表

        Returns:
            list: 行业列表
        """
        try:
            industries = IndustryList.query.filter_by(is_active=True).all()
            return [
                {
                    'id': industry.id,
                    'name': industry.name,
                    'description': industry.description
                }
                for industry in industries
            ]
        except Exception as e:
            current_app.logger.error(f"获取行业列表失败: {str(e)}")
            return []

    @staticmethod
    def get_outline_rules():
        """
        获取大纲规则

        Returns:
            list: 大纲规则列表
        """
        try:
            rules = OutlineRules.query.order_by(OutlineRules.sort).all()
            return [
                {
                    'id': rule.id,
                    'title_num': rule.title_num,
                    'sort': rule.sort,
                    'content': rule.content
                }
                for rule in rules
            ]
        except Exception as e:
            current_app.logger.error(f"获取大纲规则失败: {str(e)}")
            return []

    @staticmethod
    def get_review_rules():
        """
        获取评审规则

        Returns:
            list: 评审规则列表
        """
        try:
            rules = ReviewRules.query.order_by(ReviewRules.sort).all()
            return [
                {
                    'id': rule.id,
                    'title_num': rule.title_num,
                    'sort': rule.sort,
                    'content': rule.content
                }
                for rule in rules
            ]
        except Exception as e:
            current_app.logger.error(f"获取评审规则失败: {str(e)}")
            return []

    @staticmethod
    def get_selected_drafts(document_id, node_id):
        """
        获取选中的草稿

        Args:
            document_id: 文档ID
            node_id: 节点ID

        Returns:
            list: 选中的草稿列表
        """
        try:
            drafts = ImprovementDraft.query.filter_by(
                document_id=document_id,
                node_id=node_id,
                is_selected=True,
                is_merged=False
            ).all()

            return [
                {
                    'id': draft.id,
                    'session_id': draft.session_id,
                    'source_type': draft.source_type,
                    'content': draft.content,
                    'help_text': draft.help_text,
                    'created_at': draft.created_at.isoformat() if draft.created_at else None
                }
                for draft in drafts
            ]
        except Exception as e:
            current_app.logger.error(f"获取选中草稿失败: {str(e)}")
            return []

    @staticmethod
    def get_id_by_document_and_node(document_id, node_id):
        """
        根据文档ID和节点标识符获取节点ID（主键）

        Args:
            document_id: 文档ID
            node_id: 节点标识符（如 "1", "1.1", "1.2" 等）

        Returns:
            int: 节点ID，如果未找到则返回 None
        """
        node = DocumentNode.query.filter_by(
            document_id=document_id,
            node_id=str(node_id)  # 确保 node_id 是字符串类型
        ).first()

        return node.id if node else None

