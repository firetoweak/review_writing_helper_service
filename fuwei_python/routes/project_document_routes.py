# routes/project_document_routes.py
import json
import os
import threading
import re
import time
from datetime import datetime

import requests
from flask import Blueprint, request, jsonify, current_app, g, render_template, Response, stream_with_context

from common.aliOss import aliOss
from conf.config import app_config
from models.project_document.model import ProjectDocument, DocumentAttachment, ImprovementDraft, DocumentNode, \
    KnowledgeBaseDocument, Task, OutlineRules, ConversationMessage
from services.ai_task_services import AITaskService
from services.project_document_services import ProjectDocumentService
from utils.file_handler import FileHandler
from conf.db import db
from services.upload_file_service import UploadFileService

project_document_bp = Blueprint('project_document', __name__)


# =========== 1. 行业特点识别 ===========
@project_document_bp.route('/industry', methods=['POST'])
def identify_industry():
    """识别行业特点"""
    try:
        data = request.json
        title = data.get('title')
        idea = data.get('idea', '')

        if not title:
            return jsonify({
                'code': 400,
                'message': '缺少标题参数',
                'data': None
            }), 400

        result = AITaskService.handle_industry_identification(title, idea)

        return jsonify({
            'code': 200,
            'message': '行业特点识别成功',
            'data': result
        })

    except Exception as e:
        current_app.logger.error(f"行业特点识别失败: {str(e)}")
        return jsonify({
            'code': 500,
            'message': f'识别失败: {str(e)}',
            'data': None
        }), 500


# =========== 2. 全文写作指导（大纲生成） ===========
@project_document_bp.route('/outline', methods=['POST'])
def generate_outline():
    """生成大纲"""
    try:
        user_id = g.user_id
        data = request.json

        # 验证必要参数
        if not data.get('title'):
            return jsonify({
                'code': 400,
                'message': '缺少标题参数',
                'data': None
            }), 400

        # 先识别行业特点
        industry = AITaskService.handle_industry_identification(
            data.get('title'),
            data.get('idea', '')
        )
        # 创建项目文档
        project_doc = ProjectDocument(
            user_id=user_id,
            title=data.get('title'),
            idea=data.get('idea', ''),
            industry=industry,
            status='draft',
            created_at=datetime.now()
        )

        db.session.add(project_doc)
        db.session.commit()

        # 处理附件
        attachments = data.get('attachments', [])
        atta_threads = []
        for attachment in attachments:
            # 保存附件记录
            cache = current_app.extensions.get('cache')
            thread = threading.Thread(target=UploadFileService.project_document_deal_att_markdown,args=(attachment,project_doc.id,cache,g.user_id))
            atta_threads.append(thread)
            thread.start()
        for thread in atta_threads:
            thread.join()
        # 调用AI服务生成大纲
        AITaskService.index_document_to_kb(project_doc.id)
        result = AITaskService.handle_outline_generation(project_doc.id, data, industry)

        return jsonify({
            'code': 200,
            'message': '大纲生成成功',
            'data': {
                'document_id': project_doc.id,
                'industry': industry,
                **result
            }
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"大纲生成失败: {str(e)}")
        return jsonify({
            'code': 500,
            'message': f'大纲生成失败: {str(e)}',
            'data': None
        }), 500


@project_document_bp.route('/outline/<int:document_id>/level-two-keypoints', methods=['POST'])
def generate_level_two_keypoints(document_id):
    """生成二级章节写作要点"""
    try:
        data = request.json
        node_id = data.get('node_id')

        if not node_id:
            return jsonify({
                'code': 400,
                'message': '缺少节点ID参数',
                'data': None
            }), 400

        # 验证文档所有权
        project_doc = ProjectDocument.query.filter_by(
            id=document_id,
            user_id=g.user_id,
            deleted_at=None
        ).first()

        if not project_doc:
            return jsonify({
                'code': 404,
                'message': '文档不存在或无权访问',
                'data': None
            }), 404

        result = AITaskService.handle_level_two_keypoints(
            document_id, node_id, project_doc.industry
        )

        return jsonify({
            'code': 200,
            'message': '二级章节写作要点生成成功',
            'data': result
        })

    except Exception as e:
        current_app.logger.error(f"生成二级章节写作要点失败: {str(e)}")
        return jsonify({
            'code': 500,
            'message': f'生成失败: {str(e)}',
            'data': None
        }), 500


@project_document_bp.route('/<int:document_id>/writing-workspace', methods=['GET'])
def get_writing_workspace_data(document_id):
    """获取写作工作区页面所需的数据"""
    try:
        user_id = g.user_id

        # 验证文档所有权
        project_doc = ProjectDocument.query.filter_by(
            id=document_id,
            user_id=user_id,
            deleted_at=None
        ).first()

        if not project_doc:
            return jsonify({
                'code': 404,
                'message': '文档不存在或无权访问',
                'data': None
            }), 404

        # 获取文档大纲数据
        document_nodes = DocumentNode.query.filter_by(document_id=document_id) \
            .order_by(DocumentNode.level, DocumentNode.order_num, DocumentNode.node_id) \
            .all()

        # 构建大纲数据
        outline_data = {
            'title': project_doc.title,
            'chapters': []
        }

        # 组织章节结构
        chapter_nodes = {}
        for node in document_nodes:
            if node.level == 1:  # 一级章节
                if node.id not in chapter_nodes:
                    chapter_nodes[node.id] = {
                        'id': node.node_id,
                        'name': node.title,
                        'key_point': node.key_point,
                        'sections': []
                    }
            elif node.level == 2:  # 二级小节
                parent_id = node.parent_id
                if parent_id in chapter_nodes:
                    section_data = {
                        'id': node.node_id,
                        'title': node.title,
                        'key_point': node.key_point,
                        'content': node.content,
                        'review_score': node.review_score,
                        'review_detail': node.review_detail,
                        'status': node.status,
                        'subsections': []
                    }
                    # 查找三级子节点
                    subsections = DocumentNode.query.filter_by(
                        document_id=document_id,
                        parent_id=node.id,
                        level=3
                    ).order_by(DocumentNode.order_num).all()

                    for sub in subsections:
                        section_data['subsections'].append({
                            'id': sub.node_id,
                            'title': sub.title,
                            'key_point': sub.key_point,
                            'content': sub.content
                        })

                    chapter_nodes[parent_id]['sections'].append(section_data)

        # 转换为列表
        for chapter in chapter_nodes.values():
            outline_data['chapters'].append(chapter)

        # 获取当前激活的章节（默认为第一个章节的第一个小节）
        active_section = None
        if outline_data['chapters'] and outline_data['chapters'][0]['sections']:
            first_chapter = outline_data['chapters'][0]
            first_section = first_chapter['sections'][0]
            active_section = {
                'chapter_name': first_chapter['name'],
                'section_id': first_section['id'],
                'section_title': first_section['title']
            }

        # 获取编辑器数据
        editor_data = {
            'chapterTitle': '',
            'writingPoint': '',
            'sectionTitle': '',
            'paragraphs': []
        }

        if active_section:
            # 查找对应的文档节点
            section_node = DocumentNode.query.filter_by(
                document_id=document_id,
                node_id=active_section['section_id']
            ).first()

            if section_node:
                editor_data = {
                    'chapterTitle': f"{active_section['chapter_name']} {active_section['section_title']}",
                    'writingPoint': section_node.key_point or '暂无写作要点',
                    'sectionTitle': f"{active_section['section_id']} {active_section['section_title']}",
                    'paragraphs': [section_node.content] if section_node.content else ['请开始写作...']
                }

        # 获取评审数据
        review_data = {
            'score': section_node.review_score if section_node else 0,
            'maxScore': 10,
            'suggestions': []
        }

        if section_node and section_node.review_detail:
            # 解析评审详情
            suggestions = section_node.review_detail.split('\n')
            review_data['evaluate'] = suggestions[0]
            if len(suggestions) > 1:
                review_data['suggestions'] = suggestions[1]
        # 获取改进草稿数据
        improvement_drafts = ImprovementDraft.query.filter_by(
            document_id=document_id,
            is_merged=False
        ).order_by(ImprovementDraft.created_at.desc()).limit(5).all()

        notes_data = []
        for draft in improvement_drafts:
            notes_data.append({
                'id': draft.id,
                'summary': draft.help_text[:20] + '...' if draft.help_text else '改进草稿',
                'dialogMessages': [
                    {'type': 'user', 'text': draft.help_text or '我需要帮助'},
                    {'type': 'ai', 'text': draft.content or '这是AI的建议', 'hasReference': False}
                ],
                'timestamp': int(draft.created_at.timestamp() * 1000) if draft.created_at else 0
            })

        # 获取AI话题数据（可以从数据库或配置中获取）
        ai_topics_data = [
            {'type': '润色', 'text': '帮我文字润色', 'isFirst': True},
            {'type': '打分', 'text': '帮我进行AI评审打分', 'isFirst': False},
            {'text': '帮我进行AI评审打分', 'isFirst': False}
        ]

        # 获取历史对话数据
        tasks = Task.query.filter_by(
            document_id=document_id,
        ).order_by(Task.created_at.desc()).limit(3).all()

        history_data = []
        for task in tasks:
            if task.response_data:
                history_data.append({
                    'text': task.response_data.get('summary', '对话记录')[:30] + '...'
                })

        # 获取附件数据
        attachments = DocumentAttachment.query.filter_by(
            document_id=document_id,
            is_in_knowledge_base = 1
        ).all()

        material_data = []
        for attachment in attachments:
            material_data.append({
                'name': attachment.filename[:15] + '...' if len(attachment.filename) > 15 else attachment.filename,
                'icon': '/static/project_document/images/common/icon-file-doc.png',# 根据文件类型返回不同的图标
                'file_url': f"https://{app_config['ali_bucket']}.{app_config['ali_endpoint']}/{attachment.file_url}",
                "file_name":attachment.file_url,
                "file_id":attachment.id
            })

        # 快捷操作数据
        quick_actions_data = [
            {'text': '帮我润色', 'isEdit': False},
            {'text': '帮我打分', 'isEdit': False},
            {'text': '帮我写作', 'isEdit': False},
            {'text': '编辑对话', 'isEdit': True}
        ]

        return jsonify({
            'code': 200,
            'message': 'success',
            'data': {
                'outlineData': outline_data,
                'editorData': editor_data,
                'reviewData': review_data,
                'notesData': notes_data,
                'aiTopicsData': ai_topics_data,
                'historyData': history_data,
                'materialData': material_data,
                'quickActionsData': quick_actions_data,
                'chapterPointsTemplate': f'<div class="flex-col mt-space-seventeen"><span class="editor-text editor-text-justify">{section_node.key_point if section_node else "暂无写作要点"}</span></div>'
            }
        })

    except Exception as e:
        current_app.logger.error(f"获取写作工作区数据失败: {str(e)}")
        return jsonify({
            'code': 500,
            'message': f'获取数据失败: {str(e)}',
            'data': None
        }), 500


@project_document_bp.route('/<int:document_id>/section/<string:node_id>', methods=['GET'])
def get_section_content(document_id, node_id):
    """获取指定节点的内容（支持章节和小节）"""
    try:
        user_id = g.user_id

        # 验证文档所有权
        project_doc = ProjectDocument.query.filter_by(
            id=document_id,
            user_id=user_id,
            deleted_at=None
        ).first()

        if not project_doc:
            return jsonify({
                'code': 404,
                'message': '文档不存在或无权访问',
                'data': None
            }), 404

        # 查找对应的文档节点
        section_node = DocumentNode.query.filter_by(
            document_id=document_id,
            node_id=node_id
        ).first()

        if not section_node:
            return jsonify({
                'code': 404,
                'message': '节点不存在',
                'data': None
            }), 404

        # 根据节点级别处理数据
        if section_node.level == 1:  # 一级节点（章节）
            chapter_node = section_node
            section_title = f"{section_node.node_id} {section_node.title}"
            # 对于一级节点，章节标题就是节点标题本身
            chapter_title = section_node.title
        elif section_node.level == 2:  # 二级节点（小节）
            # 查找父节点（章节）
            chapter_node = DocumentNode.query.get(section_node.parent_id) if section_node.parent_id else None
            section_title = f"{section_node.node_id} {section_node.title}"
            # 对于二级节点，章节标题是父节点标题
            chapter_title = f"{chapter_node.title if chapter_node else '章节'}"
        else:
            # 其他级别节点暂时不支持
            return jsonify({
                'code': 400,
                'message': '不支持的节点级别',
                'data': None
            }), 400

        # 解析评审建议数据
        try:
            review_data = {
                'evaluate': section_node.evaluate,
                'suggestions': json.loads(section_node.suggestion) if section_node.suggestion else []
            }
        except Exception as e:
            current_app.logger.warning(f"解析评审建议失败: {str(e)}")
            review_data = {
                'evaluate': section_node.evaluate,
                'suggestions': []
            }

        # 构建返回数据
        data = {
            'chapterTitle': chapter_title,
            'writingPoint': section_node.key_point or '暂无写作要点',
            'sectionTitle': section_title,
            'content': section_node.content or '请开始写作...',
            'review_score': section_node.review_score,
            'review_detail': section_node.review_detail,
            'review_data': review_data,
            'status': section_node.status,
            'level': section_node.level,  # 返回节点级别，方便前端识别
            'node_id': section_node.node_id,
            'title': section_node.title,
            'parent_id': section_node.parent_id  # 返回父节点ID
        }

        # 如果是二级节点，添加章节节点信息
        if section_node.level == 2 and chapter_node:
            data['chapter_info'] = {
                'chapter_node_id': chapter_node.node_id,
                'chapter_title': chapter_node.title,
                'chapter_content': chapter_node.content or ''
            }

        return jsonify({
            'code': 200,
            'message': 'success',
            'data': data
        })

    except Exception as e:
        current_app.logger.error(f"获取节点内容失败: {str(e)}")
        return jsonify({
            'code': 500,
            'message': f'获取数据失败: {str(e)}',
            'data': None
        }), 500

@project_document_bp.route('/<int:document_id>/section/<string:node_id>', methods=['POST'])
def save_section_content(document_id, node_id):
    """保存指定节点的内容"""
    try:
        user_id = g.user_id
        data = request.get_json()

        # 验证文档所有权
        project_doc = ProjectDocument.query.filter_by(
            id=document_id,
            user_id=user_id,
            deleted_at=None
        ).first()

        if not project_doc:
            return jsonify({
                'code': 404,
                'message': '文档不存在或无权访问',
                'data': None
            }), 404

        # 查找对应的文档节点
        section_node = DocumentNode.query.filter_by(
            document_id=document_id,
            node_id=node_id
        ).first()

        if not section_node:
            return jsonify({
                'code': 404,
                'message': '节点不存在',
                'data': None
            }), 404

        # 检查是否有任何字段实际发生变化
        has_changes = False
        current_time = datetime.now()

        if 'content' in data:
            # 判断内容是否实际变更
            current_content = section_node.content or ""
            new_content = data['content'] or ""
            if current_content != new_content:
                section_node.content = data['content']
                has_changes = True

        if 'key_point' in data:
            # 判断关键点是否实际变更
            current_key_point = section_node.key_point or ""
            new_key_point = data['key_point'] or ""
            if current_key_point != new_key_point:
                section_node.key_point = data['key_point']
                has_changes = True

        if 'status' in data:
            # 判断状态是否实际变更
            current_status = section_node.status or ""
            new_status = data['status'] or ""
            if current_status != new_status:
                section_node.status = data['status']
                has_changes = True

        # 如果没有实际变化，直接返回成功
        if not has_changes:
            return jsonify({
                'code': 200,
                'message': '内容无变化',
                'data': {
                    'node_id': section_node.node_id,
                    'title': section_node.title,
                    'updated_at': section_node.updated_at.isoformat(),
                    'no_change': True  # 添加标记表示没有实际更新
                }
            })

        # 只有有变化时才更新时间和提交到数据库
        section_node.updated_at = current_time
        project_doc.updated_at = current_time
        db.session.commit()

        return jsonify({
            'code': 200,
            'message': '保存成功',
            'data': {
                'node_id': section_node.node_id,
                'title': section_node.title,
                'updated_at': section_node.updated_at.isoformat()
            }
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"保存节点内容失败: {str(e)}")
        return jsonify({
            'code': 500,
            'message': f'保存失败: {str(e)}',
            'data': None
        }), 500


# =========== 3. 启发式写作 ===========
@project_document_bp.route('/heuristic-writing/start', methods=['POST'])
def start_heuristic_writing():
    """开始启发式写作"""
    # try:
    data = request.json
    document_id = data.get('document_id')
    node_id = data.get('node_id')
    session_id = str(int(time.time() * 100000)) + str(g.user_id)
    text = data.get('text', '')

    if not all([document_id, node_id]):
        return jsonify({
            'code': 400,
            'message': '缺少必要参数',
            'data': None
        }), 400

    # 验证文档所有权
    project_doc = ProjectDocument.query.filter_by(
        id=document_id,
        user_id=g.user_id,
        deleted_at=None
    ).first()

    if not project_doc:
        return jsonify({
            'code': 404,
            'message': '文档不存在或无权访问',
            'data': None
        }), 404
    #AITaskService.handle_heuristic_writing(document_id, node_id, session_id, text)
    response = Response(stream_with_context(AITaskService.handle_heuristic_writing(document_id, node_id, session_id, text)),
                        mimetype='text/event-stream; charset=utf-8')
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['Connection'] = 'keep-alive'
    response.headers['X-Accel-Buffering'] = 'no'  # 禁用反向代理缓冲
    return response

    # return jsonify({
    #     'code': 200,
    #     'message': '启发式写作已启动',
    #     'data': result
    # })

    # except Exception as e:
    #     current_app.logger.error(f"启动启发式写作失败: {str(e)}")
    #     return jsonify({
    #         'code': 500,
    #         'message': f'启动失败: {str(e)}',
    #         'data': None
    #     }), 500


@project_document_bp.route('/heuristic-writing/response', methods=['POST'])
def handle_heuristic_response():
    """处理启发式写作的用户回复"""
    try:
        data = request.json
        document_id = data.get('document_id')
        node_id = data.get('node_id')
        session_id = data.get('session_id')
        messages = data.get('messages', [])
        attachment = data.get('attachment',{})
        message_id = f"m_u_{int(time.time())}{g.user_id}"

        if not all([document_id, node_id, session_id, messages]):
            return jsonify({
                'code': 400,
                'message': '缺少必要参数',
                'data': None
            }), 400

        # 验证文档所有权
        project_doc = ProjectDocument.query.filter_by(
            id=document_id,
            user_id=g.user_id,
            deleted_at=None
        ).first()

        if not project_doc:
            return jsonify({
                'code': 404,
                'message': '文档不存在或无权访问',
                'data': None
            }), 404
        cache = current_app.extensions.get('cache')
        # if attachment:
        #     mark_down_text,image_url = UploadFileService.ai_deal(g.user_id, attachment, cache, document_id)
        #     attachments = [{"text":mark_down_text,"image_url":image_url}]
        # else:
        #     attachments = []
        response = Response(
            stream_with_context(AITaskService.handle_heuristic_response(document_id, node_id, session_id, messages, attachment,message_id)),
            mimetype='text/event-stream; charset=utf-8')
        response.headers['Cache-Control'] = 'no-cache'
        response.headers['Connection'] = 'keep-alive'
        response.headers['X-Accel-Buffering'] = 'no'  # 禁用反向代理缓冲
        return response
    except Exception as e:
        current_app.logger.error(f"处理启发式回复失败: {str(e)}")
        return jsonify({
            'code': 500,
            'message': f'处理失败: {str(e)}',
            'data': None
        }), 500


# =========== 4. AI自动评审 ===========
@project_document_bp.route('/review/section', methods=['POST'])
def review_section():
    """评审章节/小节"""
    try:
        data = request.json
        document_id = data.get('document_id')
        node_id = data.get('node_id')
        if not all([document_id, node_id]):
            return jsonify({
                'code': 400,
                'message': '缺少必要参数',
                'data': None
            }), 400
        # 验证文档所有权
        project_doc = ProjectDocument.query.filter_by(
            id=document_id,
            user_id=g.user_id,
            deleted_at=None
        ).first()

        if not project_doc:
            return jsonify({
                'code': 404,
                'message': '文档不存在或无权访问',
                'data': None
            }), 404

        #
        # review_data = {
        #                 "score": "10",
        #                 "business_level": "level_1",
        #                 "ideal_score": "",
        #             "evaluate": "当前正文内容仅为占位符'11111111111111111111'，未提供任何实质内容。根据评审规则，1.4节要求对相似产品进行成功与不足的复盘，必须包含标杆选择关联度、成败归因深度、客观性与批判性、启示录与机会输入四个维度的分析。当前内容完全缺失，无法满足核心及格线要求。例如，未选择任何历史产品作为复盘对象，未进行任何归因分析，未提供数据支撑，也未输出继承点与改进点。在商业价值层面，该部分内容对后续产品定义无任何输入价值，属于完全无效的‘空壳’章节。因此，商业价值评级为Level 1（最低级），写作质量实际得分为0分。",
        #             "suggestion": [
        #                 "立即替换占位符内容，选择公司内部在技术、市场或场景上高度相关的现有产品（如上一代机器人产品或类似智能硬件）进行复盘，确保标杆选择具有强关联性。",
        #                 "对所选产品的成功与不足进行深度归因，必须关联到1.2节中客户痛点与场景，避免表面化描述，如‘销售不给力’或‘用户体验差’等无效归因。",
        #                 "必须同时呈现‘成功’与‘不足’，并用具体数据（如销量、退货率、NPS、活跃度）支撑，杜绝主观形容词，展现批判性思维。",
        #                 "在复盘结论中明确列出‘继承点（Keep）’和‘改进点（Fix/Drop）’，确保内容能直接作为新产品定义的输入材料，避免逻辑断层。",
        #                 "若当前无直接相似产品，需拆解能力模块（如感知算法、人机交互、供应链响应等），跨产品线复盘关键能力的复用性与短板，体现战略思维。"
        #             ],
        #             "to_do_list": [
        #                 "我能帮你设计一套复盘框架，包含标杆选择、归因分析、数据支撑、启示输出四个模块，确保结构完整。",
        #                 "我能帮你构建竞品分析的对比维度，如技术参数、用户反馈、渠道表现等，用于支撑复盘结论。",
        #                 "我能帮你润色这段文字的商业语气，使其更符合IPD文档的严谨与战略表达要求。",
        #                 "我能帮你检查逻辑是否自洽，确保复盘内容与1.2节客户痛点形成闭环。",
        #                 "我能为你提供一个数据填空模板（包含销量、退货率、NPS等维度），并给出一个假设性的参考范围（仅作逻辑演示），供你调研时参考。"
        #             ]
        # }
        # return jsonify({
        #     'code': 200,
        #     'message': '评审完成',
        #     'data': {
        #         "taskId": "task_bfb8bf96af00477a",
        #         "review": review_data
        #     }
        # })


        result = AITaskService.handle_section_review(document_id, node_id)

        return jsonify({
            'code': 200,
            'message': '评审完成',
            'data': result
        })

    except Exception as e:
        current_app.logger.error(f"章节评审失败: {str(e)}")
        return jsonify({
            'code': 500,
            'message': f'评审失败: {str(e)}',
            'data': None
        }), 500


# =========== 5. "我能帮你"交互 ===========
@project_document_bp.route('/help/start', methods=['POST'])
def start_help_session():
    """开始"我能帮你"会话"""
    try:
        data = request.json
        document_id = data.get('document_id')
        node_id = data.get('node_id')
        help_text = data.get('help_text')
        session_id = data.get('session_id')
        # session_id = "help_"+str(int(time.time() * 100000)) + str(g.user_id) # session_id 从前端传入

        if not all([document_id, node_id, help_text]):
            return jsonify({
                'code': 400,
                'message': '缺少必要参数',
                'data': None
            }), 400

        # 验证文档所有权
        project_doc = ProjectDocument.query.filter_by(
            id=document_id,
            user_id=g.user_id,
            deleted_at=None
        ).first()

        if not project_doc:
            return jsonify({
                'code': 404,
                'message': '文档不存在或无权访问',
                'data': None
            }), 404

        #result = AITaskService.handle_help_session(document_id, node_id, session_id, help_text)

        response = Response(
            stream_with_context(AITaskService.handle_help_session(document_id, node_id, session_id, help_text)),
            mimetype='text/event-stream; charset=utf-8')
        response.headers['Cache-Control'] = 'no-cache'
        response.headers['Connection'] = 'keep-alive'
        response.headers['X-Accel-Buffering'] = 'no'  # 禁用反向代理缓冲
        return response
        return jsonify({
            'code': 200,
            'message': '帮助会话已启动',
            'data': result
        })
    except Exception as e:
        current_app.logger.error(f"启动帮助会话失败: {str(e)}")
        return jsonify({
            'code': 500,
            'message': f'启动失败: {str(e)}',
            'data': None
        }), 500


@project_document_bp.route('/help/response', methods=['POST'])
def handle_help_response():
    """处理"我能帮你"的用户回复"""
    try:
        data = request.json
        document_id = data.get('document_id','')
        node_id = data.get('node_id','')
        session_id = data.get('session_id','')
        message = data.get('message', "")
        message_id = f"m_u_{int(time.time())}{g.user_id}"
        attachment = data.get('attachment', {})
        if not all([document_id, node_id, session_id, message,message_id]):
            return jsonify({
                'code': 400,
                'message': '缺少必要参数',
                'data': None
            }), 400

        # 验证文档所有权
        project_doc = ProjectDocument.query.filter_by(
            id=document_id,
            user_id=g.user_id,
            deleted_at=None
        ).first()

        if not project_doc:
            return jsonify({
                'code': 404,
                'message': '文档不存在或无权访问',
                'data': None
            }), 404

        #result = AITaskService.handle_help_session_response( document_id, node_id, session_id, message,attachment,g.user_id,message_id)
        response = Response(
            stream_with_context(AITaskService.handle_help_session_response(document_id, node_id, session_id, message,attachment,g.user_id,message_id)),
            mimetype='text/event-stream; charset=utf-8')
        response.headers['Cache-Control'] = 'no-cache'
        response.headers['Connection'] = 'keep-alive'
        response.headers['X-Accel-Buffering'] = 'no'  # 禁用反向代理缓冲
        return response

        return jsonify({
            'code': 200,
            'message': '处理成功',
            'data': result
        })

    except Exception as e:
        current_app.logger.error(f"处理帮助回复失败: {str(e)}")
        return jsonify({
            'code': 500,
            'message': f'处理失败: {str(e)}',
            'data': None
        }), 500


# =========== 6. 一键合入 ===========
@project_document_bp.route('/merge', methods=['POST'])
def merge_drafts():
    """一键合入草稿"""
    try:
        data = request.json
        document_id = data.get('document_id')
        node_id = data.get('node_id')
        draft_ids = data.get('draft_ids', [])
        if not all([document_id, node_id,draft_ids]):
            return jsonify({
                'code': 400,
                'message': '缺少必要参数',
                'data': None
            }), 400

        # 验证文档所有权
        project_doc = ProjectDocument.query.filter_by(
            id=document_id,
            user_id=g.user_id,
            deleted_at=None
        ).first()

        if not project_doc:
            return jsonify({
                'code': 404,
                'message': '文档不存在或无权访问',
                'data': None
            }), 404

        result = AITaskService.handle_merge(document_id, node_id, draft_ids)
        db.session.commit()
        return jsonify({
            'code': 200,
            'message': '合入完成',
            'data': result
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"一键合入失败: {str(e)}")
        return jsonify({
            'code': 500,
            'message': f'合入失败: {str(e)}',
            'data': None
        }), 500


# =========== 7. 全文评审 ===========
@project_document_bp.route('/review/full', methods=['POST'])
def review_full():
    """全文评审"""
    try:
        data = request.json
        document_id = data.get('document_id')
        if not document_id:
            return jsonify({
                'code': 400,
                'message': '缺少文档ID',
                'data': None
            }), 400

        # 验证文档所有权
        project_doc = ProjectDocument.query.filter_by(
            id=document_id,
            user_id=g.user_id,
            deleted_at=None
        ).first()

        if not project_doc:
            return jsonify({
                'code': 404,
                'message': '文档不存在或无权访问',
                'data': None
            }), 404

        result = AITaskService.handle_full_review(document_id,project_doc)

        # 检查是否是部分评审
        # if result.get('status') == 'partial':
        #     return jsonify({
        #         'code': 200,
        #         'message': result.get('message', ''),
        #         'data': result
        #     })

        return jsonify({
            'code': 200,
            'message': '全文评审完成',
            'data': result
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"全文评审失败: {str(e)}")
        return jsonify({
            'code': 500,
            'message': f'评审失败: {str(e)}',
            'data': None
        }), 500


# =========== 8. 全文AI润色 ===========
@project_document_bp.route('/polish/full', methods=['POST'])
def polish_full():
    """全文AI润色"""
    try:
        data = request.json
        document_id = data.get('document_id')

        if not document_id:
            return jsonify({
                'code': 400,
                'message': '缺少文档ID',
                'data': None
            }), 400

        # 验证文档所有权
        project_doc = ProjectDocument.query.filter_by(
            id=document_id,
            user_id=g.user_id,
            deleted_at=None
        ).first()

        if not project_doc:
            return jsonify({
                'code': 404,
                'message': '文档不存在或无权访问',
                'data': None
            }), 404

        result = AITaskService.handle_full_polish(document_id)

        return jsonify({
            'code': 200,
            'message': '全文润色完成',
            'data': result
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"全文润色失败: {str(e)}")
        return jsonify({
            'code': 500,
            'message': f'润色失败: {str(e)}',
            'data': None
        }), 500


# =========== 9. 评审立项报告（新文件） ===========
@project_document_bp.route('/review/new-file', methods=['POST'])
def review_new_file():
    """评审新上传的立项报告"""
    try:
        user_id = g.user_id
        file = request.files.get('file')
        project_id = request.form.get('project_id')

        if not file:
            return jsonify({
                'code': 400,
                'message': '请上传文件',
                'data': None
            }), 400

        # 保存文件
        file_path = FileHandler.save_uploaded_file(file, user_id)

        # 处理文件结构化重组
        result = AITaskService.handle_text_restruct(file_path, project_id)

        # 创建新的项目文档
        project_doc = ProjectDocument(
            user_id=user_id,
            title=file.filename,
            status='reviewing',
            doc_guide=result.get('docGuide', ''),
            created_at=datetime.now()
        )

        db.session.add(project_doc)
        db.session.flush()

        # 创建文档节点
        outline_data = result.get('outline', [])
        full_text = result.get('fullText', [])

        # 先创建所有一级章节
        chapter_nodes = {}
        for i, chapter_data in enumerate(outline_data):
            chapter_node = DocumentNode(
                document_id=project_doc.id,
                node_id=chapter_data['nodeId'],
                level=1,
                title=chapter_data['title'],
                key_point=chapter_data.get('keyPoint', ''),
                order_num=i,
                status='reviewed',  # 新文件直接标记为已评审
                created_at=datetime.now()
            )
            db.session.add(chapter_node)
            db.session.flush()
            chapter_nodes[chapter_data['nodeId']] = chapter_node

        # 创建二级小节并关联内容
        for chapter_data in full_text:
            chapter_node = chapter_nodes.get(chapter_data['nodeId'])
            if chapter_node:
                for j, section_data in enumerate(chapter_data.get('children', [])):
                    section_node = DocumentNode(
                        document_id=project_doc.id,
                        node_id=section_data['nodeId'],
                        level=2,
                        title=section_data['title'],
                        key_point=section_data.get('keyPoint', ''),
                        content=section_data.get('text', ''),
                        parent_id=chapter_node.id,
                        order_num=j,
                        status='reviewed',
                        created_at=datetime.now()
                    )
                    db.session.add(section_node)

        db.session.commit()

        return jsonify({
            'code': 200,
            'message': '文件评审完成',
            'data': {
                'document_id': project_doc.id,
                'doc_guide': result.get('docGuide'),
                'outline': outline_data,
                'full_text': full_text
            }
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"评审新文件失败: {str(e)}")
        return jsonify({
            'code': 500,
            'message': f'评审失败: {str(e)}',
            'data': None
        }), 500


# =========== 10. 知识库管理 --暂时没用===========
@project_document_bp.route('/knowledge/documents', methods=['POST'])
def add_knowledge_document():
    """添加知识库文档"""
    try:
        user_id = g.user_id
        file = request.files.get('file')
        project_id = request.form.get('project_id')
        collection_id = request.form.get('collection_id')

        if not file:
            return jsonify({
                'code': 400,
                'message': '请上传文件',
                'data': None
            }), 400

        # 保存文件
        file_path = FileHandler.save_uploaded_file(file, user_id)

        # 索引到知识库
        kb_doc = AITaskService.index_document_to_kb(
            user_id=user_id,
            file_path=file_path,
            filename=file.filename,
            project_id=project_id,
            collection_id=collection_id
        )

        if kb_doc and kb_doc.status == 'indexed':
            return jsonify({
                'code': 200,
                'message': '文档已成功添加到知识库',
                'data': {
                    'document_id': kb_doc.id,
                    'filename': kb_doc.filename,
                    'status': kb_doc.status,
                    'chunk_count': kb_doc.chunk_count
                }
            })
        else:
            error_reason = kb_doc.error_reason if kb_doc else '未知错误'
            return jsonify({
                'code': 500,
                'message': f'文档索引失败: {error_reason}',
                'data': None
            }), 500

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"添加知识库文档失败: {str(e)}")
        return jsonify({
            'code': 500,
            'message': f'添加失败: {str(e)}',
            'data': None
        }), 500


@project_document_bp.route('/knowledge/documents/<int:document_id>', methods=['DELETE'])
def delete_knowledge_document(document_id):
    """删除知识库文档"""
    try:
        user_id = g.user_id

        # 验证文档所有权
        kb_doc = KnowledgeBaseDocument.query.filter_by(
            id=document_id,
            user_id=user_id
        ).first()

        if not kb_doc:
            return jsonify({
                'code': 404,
                'message': '文档不存在或无权访问',
                'data': None
            }), 404

        success = AITaskService.delete_document_from_kb(document_id)

        if success:
            return jsonify({
                'code': 200,
                'message': '文档已删除',
                'data': None
            })
        else:
            return jsonify({
                'code': 500,
                'message': '删除失败',
                'data': None
            }), 500

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"删除知识库文档失败: {str(e)}")
        return jsonify({
            'code': 500,
            'message': f'删除失败: {str(e)}',
            'data': None
        }), 500


# =========== 11. 悬浮球 ===========
@project_document_bp.route('/float', methods=['POST'])
def handle_float_ball():
    """处理悬浮球请求"""
    try:
        data = request.json
        title = data.get('title')
        text = data.get('text')
        target_text = data.get('targetText')
        user_input = data.get('userInput')

        if not all([title, text, user_input]):
            return jsonify({
                'code': 400,
                'message': '缺少必要参数',
                'data': None
            }), 400

        result = AITaskService.handle_float_ball(title, text, target_text, user_input)

        return jsonify({
            'code': 200,
            'message': '悬浮球处理成功',
            'data': result
        })

    except Exception as e:
        current_app.logger.error(f"悬浮球处理失败: {str(e)}")
        return jsonify({
            'code': 500,
            'message': f'处理失败: {str(e)}',
            'data': None
        }), 500


# =========== 工具接口 ===========
@project_document_bp.route('/tasks/<string:task_uuid>/status', methods=['GET'])
def get_task_status(task_uuid):
    """获取任务状态"""
    try:
        task = Task.query.filter_by(task_uuid=task_uuid).first()

        if not task:
            return jsonify({
                'code': 404,
                'message': '任务不存在',
                'data': None
            }), 404

        # 验证权限（通过文档所有权）
        if task.document_id:
            project_doc = ProjectDocument.query.get(task.document_id)
            if project_doc and project_doc.user_id != g.user_id:
                return jsonify({
                    'code': 403,
                    'message': '无权访问此任务',
                    'data': None
                }), 403

        return jsonify({
            'code': 200,
            'message': 'success',
            'data': {
                'task_uuid': task.task_uuid,
                'task_type': task.task_type,
                'status': task.status,
                'progress': task.progress,
                'response_data': task.response_data,
                'error_message': task.error_message,
                'started_at': task.started_at.isoformat() if task.started_at else None,
                'completed_at': task.completed_at.isoformat() if task.completed_at else None
            }
        })

    except Exception as e:
        current_app.logger.error(f"获取任务状态失败: {str(e)}")
        return jsonify({
            'code': 500,
            'message': f'获取失败: {str(e)}',
            'data': None
        }), 500


@project_document_bp.route('/drafts/<int:draft_id>/select', methods=['PUT'])
def select_draft(draft_id):
    """选择/取消选择草稿"""
    try:
        data = request.json
        is_selected = data.get('is_selected', True)

        draft = ImprovementDraft.query.get(draft_id)
        if not draft:
            return jsonify({
                'code': 404,
                'message': '草稿不存在',
                'data': None
            }), 404

        # 验证权限
        project_doc = ProjectDocument.query.get(draft.document_id)
        if project_doc.user_id != g.user_id:
            return jsonify({
                'code': 403,
                'message': '无权操作此草稿',
                'data': None
            }), 403

        draft.is_selected = is_selected
        draft.updated_at = datetime.now()

        db.session.commit()

        return jsonify({
            'code': 200,
            'message': '操作成功',
            'data': {'is_selected': is_selected}
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"选择草稿失败: {str(e)}")
        return jsonify({
            'code': 500,
            'message': f'操作失败: {str(e)}',
            'data': None
        }), 500


@project_document_bp.route('', methods=['GET'])
def get_user_projects():
    """获取用户的所有项目文档"""
    try:
        user_id = g.user_id

        # 分页参数
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        status = request.args.get('status', None)

        # 构建查询
        query = ProjectDocument.query.filter_by(user_id=user_id, deleted_at=None)

        if status:
            query = query.filter_by(status=status)

        # 执行分页查询
        pagination = query.order_by(ProjectDocument.updated_at.desc()) \
            .paginate(page=page, per_page=per_page, error_out=False)

        projects = pagination.items

        # 构建响应
        result = {
            'projects': [
                {
                    'id': project.id,
                    'title': project.title,
                    'status': project.status,
                    'idea': project.idea,
                    'industry': project.industry,
                    'doc_guide': project.doc_guide,
                    'created_at': project.created_at.isoformat() if project.created_at else None,
                    'updated_at': project.updated_at.isoformat() if project.updated_at else None
                }
                for project in projects
            ],
            'pagination': {
                'page': pagination.page,
                'per_page': pagination.per_page,
                'total': pagination.total,
                'pages': pagination.pages
            }
        }

        return jsonify({
            'code': 200,
            'message': 'success',
            'data': result
        })

    except Exception as e:
        current_app.logger.error(f"获取用户项目失败: {str(e)}")
        return jsonify({
            'code': 500,
            'message': f'获取项目列表失败: {str(e)}',
            'data': None
        }), 500


@project_document_bp.route('/<int:document_id>', methods=['GET'])
def get_project_document(document_id):
    """获取完整的项目文档"""
    try:
        user_id = g.user_id

        # 验证文档所有权
        project_doc = ProjectDocument.query.filter_by(id=document_id, user_id=user_id, deleted_at=None).first()
        if not project_doc:
            return jsonify({
                'code': 404,
                'message': '文档不存在或无权访问',
                'data': None
            }), 404

        # 获取完整文档数据
        include_history = request.args.get('include_history', 'false').lower() == 'true'
        complete_document = ProjectDocumentService.get_complete_project_document(document_id, include_history)

        if not complete_document:
            return jsonify({
                'code': 500,
                'message': '获取文档数据失败',
                'data': None
            }), 500

        return jsonify({
            'code': 200,
            'message': 'success',
            'data': complete_document
        })

    except Exception as e:
        current_app.logger.error(f"获取项目文档失败: {str(e)}")
        return jsonify({
            'code': 500,
            'message': f'获取文档失败: {str(e)}',
            'data': None
        }), 500


@project_document_bp.route('/<int:document_id>/full-text', methods=['GET'])
def get_full_text(document_id):
    """获取用于AI处理的完整文档文本"""
    try:
        user_id = g.user_id

        # 验证文档所有权
        project_doc = ProjectDocument.query.filter_by(id=document_id, user_id=user_id, deleted_at=None).first()
        if not project_doc:
            return jsonify({
                'code': 404,
                'message': '文档不存在或无权访问',
                'data': None
            }), 404

        # 获取完整文本
        full_text = ProjectDocumentService.get_full_text_for_ai(document_id)

        return jsonify({
            'code': 200,
            'message': 'success',
            'data': {
                'document_id': document_id,
                'title': project_doc.title,
                'industry': project_doc.industry,
                'fullText': full_text
            }
        })

    except Exception as e:
        current_app.logger.error(f"获取完整文本失败: {str(e)}")
        return jsonify({
            'code': 500,
            'message': f'获取完整文本失败: {str(e)}',
            'data': None
        }), 500

@project_document_bp.route('/<int:document_id>/section-content/<string:node_id>', methods=['GET'])
def get_section_content_via_service(document_id, node_id):
    """通过Service获取 特定章节、小节或 全量节点 的内容"""
    try:
        user_id = g.user_id

        # 验证文档所有权
        project_doc = ProjectDocument.query.filter_by(
            id=document_id,
            user_id=user_id,
            deleted_at=None
        ).first()

        if not project_doc:
            return jsonify({
                'code': 404,
                'message': '文档不存在或无权访问',
                'data': None
            }), 404

        # 调用Service方法
        section_content = ProjectDocumentService.get_section_content(document_id, node_id)

        if not section_content:
            return jsonify({
                'code': 404,
                'message': '章节内容不存在',
                'data': None
            }), 404

        return jsonify({
            'code': 200,
            'message': 'success',
            'data': section_content
        })

    except Exception as e:
        current_app.logger.error(f"获取章节内容失败: {str(e)}")
        return jsonify({
            'code': 500,
            'message': f'获取章节内容失败: {str(e)}',
            'data': None
        }), 500


@project_document_bp.route('/<int:document_id>/reviews', methods=['GET'])
def get_reviews_and_suggestions(document_id):
    """获取文档的所有评审和改进建议"""
    try:
        user_id = g.user_id

        # 验证文档所有权
        project_doc = ProjectDocument.query.filter_by(id=document_id, user_id=user_id, deleted_at=None).first()
        if not project_doc:
            return jsonify({
                'code': 404,
                'message': '文档不存在或无权访问',
                'data': None
            }), 404

        # 获取评审和建议
        reviews_data = ProjectDocumentService.get_reviews_and_suggestions(document_id)

        return jsonify({
            'code': 200,
            'message': 'success',
            'data': reviews_data
        })

    except Exception as e:
        current_app.logger.error(f"获取评审和建议失败: {str(e)}")
        return jsonify({
            'code': 500,
            'message': f'获取评审和建议失败: {str(e)}',
            'data': None
        }), 500


@project_document_bp.route('/industry/list', methods=['GET'])
def get_industry_list():
    """获取行业列表"""
    try:
        industries = ProjectDocumentService.get_industry_list()

        return jsonify({
            'code': 200,
            'message': 'success',
            'data': industries
        })

    except Exception as e:
        current_app.logger.error(f"获取行业列表失败: {str(e)}")
        return jsonify({
            'code': 500,
            'message': f'获取行业列表失败: {str(e)}',
            'data': None
        }), 500


@project_document_bp.route('/rules/outline', methods=['GET'])
def get_outline_rules():
    """获取大纲规则"""
    try:
        rules = ProjectDocumentService.get_outline_rules()

        return jsonify({
            'code': 200,
            'message': 'success',
            'data': rules
        })

    except Exception as e:
        current_app.logger.error(f"获取大纲规则失败: {str(e)}")
        return jsonify({
            'code': 500,
            'message': f'获取大纲规则失败: {str(e)}',
            'data': None
        }), 500


@project_document_bp.route('/rules/review', methods=['GET'])
def get_review_rules():
    """获取评审规则"""
    try:
        rules = ProjectDocumentService.get_review_rules()

        return jsonify({
            'code': 200,
            'message': 'success',
            'data': rules
        })

    except Exception as e:
        current_app.logger.error(f"获取评审规则失败: {str(e)}")
        return jsonify({
            'code': 500,
            'message': f'获取评审规则失败: {str(e)}',
            'data': None
        }), 500


@project_document_bp.route('/<int:document_id>/export', methods=['GET'])
def export_project_document(document_id):
    """导出完整的产品立项报告（多种格式）"""
    try:
        user_id = g.user_id

        # 验证文档所有权
        project_doc = ProjectDocument.query.filter_by(id=document_id, user_id=user_id, deleted_at=None).first()
        if not project_doc:
            return jsonify({
                'code': 404,
                'message': '文档不存在或无权访问',
                'data': None
            }), 404

        # 获取完整文档数据
        complete_document = ProjectDocumentService.get_complete_project_document(document_id, False)

        if not complete_document:
            return jsonify({
                'code': 500,
                'message': '获取文档数据失败',
                'data': None
            }), 500

        # 确定导出格式
        export_format = request.args.get('format', 'json')

        if export_format == 'markdown':
            # 转换为Markdown格式
            markdown_content = convert_to_markdown(complete_document)

            return jsonify({
                'code': 200,
                'message': 'success',
                'data': {
                    'format': 'markdown',
                    'content': markdown_content,
                    'filename': f"{project_doc.title.replace(' ', '_')}.md"
                }
            })

        elif export_format == 'html':
            # 转换为HTML格式
            html_content = convert_to_html(complete_document)

            return jsonify({
                'code': 200,
                'message': 'success',
                'data': {
                    'format': 'html',
                    'content': html_content,
                    'filename': f"{project_doc.title.replace(' ', '_')}.html"
                }
            })

        else:  # 默认JSON格式
            return jsonify({
                'code': 200,
                'message': 'success',
                'data': {
                    'format': 'json',
                    'content': complete_document,
                    'filename': f"{project_doc.title.replace(' ', '_')}.json"
                }
            })

    except Exception as e:
        current_app.logger.error(f"导出文档失败: {str(e)}")
        return jsonify({
            'code': 500,
            'message': f'导出文档失败: {str(e)}',
            'data': None
        }), 500


def convert_to_markdown(document_data):
    """将文档数据转换为Markdown格式"""
    markdown_lines = []

    # 添加标题
    markdown_lines.append(f"# {document_data['title']}\n")

    # 添加行业特点
    if document_data.get('industry'):
        markdown_lines.append(f"**行业**: {document_data['industry']}\n")

    # 添加项目构想
    if document_data.get('idea'):
        markdown_lines.append("## 项目构想")
        markdown_lines.append(f"{document_data['idea']}\n")

    # 添加写作指导
    if document_data.get('doc_guide'):
        markdown_lines.append("## 写作指导")
        markdown_lines.append(f"{document_data['doc_guide']}\n")

    # 递归添加章节内容
    def add_node_to_markdown(node, depth):
        indent = "#" * (depth + 1)  # 一级章节用##，二级小节用###
        markdown_lines.append(f"{indent} {node['title']}\n")

        # 添加写作要点
        if node.get('key_point'):
            markdown_lines.append(f"**写作要点**: {node['key_point']}\n")

        # 添加正文内容
        if node.get('content'):
            markdown_lines.append(f"{node['content']}\n")

        # 添加评审分数
        if node.get('review_score') is not None:
            markdown_lines.append(f"**评审分数**: {node['review_score']}/10\n")

        # 添加评审详情
        if node.get('review_detail'):
            markdown_lines.append(f"**评审详情**: {node['review_detail']}\n")

        # 递归处理子节点
        for child in node.get('children', []):
            add_node_to_markdown(child, depth + 1)

    # 添加所有章节
    for chapter in document_data.get('outline', []):
        add_node_to_markdown(chapter, 1)  # 从##开始

    return "\n".join(markdown_lines)


def convert_to_html(document_data):
    """将文档数据转换为HTML格式"""
    html_lines = []

    html_lines.append('<!DOCTYPE html>')
    html_lines.append('<html lang="zh-CN">')
    html_lines.append('<head>')
    html_lines.append('    <meta charset="UTF-8">')
    html_lines.append('    <meta name="viewport" content="width=device-width, initial-scale=1.0">')
    html_lines.append(f'    <title>{document_data["title"]}</title>')
    html_lines.append('    <style>')
    html_lines.append(
        '        body { font-family: "Microsoft YaHei", Arial, sans-serif; line-height: 1.6; max-width: 800px; margin: 0 auto; padding: 20px; }')
    html_lines.append('        h1 { color: #333; border-bottom: 2px solid #4CAF50; padding-bottom: 10px; }')
    html_lines.append('        h2 { color: #555; margin-top: 30px; }')
    html_lines.append('        h3 { color: #666; margin-top: 20px; }')
    html_lines.append('        .industry { color: #666; font-style: italic; margin-bottom: 20px; }')
    html_lines.append(
        '        .key-point { background-color: #f0f8ff; padding: 10px; border-left: 4px solid #4CAF50; margin: 10px 0; }')
    html_lines.append('        .review-score { color: #ff9800; font-weight: bold; }')
    html_lines.append(
        '        .review-detail { background-color: #fff8e1; padding: 10px; border-radius: 5px; margin: 10px 0; }')
    html_lines.append('        .content { margin: 15px 0; }')
    html_lines.append('    </style>')
    html_lines.append('</head>')
    html_lines.append('<body>')

    # 添加标题
    html_lines.append(f'    <h1>{document_data["title"]}</h1>')

    # 添加行业特点
    if document_data.get('industry'):
        html_lines.append(f'    <div class="industry">行业: {document_data["industry"]}</div>')

    # 添加项目构想
    if document_data.get('idea'):
        html_lines.append('    <h2>项目构想</h2>')
        html_lines.append(f'    <div class="content">{document_data["idea"]}</div>')

    # 添加写作指导
    if document_data.get('doc_guide'):
        html_lines.append('    <h2>写作指导</h2>')
        html_lines.append(f'    <div class="content">{document_data["doc_guide"]}</div>')

    # 递归添加章节内容
    def add_node_to_html(node, depth):
        tag = f'h{depth + 1}'  # h2, h3, etc.
        html_lines.append(f'    <{tag}>{node["title"]}</{tag}>')

        # 添加写作要点
        if node.get('key_point'):
            html_lines.append(f'    <div class="key-point"><strong>写作要点:</strong> {node["key_point"]}</div>')

        # 添加正文内容
        if node.get('content'):
            html_lines.append(f'    <div class="content">{node["content"]}</div>')

        # 添加评审分数
        if node.get('review_score') is not None:
            html_lines.append(f'    <div class="review-score">评审分数: {node["review_score"]}/10</div>')

        # 添加评审详情
        if node.get('review_detail'):
            html_lines.append(
                f'    <div class="review-detail"><strong>评审详情:</strong> {node["review_detail"]}</div>')

        # 递归处理子节点
        for child in node.get('children', []):
            add_node_to_html(child, depth + 1)

    # 添加所有章节
    for chapter in document_data.get('outline', []):
        add_node_to_html(chapter, 1)  # 从h2开始

    html_lines.append('</body>')
    html_lines.append('</html>')

    return "\n".join(html_lines)


@project_document_bp.route('/upload', methods=['POST'])
def upload_file():
    """上传文件接口"""
    try:
        user_id = g.user_id
        if 'file' not in request.files:
            return jsonify({
                'code': 400,
                'message': '没有选择文件',
                'data': None
            }), 400

        file = request.files['file']

        if file.filename == '':
            return jsonify({
                'code': 400,
                'message': '没有选择文件',
                'data': None
            }), 400

        # 验证文件类型
        allowed_extensions = ['ppt', 'pptx', 'doc', 'docx', 'pdf']
        if '.' in file.filename:
            file_ext = file.filename.rsplit('.', 1)[1].lower()
        else:
            file_ext = ''

        # 如果文件名没有扩展名，检查MIME类型
        if not file_ext and file.content_type:
            mime_to_ext = {
                'application/pdf': 'pdf',
                'application/msword': 'doc',
                'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
                'application/vnd.ms-powerpoint': 'ppt',
                'application/vnd.openxmlformats-officedocument.presentationml.presentation': 'pptx'
            }
            file_ext = mime_to_ext.get(file.content_type, '')

        if file_ext not in allowed_extensions:
            return jsonify({
                'code': 400,
                'message': '不支持的文件格式，仅支持PPT、Word、PDF文件',
                'data': None
            }), 400

        # 验证文件大小（100MB限制）
        file.seek(0, 2)  # 移动到文件末尾
        file_size = file.tell()
        file.seek(0)  # 重置文件指针

        if file_size > 100 * 1024 * 1024:
            return jsonify({
                'code': 400,
                'message': '文件大小超过100MB限制',
                'data': None
            }), 400

        # 使用FileHandler保存文件
        try:
            key, url,file_info = UploadFileService.upload_files(file, f"{user_id}")
        except Exception as e:
            current_app.logger.error(f"保存文件失败: {str(e)}")
            return jsonify({
                'code': 500,
                'message': f'保存文件失败: {str(e)}',
                'data': None
            }), 500
        if '.' in file.filename:
            original_name_without_ext = file.filename.rsplit('.', 1)[0]
        else:
            original_name_without_ext = file.filename
        return jsonify({
            'code': 200,
            'message': '文件上传成功',
            'data': {
                'name': original_name_without_ext,  # 原始文件名（不含扩展名）
                'original_name': file.filename,  # 原始完整文件名
                'url': url,
                'file_path': key,
                'unique_name': os.path.basename(key),
                'mimeType': file_info['mime_type'],
                'size': file_info['file_size'],
                'uploaded_at': datetime.now().isoformat()
            }
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"文件上传失败: {str(e)}")
        return jsonify({
            'code': 500,
            'message': f'文件上传失败: {str(e)}',
            'data': None
        }), 500

@project_document_bp.route('/<int:document_id>/material_upload', methods=['POST'])
def material_upload_file(document_id):
    try:
        user_id = g.user_id
        project_doc = ProjectDocument.query.filter_by(
            id=document_id,
            user_id=user_id,
            deleted_at=None
        ).first()
        if not project_doc:
            return jsonify({
                'code': 404,
                'message': '文档不存在或无权访问',
                'data': None
            }), 404
        res = upload_file()
        file = res.json
        cache = current_app.extensions.get('cache')
        data = file['data']
        data['key'] = file['data']['file_path']
        UploadFileService.project_document_deal_att_markdown(data, project_doc.id, cache, g.user_id)
        # 调用AI服务生成大纲
        AITaskService.index_document_to_kb(project_doc.id)
        return res
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"素材文件上传失败: {str(e)}")
        return jsonify({
            'code': 500,
            'message': f'素材文件上传失败: {str(e)}',
            'data': None
        }), 500


@project_document_bp.route('/delete-file', methods=['DELETE'])
def delete_file():
    """删除文件接口"""
    try:
        user_id = g.user_id
        data = request.json
        file_path = data.get('file_path')
        file_url = data.get('url')

        if not file_path and not file_url:
            return jsonify({
                'code': 400,
                'message': '缺少文件路径或文件URL',
                'data': None
            }), 400
        aliOss.deleteFile(file_path)
        return jsonify({
            'code': 200,
            'message': '文件删除成功',
            'data': {
                'file_path': file_path,
                'deleted': True
            }
        })

        # 优先使用file_path
        # if not file_path and file_url:
        #     # 从URL中提取文件路径
        #     if file_url.startswith('/static/'):
        #         # 将URL转换为文件系统路径
        #         relative_path = file_url[8:]  # 去掉'/static/'
        #         static_dir = os.path.join(current_app.root_path, 'static')
        #         file_path = os.path.join(static_dir, relative_path)
        #     else:
        #         return jsonify({
        #             'code': 400,
        #             'message': '无效的文件URL格式',
        #             'data': None
        #         }), 400
        #
        # # 验证文件路径是否在允许的目录内（防止路径遍历攻击）
        # upload_dir = current_app.config.get('UPLOAD_FOLDER', 'static/uploads')
        # if not os.path.abspath(file_path).startswith(os.path.abspath(upload_dir)):
        #     return jsonify({
        #         'code': 403,
        #         'message': '无权删除此文件',
        #         'data': None
        #     }), 403
        #
        # # 验证文件是否存在
        # if not os.path.exists(file_path):
        #     return jsonify({
        #         'code': 404,
        #         'message': '文件不存在',
        #         'data': None
        #     }), 404
        #
        # # 使用FileHandler删除文件
        # success = FileHandler.delete_file(file_path)
        #
        # if success:
        #     return jsonify({
        #         'code': 200,
        #         'message': '文件删除成功',
        #         'data': {
        #             'file_path': file_path,
        #             'deleted': True
        #         }
        #     })
        # else:
        #     return jsonify({
        #         'code': 500,
        #         'message': '删除文件失败',
        #         'data': None
        #     }), 500

    except Exception as e:
        current_app.logger.error(f"删除文件接口失败: {str(e)}")
        return jsonify({
            'code': 500,
            'message': f'删除失败: {str(e)}',
            'data': None
        }), 500

@project_document_bp.route('/material-delete-file', methods=['DELETE'])
def material_delete_file():
    try:
        data = request.json
        project_doc = ProjectDocument.query.filter_by(id=data['document_id'],user_id=g.user_id,deleted_at=None).first()
        if not project_doc:
            return jsonify({
                'code': 404,
                'message': '文档不存在或无权访问',
                'data': None
            }), 404
        attach = DocumentAttachment.query.filter_by(id=data['file_id'],document_id=data['document_id']).first()
        if not attach:
            return jsonify({
                'code': 404,
                'message': '素材文件不存在',
                'data': None
            }), 404
        try:
            payload = {
                "action": "delete",
                "projectId": f"{data['document_id']}",
                "document_id": f"{data['file_id']}"
            }
            headers = {
                "Content-Type": "application/json",
                "Authorization": "Bearer token123"
            }
            response = None
            response = requests.post(
                f"{app_config['ai_server']}/api/kb/documents",
                json=payload,
                headers=headers,
                timeout=600
            )
            data = response.json()
            print(data)
            if data['status'] == 'deleted':
                DocumentAttachment.query.filter(DocumentAttachment.id==attach.id).delete()
                db.session.commit()
                return jsonify({
                    'code': 200,
                    'message':"删除成功",
                    'data': None
                }),200
            else:
                return jsonify({
                    'code': 500,
                    'message': f'删除失败',
                    'data': None
                }), 500
        except Exception as e:
            current_app.logger.info_module(
                f"知识库删除异常-material_delete_file：{e},文件：{e.__traceback__.tb_frame.f_globals['__file__']};行数：{e.__traceback__.tb_lineno}",
                "model")
            if response is not None and response.content:
                current_app.logger.info_module(f"respones:{response.content.decode('utf-8')}", "model")
            return jsonify({
                'code': 500,
                'message': f'删除失败: {str(e)}',
                'data': None
            }), 500
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"素材文件删除失败: {str(e)}")
        return jsonify({
            'code': 500,
            'message': f'删除失败: {str(e)}',
            'data': None
        }), 500



@project_document_bp.route('/<int:document_id>/preview-data', methods=['GET'])
def get_preview_data(document_id):
    """获取预览页面数据"""
    try:
        user_id = g.user_id

        # 验证文档所有权
        project_doc = ProjectDocument.query.filter_by(
            id=document_id,
            user_id=user_id,
            deleted_at=None
        ).first()

        if not project_doc:
            return jsonify({
                'code': 404,
                'message': '文档不存在或无权访问',
                'data': None
            }), 404

        # 获取文档节点
        document_nodes = DocumentNode.query.filter_by(
            document_id=document_id
        ).order_by(DocumentNode.level, DocumentNode.order_num).all()

        # 组织章节结构
        chapters = []
        chapter_nodes = {}

        # 先找出所有一级章节
        for node in document_nodes:
            if node.level == 1:
                chapter_node = {
                    'id': node.id,
                    'node_id': node.node_id,
                    'title': node.title,
                    'name': node.node_id,
                    'sections': []
                }
                chapter_nodes[node.id] = chapter_node
                chapters.append(chapter_node)

        # 找出所有二级小节并归到对应的章节
        for node in document_nodes:
            if node.level == 2:
                parent_chapter = chapter_nodes.get(node.parent_id)
                if parent_chapter:
                    section_data = {
                        'id': node.node_id,
                        'title': node.title,
                        'content': node.content or '暂无内容',
                        'key_point': node.key_point,
                        'review_score': node.review_score,
                        'review_detail': node.review_detail,
                        'status': node.status
                    }
                    parent_chapter['sections'].append(section_data)

        # 计算总字数
        total_words = 0
        for node in document_nodes:
            if node.content:
                # 简单的中文字数统计（中文字符算1个，英文字母算0.5个）
                chinese_count = len(re.findall(r'[\u4e00-\u9fff]', node.content))
                english_count = len(re.findall(r'[a-zA-Z]', node.content))
                total_words += chinese_count + english_count * 0.5

        # 构建返回数据
        preview_data = {
            'title': project_doc.title,
            'wordCount': int(total_words),
            'industry': project_doc.industry,
            'idea': project_doc.idea,
            'doc_guide': project_doc.doc_guide,
            'status': project_doc.status,
            'created_at': project_doc.created_at.strftime('%Y-%m-%d %H:%M:%S') if project_doc.created_at else None,
            'updated_at': project_doc.updated_at.strftime('%Y-%m-%d %H:%M:%S') if project_doc.updated_at else None,
            'chapters': chapters
        }

        return jsonify({
            'code': 200,
            'message': 'success',
            'data': preview_data
        })

    except Exception as e:
        current_app.logger.error(f"获取预览数据失败: {str(e)}")
        return jsonify({
            'code': 500,
            'message': f'获取数据失败: {str(e)}',
            'data': None
        }), 500


@project_document_bp.route('/<int:document_id>/section-content', methods=['PUT'])
def update_section_content(document_id):
    """更新章节内容"""
    try:
        user_id = g.user_id
        data = request.json

        section_id = data.get('section_id')
        content = data.get('content')

        if not all([section_id, content]):
            return jsonify({
                'code': 400,
                'message': '缺少必要参数',
                'data': None
            }), 400

        # 验证文档所有权
        project_doc = ProjectDocument.query.filter_by(
            id=document_id,
            user_id=user_id,
            deleted_at=None
        ).first()

        if not project_doc:
            return jsonify({
                'code': 404,
                'message': '文档不存在或无权访问',
                'data': None
            }), 404

        # 查找对应的文档节点
        document_node = DocumentNode.query.filter_by(
            document_id=document_id,
            node_id=section_id
        ).first()

        if not document_node:
            return jsonify({
                'code': 404,
                'message': '章节不存在',
                'data': None
            }), 404

        # 更新内容
        document_node.content = content
        document_node.updated_at = datetime.now()
        document_node.status = 'completed'  # 标记为已完成

        db.session.commit()

        return jsonify({
            'code': 200,
            'message': '保存成功',
            'data': {
                'section_id': section_id,
                'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"更新章节内容失败: {str(e)}")
        return jsonify({
            'code': 500,
            'message': f'保存失败: {str(e)}',
            'data': None
        }), 500

@project_document_bp.route('/<int:document_id>/full-text-data', methods=['GET'])
def full_text_data(document_id):
    '''
    获取全文评审数据
    '''
    project = ProjectDocument.query.filter_by(id=document_id,user_id=g.user_id).first()
    if not project:
        return jsonify({
            'code': 404,
            'message': '项目不存在',
            'data': None
        }), 404
    nodes = DocumentNode.query.filter_by(document_id=document_id,level=1).order_by(DocumentNode.node_id.asc()).all()
    chapters = {"1":"机会识别视角","2":"产品定位视角","3":"产品包定义视角","4":"路径与壁垒视角","5":"投资收益视角"}
    return {
        "data":{
        "title":project.title,
        "total_review_score":project.total_review_score,
        "total_review_content":project.total_review_content,
        "steps":[{"suggestion":node.suggestion,"evaluate":node.evaluate,"review_score":node.review_score,"chapter_title":chapters[node.node_id]} for node in nodes]
        },
        "code":200
    }

@project_document_bp.route('/outline-draft', methods=['GET'])
def outline_draft():
    """填写构想页面"""
    return render_template('project_document/outline-draft.html')


@project_document_bp.route('/outline-confirm/<int:document_id>', methods=['GET'])
def outline_confirm(document_id):
    """大纲确认页面"""
    try:
        user_id = g.user_id

        # 验证文档所有权
        project_doc = ProjectDocument.query.filter_by(
            id=document_id,
            user_id=user_id,
            deleted_at=None
        ).first()

        if not project_doc:
            return "文档不存在或无权访问", 404

        return render_template('project_document/outline-confirm.html')

    except Exception as e:
        current_app.logger.error(f"访问大纲确认页面失败: {str(e)}")
        return "页面加载失败", 500


@project_document_bp.route('/writing-workspace/<int:document_id>', methods=['GET'])
def writing_workspace(document_id):
    """写作工作区页面"""
    try:
        user_id = g.user_id

        # 验证文档所有权
        project_doc = ProjectDocument.query.filter_by(
            id=document_id,
            user_id=user_id,
            deleted_at=None
        ).first()

        if not project_doc:
            return "文档不存在或无权访问", 404

        return render_template('project_document/writing-workspace.html',document_id=document_id)

    except Exception as e:
        current_app.logger.error(f"访问写作工作区页面失败: {str(e)}")
        return "页面加载失败", 500


@project_document_bp.route('/ai-review-report/<int:document_id>', methods=['GET'])
def ai_review_report(document_id):
    """AI评审报告页面"""
    try:
        user_id = g.user_id

        # 验证文档所有权
        project_doc = ProjectDocument.query.filter_by(
            id=document_id,
            user_id=user_id,
            deleted_at=None
        ).first()

        if not project_doc:
            return "文档不存在或无权访问", 404

        return render_template('project_document/ai-review-report.html')

    except Exception as e:
        current_app.logger.error(f"访问AI评审报告页面失败: {str(e)}")
        return "页面加载失败", 500

@project_document_bp.route('/full-compare/<int:document_id>', methods=['GET'])
def full_compare(document_id):
    """全文对比页面"""
    try:
        user_id = g.user_id

        # 验证文档所有权
        project_doc = ProjectDocument.query.filter_by(
            id=document_id,
            user_id=user_id,
            deleted_at=None
        ).first()

        if not project_doc:
            return "文档不存在或无权访问", 404

        # 获取URL参数（可选）
        node_id = request.args.get('node_id')
        tree_data_json = request.args.get('tree_data')

        # 如果需要，可以解析tree_data
        tree_data = None
        if tree_data_json:
            try:
                tree_data = json.loads(tree_data_json)
            except:
                tree_data = None

        return render_template('project_document/full-compare.html',
                               document_id=document_id,
                               node_id=node_id,
                               tree_data=tree_data)


    except Exception as e:
        current_app.logger.error(f"访问全文对比页面失败: {str(e)}")
        return "页面加载失败", 500

@project_document_bp.route('/preview-review/<int:document_id>', methods=['GET'])
def preview_review(document_id):
    """全文对比页面"""
    try:
        user_id = g.user_id

        # 验证文档所有权
        project_doc = ProjectDocument.query.filter_by(
            id=document_id,
            user_id=user_id,
            deleted_at=None
        ).first()

        if not project_doc:
            return "文档不存在或无权访问", 404

        return render_template('project_document/preview-review.html')

    except Exception as e:
        current_app.logger.error(f"访问全文预览页面失败: {str(e)}")
        return "页面加载失败", 500

@project_document_bp.route('/full-text-review/<int:document_id>', methods=['GET'])
def full_text_review(document_id):
    """全文评审结果"""
    try:
        user_id = g.user_id
        # 验证文档所有权
        project_doc = ProjectDocument.query.filter_by(
            id=document_id,
            user_id=user_id,
            deleted_at=None
        ).first()

        if not project_doc:
            return "文档不存在或无权访问", 404

        return render_template('project_document/full-text-review.html')

    except Exception as e:
        current_app.logger.error(f"访问全文预览页面失败: {str(e)}")
        return "页面加载失败", 500


@project_document_bp.route('/ai-collab/<int:document_id>', methods=['GET'])
def ai_collab(document_id):
    """AI协作页面"""
    try:
        user_id = g.user_id

        # 验证文档所有权
        project_doc = ProjectDocument.query.filter_by(
            id=document_id,
            user_id=user_id,
            deleted_at=None
        ).first()

        if not project_doc:
            return "文档不存在或无权访问", 404

        return render_template('project_document/ai-collab.html')

    except Exception as e:
        current_app.logger.error(f"访问AI协作页面失败: {str(e)}")
        return "页面加载失败", 500

@project_document_bp.route('/test_ai',methods=['POST'])
def ai_deal_file():
    try:
        record_id = 0
        g.user_id = 0
        file_keys = ['README202601141708330.md']
        for file_key in  file_keys:
            cache = current_app.extensions.get('cache')
            cache.setdefault(str(g.user_id) + "upload_state" + str(record_id), "uploading")
            mark_down_text = UploadFileService.ai_deal(g.user_id, file_key, cache, record_id, from_type="project_document")
            print(mark_down_text)
            return mark_down_text
    except Exception as e:
        print(e)
        return ""


# =========== 更新AI回复消息 ===========
@project_document_bp.route('/conversation-messages/update', methods=['PUT'])
def update_conversation_message():
    """更新AI回复消息内容"""
    try:
        user_id = g.user_id
        data = request.json

        document_id = data.get('document_id')
        session_id = data.get('session_id')
        message_id = data.get('message_id')
        content = data.get('content')

        if not all([document_id, session_id, message_id, content]):
            return jsonify({
                'code': 400,
                'message': '缺少必要参数',
                'data': None
            }), 400

        # 验证文档所有权
        project_doc = ProjectDocument.query.filter_by(
            id=document_id,
            user_id=user_id,
            deleted_at=None
        ).first()

        if not project_doc:
            return jsonify({
                'code': 404,
                'message': '文档不存在或无权访问',
                'data': None
            }), 404

        # 查找对应的对话消息
        conversation_message = ConversationMessage.query.filter_by(
            session_id=session_id,
            message_id=message_id,
            role='assistant'
        ).first()

        if not conversation_message:
            return jsonify({
                'code': 404,
                'message': 'AI回复消息不存在',
                'data': None
            }), 404

        # 验证消息所属的任务是否属于该文档
        task = Task.query.get(conversation_message.task_id)
        if not task or task.document_id != document_id:
            return jsonify({
                'code': 403,
                'message': '无权更新此消息',
                'data': None
            }), 403

        # 更新消息内容
        conversation_message.content = content
        conversation_message.updated_at = datetime.now()

        db.session.commit()

        return jsonify({
            'code': 200,
            'message': 'AI回复已更新',
            'data': {
                'session_id': session_id,
                'message_id': message_id,
                'updated_at': conversation_message.updated_at.isoformat()
            }
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"更新AI回复失败: {str(e)}")
        return jsonify({
            'code': 500,
            'message': f'更新失败: {str(e)}',
            'data': None
        }), 500


# =========== AI出谋划策  新增、删除对话消息、加入估计笔记、获取改进笔记、获取改进笔记对应的对话消息   ===========
@project_document_bp.route('/conversation-messages', methods=['POST'])
def add_conversation_message():
    """新增对话消息"""
    current_app.logger.debug('==========添加对话消息=========')
    try:
        user_id = g.user_id
        data = request.json

        # 验证必要参数 - 更新为包含node_id
        required_fields = ['document_id', 'node_id', 'session_id', 'message_id', 'role', 'content']
        for field in required_fields:
            if not data.get(field):
                return jsonify({
                    'code': 400,
                    'message': f'缺少必要参数: {field}',
                    'data': None
                }), 400

        # 验证文档所有权
        project_doc = ProjectDocument.query.filter_by(
            id=data.get('document_id'),
            user_id=user_id,
            deleted_at=None
        ).first()

        if not project_doc:
            return jsonify({
                'code': 404,
                'message': '文档不存在或无权访问',
                'data': None
            }), 404

        # 获取节点信息
        node = DocumentNode.query.filter_by(
            document_id=data.get('document_id'),
            node_id=data.get('node_id')
        ).first()

        if not node:
            return jsonify({
                'code': 404,
                'message': '节点不存在',
                'data': None
            }), 404

        # 创建任务（参考help接口的任务创建逻辑）
        task_type = data.get('task_type', 'conversation')  # 默认为conversation类型
        request_data = {
            'node_id': data.get('node_id'),
            'session_id': data.get('session_id'),
            'message': data.get('content'),
            'role': data.get('role')
        }

        # 处理附件（如果有）
        if data.get('attachment'):
            attachment = data.get('attachment')
            if 'key' in attachment and '.' in attachment['key']:
                file_ext = attachment['key'].rsplit('.', 1)[1].lower()
            else:
                file_ext = ''

            if file_ext not in ["jpg", "jpeg", "png", "webp", "bmp", "doc", "docx", "pdf", ""]:
                raise Exception("文件格式错误")

            attachments = []
            if file_ext in ["doc", "docx", "pdf"]:
                cache = current_app.extensions.get('cache')
                mark_down_text, image_url = UploadFileService.ai_deal(user_id, attachment, cache,
                                                                      data.get('document_id'))
            elif file_ext in ["jpg", "jpeg", "png", "webp", "bmp"]:
                image_url = {f"IMAGE_{str(int(time.time() * 100000)) + str(user_id)}": attachment['file_url']}
                mark_down_text = ""

            if file_ext in ["jpg", "jpeg", "png", "webp", "bmp", "doc", "docx", "pdf"]:
                # 保存附件到数据库
                attach = DocumentAttachment(
                    document_id=data.get('document_id'),
                    filename=attachment['name'],
                    file_url=attachment['file_url'],
                    is_admin=0,
                    mime_type=file_ext,
                    file_size=attachment['size'],
                    is_in_knowledge_base=0,
                    content=mark_down_text,
                    img_urls=image_url
                )
                db.session.add(attach)
                db.session.commit()

                attachments.append({
                    "text": mark_down_text,
                    "image_url": image_url
                })

            request_data['attachments'] = attachments

        # 创建任务（参考AITaskService.create_task方法）
        task = AITaskService.create_task(
            document_id=data.get('document_id'),
            task_type='help',
            node_id=node.id,
            request_data=request_data
        )

        db.session.add(task)
        db.session.flush()  # 获取task的id

        # 处理文档附件ID
        document_attachments_id = data.get('document_attachments_id')
        if document_attachments_id is None:
            # 如果有附件，使用刚创建的附件ID
            if 'attach' in locals():
                document_attachments_id = attach.id
            else:
                document_attachments_id = 0

        # 创建对话消息
        current_app.logger.debug(f"task_id: {task.id}")
        conversation_message = ConversationMessage(
            task_id=task.id,  # 使用新创建的task_id
            session_id=data.get('session_id'),
            message_id=data.get('message_id'),
            role=data.get('role'),
            message_type=data.get('message_type'),
            content=data.get('content'),
            document_attachments_id=document_attachments_id,
            message_metadata=data.get('message_metadata'),
            created_at=datetime.now()
        )

        db.session.add(conversation_message)
        db.session.commit()

        return jsonify({
            'code': 200,
            'message': '对话消息添加成功',
            'data': {
                'id': conversation_message.id,
                'task_id': task.id,
                'session_id': conversation_message.session_id,
                'message_id': conversation_message.message_id,
                'role': conversation_message.role,
                'created_at': conversation_message.created_at.isoformat()
            }
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"添加对话消息失败: {str(e)}")
        return jsonify({
            'code': 500,
            'message': f'添加失败: {str(e)}',
            'data': None
        }), 500


@project_document_bp.route('/conversation-messages/<int:message_id>', methods=['DELETE'])
def delete_conversation_message(message_id):
    """删除对话消息"""
    try:
        user_id = g.user_id

        # 查找对话消息
        conversation_message = ConversationMessage.query.get(message_id)

        if not conversation_message:
            return jsonify({
                'code': 404,
                'message': '对话消息不存在',
                'data': None
            }), 404

        # 通过任务验证文档所有权
        task = Task.query.get(conversation_message.task_id)
        if not task:
            return jsonify({
                'code': 404,
                'message': '关联的任务不存在',
                'data': None
            }), 404

        project_doc = ProjectDocument.query.filter_by(
            id=task.document_id,
            user_id=user_id,
            deleted_at=None
        ).first()

        if not project_doc:
            return jsonify({
                'code': 403,
                'message': '无权删除此消息',
                'data': None
            }), 403

        # 删除对话消息
        db.session.delete(conversation_message)
        db.session.commit()

        return jsonify({
            'code': 200,
            'message': '对话消息删除成功',
            'data': None
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"删除对话消息失败: {str(e)}")
        return jsonify({
            'code': 500,
            'message': f'删除失败: {str(e)}',
            'data': None
        }), 500


@project_document_bp.route('/improvement-drafts', methods=['POST'])
def add_improvement_draft():
    """加入改进笔记"""
    try:
        user_id = g.user_id
        data = request.json

        # 验证必要参数
        required_fields = ['document_id', 'node_id', 'session_id', 'source_type']
        for field in required_fields:
            if not data.get(field):
                return jsonify({
                    'code': 400,
                    'message': f'缺少必要参数: {field}',
                    'data': None
                }), 400
        # 验证文档所有权
        project_doc = ProjectDocument.query.filter_by(
            id=data.get('document_id'),
            user_id=user_id,
            deleted_at=None
        ).first()

        if not project_doc:
            return jsonify({
                'code': 404,
                'message': '文档不存在或无权访问',
                'data': None
            }), 404

        # 验证节点是否存在
        node = DocumentNode.query.filter_by(
            document_id=data.get('document_id'),
            node_id=data.get('node_id')
        ).first()

        if not node:
            return jsonify({
                'code': 404,
                'message': '文档节点不存在',
                'data': None
            }), 404

        # 检查是否已存在相同的改进笔记（防止重复添加）
        existing_draft = ImprovementDraft.query.filter_by(
            document_id=data.get('document_id'),
            node_id=node.id,
            session_id=data.get('session_id'),
            is_merged=False
        ).first()
        current_app.logger.debug(
            f"{data.get('document_id')}、{data.get('node_id')}、{data.get('session_id')}、{data.get('source_type')}")
        if existing_draft:
            # 如果已存在，更新内容
            existing_draft.content = data.get('content', existing_draft.content)
            existing_draft.help_text = data.get('help_text', existing_draft.help_text)
            existing_draft.updated_at = datetime.now()
            existing_draft.is_deleted = False
            db.session.commit()

            return jsonify({
                'code': 200,
                'message': '改进笔记已更新',
                'data': {
                    'id': existing_draft.id,
                    'updated_at': existing_draft.updated_at.isoformat()
                }
            })
        document_id = data.get('document_id')
        node_id_str = data.get('node_id')
        document_notes_id = ProjectDocumentService.get_id_by_document_and_node(document_id, node_id_str)
        if not document_notes_id:
            return jsonify({
                'code': 404,
                'message': f'文档节点不存在: {node_id_str}',
                'data': None
            }), 404
        current_app.logger.debug(f'00000000000node_id: {node_id_str}')
        # 创建改进笔记
        improvement_draft = ImprovementDraft(
            document_id=data.get('document_id'),
            node_id=document_notes_id,
            session_id=data.get('session_id'),
            source_type=data.get('source_type'),
            content=data.get('content', ''),
            help_text=data.get('help_text', ''),
            is_selected=data.get('is_selected', False),
            is_merged=False,
            created_at=datetime.now()
        )

        db.session.add(improvement_draft)
        db.session.commit()

        return jsonify({
            'code': 200,
            'message': '改进笔记添加成功',
            'data': {
                'id': improvement_draft.id,
                'session_id': improvement_draft.session_id,
                'source_type': improvement_draft.source_type,
                'created_at': improvement_draft.created_at.isoformat()
            }
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"添加改进笔记失败: {str(e)}")
        return jsonify({
            'code': 500,
            'message': f'添加失败: {str(e)}',
            'data': None
        }), 500

@project_document_bp.route('/improvement-drafts/<int:draft_id>', methods=['DELETE'])
def delete_improvement_draft(draft_id):
    """
    删除改进笔记
    """
    try:
        # 获取当前用户ID（根据您的认证系统调整）
        current_user_id = g.user_id

        # 查询改进笔记
        draft = ImprovementDraft.query.get(draft_id)
        if not draft:
            return jsonify({'code': 404, 'message': '改进笔记不存在'})

        # 验证权限：用户只能删除自己的笔记
        # 首先获取文档，检查文档所属用户
        project_doc = ProjectDocument.query.get(draft.document_id)
        if not project_doc:
            return jsonify({'code': 404, 'message': '文档不存在'})

        if project_doc.user_id != current_user_id:
            return jsonify({'code': 403, 'message': '无权删除此改进笔记'})

        # 软删除：设置 is_deleted 为 True
        draft.is_deleted = True
        draft.updated_at = datetime.now()

        db.session.commit()

        return jsonify({
            'code': 200,
            'message': '删除成功',
            'data': {'draft_id': draft_id}
        })

    except Exception as e:
        current_app.logger.error(f"删除改进笔记失败: {str(e)}")
        db.session.rollback()
        return jsonify({
            'code': 500,
            'message': f'删除失败: {str(e)}'
        })


@project_document_bp.route('/improvement-drafts', methods=['GET'])
def get_improvement_drafts():
    """获取改进笔记列表"""
    try:
        user_id = g.user_id
        document_id = request.args.get('document_id', type=int)
        node_id = request.args.get('node_id', type=str)
        source_type = request.args.get('source_type', type=str)
        is_merged = request.args.get('is_merged', type=str)

        # 新增：接收is_deleted参数
        is_deleted_param = request.args.get('is_deleted', type=str)

        if not document_id or not node_id:
            return jsonify({
                'code': 400,
                'message': '缺少必要参数: document_id 或 node_id',
                'data': None
            }), 400

        # 验证文档所有权
        project_doc = ProjectDocument.query.filter_by(
            id=document_id,
            user_id=user_id,
            deleted_at=None
        ).first()

        if not project_doc:
            return jsonify({
                'code': 404,
                'message': '文档不存在或无权访问',
                'data': None
            }), 404

        # 验证节点是否存在
        document_notes_id = ProjectDocumentService.get_id_by_document_and_node(document_id, node_id)
        if not document_notes_id:
            return jsonify({
                'code': 404,
                'message': f'文档节点不存在: {node_id}',
                'data': None
            }), 404

        # 构建查询条件
        query = ImprovementDraft.query.filter_by(
            document_id=document_id,
            node_id=document_notes_id
        )

        # 处理is_deleted参数
        if is_deleted_param and is_deleted_param.lower() in ['true', 'false']:
            is_deleted = (is_deleted_param.lower() == 'true')
            query = query.filter_by(is_deleted=is_deleted)
        else:
            # 默认查询未删除的记录
            query = query.filter_by(is_deleted=False)

        if source_type:
            query = query.filter_by(source_type=source_type)

        if is_merged and is_merged.lower() in ['true', 'false']:
            query = query.filter_by(is_merged=(is_merged.lower() == 'true'))

        # 执行查询
        drafts = query.order_by(ImprovementDraft.created_at.desc()).all()

        # 构建响应数据
        drafts_list = []
        for draft in drafts:
            drafts_list.append({
                'id': draft.id,
                'document_id': draft.document_id,
                'node_id': draft.node_id,
                'session_id': draft.session_id,
                'source_type': draft.source_type,
                'content': draft.content,
                'help_text': draft.help_text,
                'is_selected': draft.is_selected,
                'is_merged': draft.is_merged,
                'is_deleted': draft.is_deleted,  # 新增字段
                'created_at': draft.created_at.isoformat() if draft.created_at else None,
                'updated_at': draft.updated_at.isoformat() if draft.updated_at else None
            })

        return jsonify({
            'code': 200,
            'message': '获取改进笔记列表成功',
            'data': {
                'count': len(drafts_list),
                'drafts': drafts_list
            }
        })

    except Exception as e:
        current_app.logger.error(f"获取改进笔记列表失败: {str(e)}")
        return jsonify({
            'code': 500,
            'message': f'获取失败: {str(e)}',
            'data': None
        }), 500

@project_document_bp.route('/conversation-messages', methods=['GET'])
def get_conversation_messages():
    """根据改进草稿ID获取对应的对话消息"""
    try:
        user_id = g.user_id
        document_id = request.args.get('document_id', type=int)
        node_id = request.args.get('node_id', type=str)
        draft_id = request.args.get('draft_id', type=int)

        if not document_id or not draft_id:
            return jsonify({
                'code': 400,
                'message': '缺少必要参数: document_id 或 draft_id',
                'data': None
            }), 400

        # 验证文档所有权
        project_doc = ProjectDocument.query.filter_by(
            id=document_id,
            user_id=user_id,
            deleted_at=None
        ).first()

        if not project_doc:
            return jsonify({
                'code': 404,
                'message': '文档不存在或无权访问',
                'data': None
            }), 404

        # 查询改进草稿
        improvement_draft = ImprovementDraft.query.filter_by(
            id=draft_id,
            document_id=document_id
        ).first()

        if not improvement_draft:
            return jsonify({
                'code': 404,
                'message': '改进草稿不存在',
                'data': None
            }), 404

        # 如果提供了node_id，验证节点是否存在
        if node_id:
            node = DocumentNode.query.filter_by(
                document_id=document_id,
                node_id=node_id
            ).first()

            if not node:
                return jsonify({
                    'code': 404,
                    'message': '文档节点不存在',
                    'data': None
                }), 404
        # 获取会话ID
        session_id = improvement_draft.session_id
        if not session_id:
            return jsonify({
                'code': 404,
                'message': '该改进草稿没有对应的会话记录',
                'data': None
            }), 404

        # 获取该会话的所有消息
        messages = ConversationMessage.query.join(
            Task, ConversationMessage.task_id == Task.id
        ).filter(
            Task.document_id == document_id,
            ConversationMessage.session_id == session_id
        ).order_by(ConversationMessage.created_at.asc()).all()

        # 构建消息列表
        messages_list = []
        for message in messages:
            message_data = {
                'messageId': message.message_id,
                'role': message.role,
                'content': message.content,
                'message_type': message.message_type,
                'created_at': message.created_at.isoformat() if message.created_at else None,
                'session_id': message.session_id
            }

            # 如果有附件，获取附件信息
            if message.document_attachments_id and message.document_attachments_id > 0:
                attachment = DocumentAttachment.query.get(message.document_attachments_id)
                if attachment:
                    message_data['attachments'] = [{
                        'id': attachment.id,
                        'filename': attachment.filename,
                        'file_url': attachment.file_url,
                        'text': attachment.content,
                        'image_url': attachment.img_urls
                    }]
                else:
                    message_data['attachments'] = []
            else:
                message_data['attachments'] = []

            messages_list.append(message_data)

        # 获取改进草稿信息
        improvement_drafts = ImprovementDraft.query.filter_by(
            document_id=document_id,
            session_id=session_id
        ).all()

        help_text_list = []
        for draft in improvement_drafts:
            if draft.help_text:
                help_text_list.append(draft.help_text)

        return jsonify({
            'code': 200,
            'message': '获取对话消息成功',
            'data': {
                'sessionId': session_id,
                'draftId': draft_id,
                'improvementContent': improvement_draft.content,
                'helpText': improvement_draft.help_text,
                'helpTexts': help_text_list,
                'draftCount': len(improvement_drafts),
                'messages': messages_list
            }
        })

    except Exception as e:
        current_app.logger.error(f"获取对话消息失败: {str(e)}")
        return jsonify({
            'code': 500,
            'message': f'获取失败: {str(e)}',
            'data': None
        }), 500


# =========== 新增：根据用户ID获取项目文档列表 ===========
@project_document_bp.route('/user/<int:target_user_id>/projects', methods=['GET'])
def get_projects_by_user_id(target_user_id):
    """根据用户ID获取项目文档列表（管理员权限）"""
    try:
        # 获取当前用户ID
        current_user_id = g.user_id

        if target_user_id != current_user_id:
            # 如果当前登录用户，返回403
            return jsonify({
                'code': 403,
                'message': '权限不足，无法查看其他用户的项目',
                'data': None
            }), 403

        # 分页参数
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        status = request.args.get('status', None)

        # 构建查询
        query = ProjectDocument.query.filter_by(
            user_id=target_user_id,
            deleted_at=None
        )

        if status:
            query = query.filter_by(status=status)

        # 执行分页查询
        pagination = query.order_by(ProjectDocument.updated_at.desc()) \
            .paginate(page=page, per_page=per_page, error_out=False)

        projects = pagination.items

        # 构建响应
        result = {
            'user_id': target_user_id,
            'projects': [
                {
                    'id': project.id,
                    'title': project.title,
                    'status': project.status,
                    'idea': project.idea,
                    'industry': project.industry,
                    'doc_guide': project.doc_guide,
                    'total_review_score': project.total_review_score,
                    'created_at': project.created_at.isoformat() if project.created_at else None,
                    'updated_at': project.updated_at.isoformat() if project.updated_at else None
                }
                for project in projects
            ],
            'pagination': {
                'page': pagination.page,
                'per_page': pagination.per_page,
                'total': pagination.total,
                'pages': pagination.pages
            }
        }

        return jsonify({
            'code': 200,
            'message': 'success',
            'data': result
        })

    except Exception as e:
        current_app.logger.error(f"获取用户{target_user_id}的项目列表失败: {str(e)}")
        return jsonify({
            'code': 500,
            'message': f'获取项目列表失败: {str(e)}',
            'data': None
        }), 500


# =========== 新增：搜索项目文档 ===========
@project_document_bp.route('/search', methods=['GET'])
def search_projects():
    """搜索项目文档（支持按标题、行业、状态搜索）"""
    try:
        user_id = g.user_id

        # 搜索参数
        keyword = request.args.get('keyword', '')
        status = request.args.get('status', None)
        industry = request.args.get('industry', None)

        # 时间范围参数
        start_date = request.args.get('start_date', None)
        end_date = request.args.get('end_date', None)

        # 分页参数
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)

        # 构建查询
        query = ProjectDocument.query.filter_by(
            user_id=user_id,
            deleted_at=None
        )

        # 关键词搜索
        if keyword:
            query = query.filter(
                ProjectDocument.title.like(f'%{keyword}%') |
                ProjectDocument.idea.like(f'%{keyword}%')
            )

        # 状态筛选
        if status:
            query = query.filter_by(status=status)

        # 行业筛选
        if industry:
            query = query.filter_by(industry=industry)

        # 时间范围筛选
        if start_date:
            try:
                start_date_obj = datetime.strptime(start_date, '%Y-%m-%d')
                query = query.filter(ProjectDocument.created_at >= start_date_obj)
            except ValueError:
                current_app.logger.warning(f"无效的起始日期格式: {start_date}")

        if end_date:
            try:
                end_date_obj = datetime.strptime(end_date, '%Y-%m-%d')
                # 结束日期加一天，包含当天
                end_date_obj = end_date_obj.replace(hour=23, minute=59, second=59)
                query = query.filter(ProjectDocument.created_at <= end_date_obj)
            except ValueError:
                current_app.logger.warning(f"无效的结束日期格式: {end_date}")

        # 执行分页查询
        pagination = query.order_by(ProjectDocument.updated_at.desc()) \
            .paginate(page=page, per_page=per_page, error_out=False)

        projects = pagination.items

        # 获取统计信息
        total_count = ProjectDocument.query.filter_by(
            user_id=user_id,
            deleted_at=None
        ).count()

        status_stats = {}
        statuses = ['draft', 'writing', 'reviewing', 'completed', 'archived']

        for status_item in statuses:
            count = ProjectDocument.query.filter_by(
                user_id=user_id,
                status=status_item,
                deleted_at=None
            ).count()
            status_stats[status_item] = count

        # 构建响应
        result = {
            'projects': [
                {
                    'id': project.id,
                    'title': project.title,
                    'status': project.status,
                    'idea': project.idea[:100] + '...' if project.idea and len(project.idea) > 100 else project.idea,
                    'industry': project.industry,
                    'doc_guide': project.doc_guide[:100] + '...' if project.doc_guide and len(
                        project.doc_guide) > 100 else project.doc_guide,
                    'total_review_score': project.total_review_score,
                    'created_at': project.created_at.isoformat() if project.created_at else None,
                    'updated_at': project.updated_at.isoformat() if project.updated_at else None,
                    'word_count': sum(
                        len(node.content or '') for node in project.document_nodes) if project.document_nodes else 0
                }
                for project in projects
            ],
            'pagination': {
                'page': pagination.page,
                'per_page': pagination.per_page,
                'total': pagination.total,
                'pages': pagination.pages
            },
            'statistics': {
                'total_count': total_count,
                'status_stats': status_stats,
                'search_count': pagination.total
            }
        }

        return jsonify({
            'code': 200,
            'message': 'success',
            'data': result
        })

    except Exception as e:
        current_app.logger.error(f"搜索项目文档失败: {str(e)}")
        return jsonify({
            'code': 500,
            'message': f'搜索失败: {str(e)}',
            'data': None
        }), 500


# =========== 项目文档管理接口 ===========
@project_document_bp.route('/projects/<int:project_id>', methods=['DELETE'])
def delete_project(project_id):
    """软删除项目文档"""
    try:
        user_id = g.user_id

        # 查找项目
        project = ProjectDocument.query.filter_by(
            id=project_id,
            user_id=user_id,
            deleted_at=None
        ).first()

        if not project:
            return jsonify({
                'code': 404,
                'message': '项目不存在或已被删除',
                'data': None
            }), 404

        # 软删除项目
        project.deleted_at = datetime.now()
        db.session.commit()

        return jsonify({
            'code': 200,
            'message': '项目删除成功',
            'data': None
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"删除项目失败: {str(e)}")
        return jsonify({
            'code': 500,
            'message': f'删除失败: {str(e)}',
            'data': None
        }), 500


@project_document_bp.route('/projects/<int:project_id>/archive', methods=['POST'])
def archive_project(project_id):
    """归档项目文档"""
    try:
        user_id = g.user_id

        # 查找项目
        project = ProjectDocument.query.filter_by(
            id=project_id,
            user_id=user_id,
            deleted_at=None
        ).first()

        if not project:
            return jsonify({
                'code': 404,
                'message': '项目不存在或已被删除',
                'data': None
            }), 404

        # 更新项目状态为归档
        project.status = 'archived'
        project.updated_at = datetime.now()
        db.session.commit()

        return jsonify({
            'code': 200,
            'message': '项目归档成功',
            'data': None
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"归档项目失败: {str(e)}")
        return jsonify({
            'code': 500,
            'message': f'归档失败: {str(e)}',
            'data': None
        }), 500


@project_document_bp.route('/projects/<int:project_id>/restore', methods=['POST'])
def restore_project(project_id):
    """恢复已删除的项目文档"""
    try:
        user_id = g.user_id

        # 查找已删除的项目
        project = ProjectDocument.query.filter_by(
            id=project_id,
            user_id=user_id
        ).first()

        if not project:
            return jsonify({
                'code': 404,
                'message': '项目不存在',
                'data': None
            }), 404

        if not project.deleted_at:
            return jsonify({
                'code': 400,
                'message': '项目未删除',
                'data': None
            }), 400

        # 恢复项目
        project.deleted_at = None
        db.session.commit()

        return jsonify({
            'code': 200,
            'message': '项目恢复成功',
            'data': None
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"恢复项目失败: {str(e)}")
        return jsonify({
            'code': 500,
            'message': f'恢复失败: {str(e)}',
            'data': None
        }), 500


# =========== 项目列表页面 ===========
@project_document_bp.route('/project-documents-list', methods=['GET'])
def project_documents_list_page():
    """项目文档列表页面"""
    return render_template('project_document/project_documents_list.html')