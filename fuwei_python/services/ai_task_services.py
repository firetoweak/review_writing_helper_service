# services/ai_task_services.py
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import uuid
import json
import time
from typing import Optional, List, Dict, Any, Generator

import requests
from flask import current_app, jsonify
from sqlalchemy import and_, func

from common.aliOss import aliOss
from conf.config import app_config
from models.project_document.model import (
    ProjectDocument, DocumentNode, Task, ConversationMessage,
    ImprovementDraft, DocumentAttachment, Prompt, KnowledgeBaseDocument,
    IndustryList, OutlineRules, ReviewRules
)
from services.project_document_services import ProjectDocumentService
from services.upload_file_service import UploadFileService
from utils.file_handler import FileHandler
from conf.db import db
from utils.markdown_converter import convert_markdown_to_html

class AITaskService:
    """AI任务服务类"""

    @staticmethod
    def generate_task_uuid() -> str:
        """生成任务唯一标识符"""
        return f"task_{uuid.uuid4().hex[:16]}"

    @staticmethod
    def get_prompt(name: str) -> str:
        """获取提示词"""
        try:
            query = Prompt.query.filter_by(name=name, is_active=True)
            prompt = query.order_by(Prompt.version.desc()).first()
            if prompt:
                return prompt.content
            else:
                current_app.logger.warning(f"未找到提示词: name={name}")
                return ""

        except Exception as e:
            current_app.logger.error(f"获取提示词失败: {str(e)}")
            return ""

    # =========== 1. 行业特点识别 ===========
    @staticmethod
    def handle_industry_identification(title: str, idea: str) -> str:

        industry_list = IndustryList.query.all()
        industry_prompt = ""
        industry_name_list = []
        for industry in industry_list:
            industry_name_list.append(industry.name)
        industry_prompt = industry_prompt+f"回答该文章属于industryNameList中哪个行业？如果都不在，返回空"
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer token123"
        }
        payload = {
                "title": title,
                "idea": idea,
                "industryNameList": industry_name_list,
                "prompt": {
                    "industryPrompt": industry_prompt
                }
        }
        try:
            response = None
            response = requests.post(
                f"{app_config['ai_server']}/api/industry",
                json=payload,
                headers=headers,
                timeout=600
            )
            data = response.json()
            print(f"industry_data:{data}")
            return data['industryName']
        except Exception as e:
            current_app.logger.info_module(
                f"识别所属行业接口异常-handle_industry_identification：{e},文件：{e.__traceback__.tb_frame.f_globals['__file__']};行数：{e.__traceback__.tb_lineno}",
                "model")
            if response is not None and response.content:
                current_app.logger.info_module(f"respones:{response.content.decode('utf-8')}", "model")
                raise


    # =========== 2. 全文写作指导（大纲生成） ===========
    @staticmethod
    def handle_outline_generation(document_id: int, project_data: dict, industry: str = None) -> dict:
        """处理大纲生成任务"""
        task = None
        try:
            # 1. 创建任务
            task = AITaskService.create_task(
                document_id=document_id,
                task_type='outline',
                request_data={'project': project_data, 'industry': industry}
            )
            # # 2. 更新任务状态为处理中
            AITaskService.update_task_status(task.id, 'processing', progress=10)
            # 3. 获取大纲规则
            outline_rules = AITaskService.get_outline_rules()
            outline_full_text_rule = "\n".join([rule['content'] for rule in outline_rules])
            # 4. 准备AI请求数据
            outline_prompt = AITaskService.get_prompt('chapterOutlinePrompt')
            all_thread = []
            AITaskService.init_project_document_nodes(document_id)
            level1_payloads,level2_payloads = AITaskService.get_chapter_section_payloads(document_id, industry,project_data.get('title'),project_data.get('idea'),outline_full_text_rule)
            thread = threading.Thread(target=AITaskService.done_full_txt_key_point, args=(document_id,project_data,outline_full_text_rule,industry,outline_prompt,task.id))
            thread.start()
            all_thread.append(thread)
            for payload in level1_payloads:
                thread = threading.Thread(target=AITaskService.done_level1_key_point, args=(payload,0))
                thread.start()
                all_thread.append(thread)
            now_exec_leve2_payload = level2_payloads[0:1]
            next_exec_leve2_payload = level2_payloads[1:]
            for payload in now_exec_leve2_payload:
                thread = threading.Thread(target=AITaskService.done_level2_key_point,  args=(payload,0))
                thread.start()
                all_thread.append(thread)
            for thread in all_thread:
                thread.join()
            for payload in next_exec_leve2_payload:
                thread = threading.Thread(target=AITaskService.done_level2_key_point,  args=(payload,0))
                thread.start()
            #AITaskService.handle_keypoints(document_id, industry, project_data.get('title'), project_data.get('idea'),outline_full_text_rule)
            return {
                "taskId": task.task_uuid,
                "docGuide": "",
                "outline": ""
            }

        except Exception as e:
            current_app.logger.error(f"大纲生成失败: {str(e)}", exc_info=True)

            # 回滚数据库事务
            try:
                db.session.rollback()
            except Exception as rollback_error:
                current_app.logger.error(f"回滚事务失败: {str(rollback_error)}")

            # 更新任务状态
            if task:
                AITaskService.update_task_status(
                    task.id,
                    'failed',
                    error_message=str(e)
                )
            raise
    @staticmethod
    def project_outline_done(project_data,outline_full_text_rule,industry,outline_prompt,document_id,task_id):

        # 更新项目文档的写作指导和行业特点

        #一二级目录的写作要点
        AITaskService.handle_keypoints(document_id, industry,  project_data.get('title'), project_data.get('idea'), outline_full_text_rule)
        # 7. 更新任务状态

    @staticmethod
    def get_chapter_section_payloads(document_id: int, industry: str = None,title=None,idea=None,outline_rules_text=None):
        """处理一级章节写作要点生成"""
        try:
            # 获取节点信息
            rules = OutlineRules.query.filter(OutlineRules.title_num!="").order_by(OutlineRules.title_num.asc()).all()
            # 获取大纲规则
            level_one_chapter_prompt = AITaskService.get_prompt('chapterPointPrompt')
            level_tow_chapter_prompt = AITaskService.get_prompt('sectionPointPrompt')
            level1_payload = []
            level2_payload = []
            for rule in rules:
                # 准备AI请求数据
                if re.match(r'^\d+$',rule.title_num) is not None:
                    payload ={
                        "projectId": f"{document_id}",
                        "title": title, # 立项标题
                        "idea": idea, # 立项构想
                        "fullWriteRule": outline_rules_text,
                        "chapterId": rule.title_num, # 章节Id
                        "industry": industry, # 行业特点
                        "prompt": {"chapterKeypointPrompt": level_one_chapter_prompt}
                    }
                    level1_payload.append(payload)
                    #thread = threading.Thread(target=AITaskService.done_level1_key_point, args=(payload,0))
                    #thread.start()
                    #chapter_threads.append(thread)
                else:
                    payload = {
                          "projectId": f"{document_id}",
                          "title": title,  # 立项标题
                          "idea": idea,  # 立项构想
                          "chapterWriteRule":rule.content,
                          "chapterId": str(int(float(rule.title_num))),
                          "sectionId": rule.title_num,
                          "industry": industry,  # 行业特点
                          "prompt": {"sectionKeypointPrompt": level_tow_chapter_prompt}
                        }
                    level2_payload.append(payload)
            return level1_payload,level2_payload
            # for chapter_thread in chapter_threads:
            #     chapter_thread.join()
            # thread = threading.Thread(target=AITaskService.done_thread_level2, args=(payload_list,))
            # thread.start()
        except Exception as e:
            current_app.logger.error(f"生成二级章节写作要点失败: {str(e)}")
            raise
    @staticmethod
    def init_project_document_nodes(document_id):
        rules = OutlineRules.query.filter(OutlineRules.title_num != "").order_by(OutlineRules.title_num.asc()).all()
        i = 0
        pid = 0
        for rule in rules:
            i = i+1
            if re.match(r'^\d+$', rule.title_num) is not None:
                chapter_node = DocumentNode(
                    document_id=document_id,
                    node_id=rule.title_num,
                    level=1,
                    title= "",
                    key_point="",
                    order_num=i,
                    status='pending',
                    created_at=datetime.now()
                )
                db.session.add(chapter_node)
                db.session.commit()
                pid = chapter_node.id
            else:
                section_node = DocumentNode(
                    document_id=document_id,
                    node_id=rule.title_num,
                    level=2,
                    title="",
                    key_point="",
                    parent_id=pid,
                    order_num= i ,
                    status='pending',
                    created_at=datetime.now()
                )
                db.session.add(section_node)
                db.session.commit()
    @staticmethod
    def done_full_txt_key_point(document_id,project_data,outline_full_text_rule,industry,outline_prompt,task_id):
        from app import app
        with app.app_context():
            payload = {
                "projectId": f"{document_id}",
                "title": project_data.get('title'),
                "idea": project_data.get('idea'),
                "fullWriteRule": outline_full_text_rule,
                "industry": industry,
                "prompt": {"outlinePrompt": outline_prompt}
            }
            print("全文写作要点：")
            print(json.dumps(payload, ensure_ascii=False))
            headers = {
                "Content-Type": "application/json",
                "Authorization": "Bearer token123"
            }
            try:
                response = None
                response = requests.post(
                    f"{app_config['ai_server']}/api/project-outline",
                    json=payload,
                    headers=headers,
                    timeout=600
                )
                data = response.json()
                print(data)
                outline_data = data['outline']
                doc_guide = data['docGuide']
                try:
                    project_doc = ProjectDocument.query.filter_by(id=document_id).first()
                    if not project_doc:
                        raise ValueError(f"项目文档不存在: {document_id}")
                    project_doc.doc_guide = convert_markdown_to_html(str(doc_guide).replace("\\n", "\n"))
                    project_doc.industry = str(industry) if industry else None  # 确保转为字符串
                    project_doc.status = 'writing'
                    db.session.commit()
                except Exception as e:
                    print(f"{e},文件：{e.__traceback__.tb_frame.f_globals['__file__']};行数：{e.__traceback__.tb_lineno}")
                    raise
                for i, chapter_data in enumerate(outline_data):
                    if not isinstance(chapter_data, dict):
                        current_app.logger.warning(f"章节数据格式错误，跳过: {chapter_data}")
                        continue
                    # 确保数据格式正确
                    node_id = chapter_data.get('nodeId', f'chapter_{i + 1}')
                    title = chapter_data.get('title', f'章节{i + 1}')
                    key_point = str(chapter_data.get('keyPoint', ''))  # 确保转为字符串
                    if node_id is None or title is None:
                        continue
                    # 创建一级章节
                    try:
                        DocumentNode.query.filter_by(node_id=node_id,document_id=document_id).update({"title":title})
                        db.session.commit()
                    except Exception as e:
                        print(f"DocumentNode:{e}")
                        raise Exception("出错了")

                    # 创建二级小节
                    children = chapter_data.get('children', [])
                    if isinstance(children, list):
                        for j, section_data in enumerate(children):
                            if not isinstance(section_data, dict):
                                continue
                            section_node_id = section_data.get('nodeId')
                            section_title = section_data.get('title')
                            if section_node_id is None or section_title is None:
                                continue
                            DocumentNode.query.filter_by(node_id=section_node_id, document_id=document_id).update({"title": section_title})
                            db.session.commit()
                AITaskService.update_task_status(
                    task_id,
                    'completed',
                    response_data={
                        'docGuide': doc_guide,
                        'outlineCount': len(outline_data)
                    },  # 只传必要的可序列化数据
                    progress=100
                )
                return doc_guide, outline_data


            except Exception as e:
                current_app.logger.info_module(
                    f"生成目录，全文写作要点调用异常-handle_outline_generation：{e},文件：{e.__traceback__.tb_frame.f_globals['__file__']};行数：{e.__traceback__.tb_lineno}",
                    "model")
                if response is not None and response.content:
                    current_app.logger.info_module(f"respones:{response.content.decode('utf-8')}", "model")
                raise

    @staticmethod
    def done_thread_level2(payload_list):
        from app import app
        with app.app_context():
            with ThreadPoolExecutor(max_workers=10) as executor:
                for payload in payload_list:
                    # submit返回Future对象，用于获取结果/设置回调
                    executor.submit(AITaskService.done_level2_key_point, payload,0)

    @staticmethod
    def done_level1_key_point(payload,tag=0):
        from app import app
        with app.app_context():
            current_app.logger.info(f"调用AI生成一级章节写作要点: {payload}")
            headers = {
                "Content-Type": "application/json",
                "Authorization": "Bearer token123"
            }
            try:
                response = requests.post(
                    f"{app_config['ai_server']}/api/project-outline/chapterKeyPoint",
                    json=payload,
                    headers=headers,
                    timeout=600
                )
                print("章节写作要点返回：")
                print(response.json())

                DocumentNode.query.filter_by(document_id=payload['projectId'], node_id=payload['chapterId']).update({"key_point": convert_markdown_to_html(response.json().get('keyPoint', '').replace("\\n", "\n")), "updated_at": datetime.now()})
                db.session.commit()
            except Exception as e:
                if tag<3:
                    AITaskService.done_level1_key_point(payload, tag=tag+1)
                else:
                    raise Exception(f"章节生成失败{(json.dumps(payload, ensure_ascii=False))}")

    @staticmethod
    def done_level2_key_point(payload,tag=0):
        from app import app
        with app.app_context():
            print("小节写作要点调用")
            print(json.dumps(payload, ensure_ascii=False))
            headers = {
                "Content-Type": "application/json",
                "Authorization": "Bearer token123"
            }
            try:
                response = requests.post(
                    f"{app_config['ai_server']}/api/project-outline/sectionKeyPoint",
                    json=payload,
                    headers=headers,
                    timeout=600
                )
                print("章节接口返回数据：")
                print(response.json())
                child_node_id = response.json().get('sectionId')
                DocumentNode.query.filter_by(
                    document_id=payload['projectId'],
                    node_id=child_node_id,
                ).update({"key_point": convert_markdown_to_html(response.json().get('keyPoint', '').replace("\\n", "\n")), "updated_at": datetime.now()})
                db.session.commit()
            except Exception as e:
                if tag<3:
                    tag = tag+1
                    AITaskService.done_level2_key_point(payload, tag)
                else:
                    raise Exception(f"小节要点生成失败{(json.dumps(payload, ensure_ascii=False))}")

    # =========== 2.1 生成二级章节写作要点 ===========
    @staticmethod
    def handle_level_two_keypoints(document_id: int, node_id: str, industry: str = None) -> dict:
        """处理二级章节写作要点生成"""
        try:
            # 获取节点信息
            node = DocumentNode.query.filter_by(
                document_id=document_id,
                node_id=node_id
            ).first()

            if not node or node.level != 1:
                raise ValueError(f"二级章节不存在: node_id={node_id}")

            # 获取大纲规则
            outline_rules = AITaskService.get_outline_rules()
            rule_text = "\n".join([rule['content'] for rule in outline_rules])

            # 获取提示词
            level_two_chapter_prompt = AITaskService.get_prompt('sectionPointPrompt')

            # 准备AI请求数据
            ai_request = {
                  "projectId": "xxx-xxx",
                  "idea": "...",
                  "sectionWriteRule": "xxx",
                  "chapterId": "1",
                  "sectionId": "1.1",
                  "industry": "xxx",
                  "outline": [
                    {
                      "nodeId": "1",
                      "level": 1,
                      "title": "一级章节标题xxx",
                      "children": [
                        { "nodeId": "1.1", "level": 2, "title": "二级小节标题xxx"},
                        { "nodeId": "1.2", "level": 2, "title": "二级小节标题xxx"}
                      ]
                    }
                  ],
                  "prompt": {"sectionKeypointPrompt": "xxxxx"}
            }

            current_app.logger.info(f"调用AI生成二级章节写作要点: {ai_request}")

            # 调用AI服务
            ai_response = AITaskService.call_ai_service('/api/project-outline/keyPoint', ai_request)

            # 更新子节点的写作要点
            keypoint_list = ai_response.get('keyPointList', [])
            for keypoint_item in keypoint_list:
                child_node_id = keypoint_item.get('nodeId')
                child_node = DocumentNode.query.filter_by(
                    document_id=document_id,
                    node_id=child_node_id,
                    parent_id=node.id
                ).first()

                if child_node:
                    child_node.key_point = keypoint_item.get('keyPoint', '')
                    child_node.updated_at = datetime.now()

            db.session.commit()

            return {
                "task": "outline",
                "title": node.title,
                "keyPointList": keypoint_list
            }

        except Exception as e:
            current_app.logger.error(f"生成二级章节写作要点失败: {str(e)}")
            raise
    # =========== 3. 启发式写作 ===========
    @staticmethod
    def handle_heuristic_writing(document_id: int, node_id: str, session_id: str = None,user_text: str = None):
        """处理启发式写作任务"""
        task = AITaskService.create_task(
            document_id=document_id,
            task_type='heuristic_writing',
            node_id=node_id,
            request_data={'node_id': node_id, 'session_id': session_id, 'user_text': user_text}
        )
        # 3. 准备会话数据
        if not session_id:
            session_id = f"heuristic_{node_id}_{int(time.time())}"
        # 获取提示词
        heuristic_prompt = AITaskService.get_prompt('firstHeuristicWriting')
        check_prompt = AITaskService.get_prompt('firstHeuristiccheckPrompt')
        text_list, history_text_list, now_node, section_write_rule, section_review_rule, headers, project_doc = AITaskService.get_public_data(document_id, node_id)
        try:
            data = {
                "projectId": f"{document_id}",
                "sessionId": session_id,
                "sectionWriteRule": section_write_rule,
                "textList": text_list,
                "historyTextList": history_text_list,
                "sectionReviewRule":section_review_rule if section_review_rule is not None else "",
                "industry": project_doc.industry,
                "title": project_doc.title,
                "idea": project_doc.idea,
                "sectionId": node_id,
                "sectionTitle": now_node.title,
                "prompt": {
                    "heuristicWritingPrompt": heuristic_prompt,
                    "heuristicCorrectPrompt": check_prompt
                }
            }
            print(json.dumps(data, ensure_ascii=False))
            # 发送请求，stream=True 表示流式接收
            response = requests.post(
                f"{app_config['ai_server']}/api/heuristic-writing",
                headers=headers,
                json=data,
                stream=True,  # 关键：开启流式模式
                timeout=600
            )
            response.raise_for_status()  # 检查 HTTP 状态码
            messages = ""
            message_id = 0
            print("流式输出")
            for chunk in response.iter_lines(chunk_size=1024):  # 按行读取
                if chunk:  # 过滤空块
                    # 字节转字符串（根据接口编码调整，通常 utf-8）
                    data = json.loads(chunk.decode("utf-8"))
                    print(data)
                    if "assistantMessage" in data:
                        message_id = data["assistantMessage"]["messageId"]
                        yield json.dumps({'session_id': session_id, "message_id": message_id,"status":"draft"})
                        continue
                    if 'done' in data:
                        AITaskService.save_conversation_message(
                            task_id=task.id,
                            session_id=session_id,
                            message_id=message_id,
                            role='assistant',
                            content=messages,
                            message_type='question'
                        )
                        AITaskService.update_task_status(task.id, 'processing', progress=30)
                        break
                    messages = messages + data['delta']
                    yield data['delta']
            #return messages
        except requests.exceptions.RequestException as e:
            print(f"HTTP 请求出错：{str(e)}")

    @staticmethod
    def handle_heuristic_response(document_id: int, node_id: str, session_id: str,message: str, attachment: dict = {},message_id= None):
        """处理启发式写作的用户回复"""
        # 1. 获取节点和任务
        node = DocumentNode.query.filter_by(
            document_id=document_id,
            node_id=node_id
        ).first()

        task = Task.query.filter_by(
            document_id=document_id,
            task_type='heuristic_writing'
        ).order_by(Task.created_at.desc()).first()

        if not task:
            raise ValueError("未找到启发式写作任务")

        # 获取当前轮次（通过查询对话消息计算）
        message_count = ConversationMessage.query.filter_by(
            task_id=task.id,
            session_id=session_id
        ).count()

        # 每轮包含AI提问和用户回答，所以轮次 = (消息数 + 1) // 2
        current_round = (message_count + 1) // 2

        # 2. 保存用户消息
        AITaskService.save_conversation_message(
            task_id=task.id,
            session_id=session_id,
            message_id=message_id,
            role='user',
            content=message,
            message_type='answer',
        )
        if attachment:
            img_tag = f"[IMAGE_{ str(int(time.time() * 100000))}{document_id}]"
            image_list = [{
                    "text":"",
                    "image_url": {f"{img_tag}":attachment['file_url']},
                }]
            message = f"{img_tag}{message}"
        else:
            image_list = []

        # 3. 获取对话历史
        history_messages = ConversationMessage.query.filter_by(
            task_id=task.id,
            session_id=session_id
        ).order_by(ConversationMessage.created_at).all()

        # 5. 调用AI服务
        data = {
            "projectId": f"{document_id}",
            "sessionId": f"{session_id}",
            "messages": [{
                "messageId": message_id,
                "role": "user",
                "type": "answer",
                "content": message,
                "attachments": image_list
            }]
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer token123"
        }
        print(json.dumps(data, ensure_ascii=False))
        try:
            # 发送请求，stream=True 表示流式接收
            response = requests.post(
                f"{app_config['ai_server']}/api/heuristic-writing/message",
                headers=headers,
                json=data,
                stream=True,  # 关键：开启流式模式
                timeout=600
            )
            response.raise_for_status()  # 检查 HTTP 状态码

            # 逐块读取流式数据（按字节/行）
            messages = ""
            status = "ask"
            print("流式输出：")
            for chunk in response.iter_lines(chunk_size=1024):  # 按行读取
                if chunk:  # 过滤空块
                    # 字节转字符串（根据接口编码调整，通常 utf-8）
                    data = json.loads(chunk.decode("utf-8"))
                    print(data)
                    if "assistantMessage" in data:
                        status = data["status"]
                        message_id = data["assistantMessage"]["messageId"]
                        yield json.dumps({'session_id': session_id, "message_id": message_id,"status":status})
                        continue
                    if 'done' in data:
                        AITaskService.save_conversation_message(
                            task_id=task.id,
                            session_id=session_id,
                            message_id=message_id,
                            role='assistant',
                            content=messages,
                            message_type='question'
                        )
                        if status == "draft" or current_round >= 5:
                            # node.content = messages  # 内容合入由用户在前端页面决定后再入库
                            node.status = 'writing'
                            db.session.commit()
                            AITaskService.update_task_status(task.id, 'completed', progress=100)
                        break
                    #messages = messages + data['delta']
                    yield data['delta']
            #return messages
                    #yield data['delta']
        except requests.exceptions.RequestException as e:
            print(f"HTTP 请求出错：{str(e)}")

    # =========== 4. AI自动评审 ===========
    @staticmethod
    def handle_section_review(document_id: int, node_id: str, session_id: str = None) -> dict:
        """处理章节/小节评审"""

        # 1. 获取节点信息
        node = DocumentNode.query.filter_by(
            document_id=document_id,
            node_id=node_id
        ).first()

        if not node:
            raise ValueError(f"节点不存在: node_id={node_id}")

        # 获取文档信息
        project_doc = ProjectDocument.query.get(document_id)

        # 2. 创建任务
        task = AITaskService.create_task(
            document_id=document_id,
            task_type='section_review',
            node_id=node.id,
            request_data={'node_id': node_id, 'session_id': session_id}
        )

        # 3. 准备评审数据
        text_list, history_text_list, now_node, write_rule, review_rule, headers,project_doc = AITaskService.get_public_data(document_id, node_id)
        if now_node.level == 1:
            url = f"{app_config['ai_server']}/api/chapter-review"
            prompt = {"chapterReviewPrompt":AITaskService.get_prompt('chapterReviewPrompt')}
            write_rule_key = "chapterWriteRule"
            review_rule_key = "chapterReviewRule"
            title_key = "chapterTitle"
        else:
            url = f"{app_config['ai_server']}/api/section-review"
            prompt = {"sectionReviewPrompt":AITaskService.get_prompt('sectionReviewPrompt')}
            write_rule_key = "sectionWriteRule"
            review_rule_key = "sectionReviewRule"
            title_key = "sectionTitle"
        data = {
            "projectId": f"{project_doc.id}",
            "textList": text_list,
            f"{write_rule_key}": write_rule,
            f"{review_rule_key}": review_rule,
            "industry": project_doc.industry,
            "historyTextList": history_text_list,
            "title": project_doc.title,
            f"{title_key}": now_node.title,
            "prompt": prompt
        }
        current_app.logger.info_module(f'''---------------------------------接口:{url}--------------------------------------\n发去刘豪那边的的数据：\n {json.dumps(data, indent=4,ensure_ascii=False)}\n相关管理后台的文档：
                （chapterReviewPrompt|sectionReviewPrompt）：<b>评审prompt</b>  
                  {write_rule_key}:  <b>大纲（全文写作）规则 </b> 
                  {review_rule_key} : <b>评审规则</b>
''',"admin_view")

        # 发送请求，stream=True 表示流式接收
        try:
            response = None
            response = requests.post(
                url,
                headers=headers,
                json=data,
                stream=True,  # 关键：开启流式模式
                timeout=600
            )
            data = response.json()
            current_app.logger.info_module(f"刘豪那边返回的数据：\n {json.dumps(data, indent=4, ensure_ascii=False)}", "admin_view")
            current_app.logger.info_module(f"\n\n\n", "admin_view")

        except Exception as e:
            current_app.logger.info_module(
                f"AI自动评审、改进建议、生成“我能帮你”列表接口异常-handle_section_review：{e},文件：{e.__traceback__.tb_frame.f_globals['__file__']};行数：{e.__traceback__.tb_lineno}",
                "model")
            current_app.logger.info_module(
                f'''
                接口调用失败！~\n
            ''', "admin_view")
            if response is not None and response.content:
                current_app.logger.info_module(f"respones:{response.content.decode('utf-8')}", "model")
                raise

        # 6. 保存评审结果
        review_data = data.get('review', {})
        score = review_data.get('score',{})

        review_data['ideal_score'] = node.ideal_score = str(score.get('ideal_score',0)) if score.get('ideal_score',0)!="" else None
        node.evaluate = convert_markdown_to_html( data['review']['evaluate'].replace("\\n", "\n"))
        review_data['business_level'] = node.business_level = score.get('business_level',None)
        node.business_describe = score.get('business_describe', '')
        node.suggestion = json.dumps(review_data.get('suggestion', []),ensure_ascii=False)
        node.status = 'reviewed'
        review_data['score'] = node.review_score = str(score.get('real_score',0))
        ImprovementDraft.query.filter_by(document_id=document_id,node_id=node.id).delete()
        data['review']['evaluate'] = node.evaluate
        # 7. 生成"我能帮你"列表并保存到草稿本(取消存入草稿本——草稿本不是to_do_list,而是对话记录)
        db.session.commit()
        # 8. 更新任务状态
        AITaskService.update_task_status(
            task.id,
            'completed',
            response_data=data,
            progress=100
        )

        return {
            "taskId": task.task_uuid,
            "review": review_data
        }


    # =========== 5. "我能帮你"交互 ===========
    @staticmethod
    def handle_help_session(document_id: int, node_id: str, session_id: str,help_text: str):
        """处理"我能帮你"会话"""
        try:
            # 1. 获取节点信息
            node = DocumentNode.query.filter_by(
                document_id=document_id,
                node_id=node_id
            ).first()
            # 获取文档信息
            project_doc = ProjectDocument.query.get(document_id)

            # 2. 创建或获取任务
            task = AITaskService.create_task(
                document_id=document_id,
                task_type='help',
                node_id=node.id,
                request_data={
                    'node_id': node_id,
                    'session_id': session_id,
                    'help_text': help_text
                }
            )
            text_list, history_text_list, now_node, write_rule, review_rule, headers, project_doc = AITaskService.get_public_data(document_id, node_id)
            help_prompt = AITaskService.get_prompt('iCan')
            if node.level == 1:
                write_rule_key = "chapterWriteRule"
            else:
                write_rule_key = "sectionWriteRule"
            try:
                suggestion = []
                try:
                    suggestion = json.loads(node.suggestion)
                except:
                    suggestion = [node.suggestion] if node.suggestion else [""]
                data = {
                    "projectId": f"{document_id}",
                    "sessionId": session_id,
                    "textList": text_list,
                    "review": {
                        "evaluate": node.evaluate,
                        "suggestion": suggestion,
                    },
                    write_rule_key: write_rule,
                    "helpText": help_text,
                    "prompt": {
                        "helpPrompt": help_prompt
                    }
                }
                print(data)
                # 发送请求，stream=True 表示流式接收
                response = None
                response = requests.post(
                    f"{app_config['ai_server']}/api/i-can/chat",
                    headers=headers,
                    json=data,
                    stream=True,  # 关键：开启流式模式
                    timeout=600
                )
                response.raise_for_status()  # 检查 HTTP 状态码

                # 逐块读取流式数据（按字节/行）
                message_id = 0
                messages = ""
                for chunk in response.iter_lines(chunk_size=1024):  # 按行读取
                    if chunk:  # 过滤空块
                        # 字节转字符串（根据接口编码调整，通常 utf-8）
                        data = json.loads(chunk.decode("utf-8"))
                        if "assistantMessage" in data:
                            message_id = data["assistantMessage"]["messageId"]
                            yield json.dumps({'session_id': session_id, "message_id": message_id})
                            continue
                        if 'done' in data:
                            AITaskService.save_conversation_message(
                                task_id=task.id,
                                session_id=session_id,
                                message_id=message_id,
                                role='assistant',
                                content=messages,
                                message_type='question'
                            )
                            AITaskService.update_task_status(task.id, 'completed', progress=100)
                            break
                        messages = messages + data['delta']
                        print(data)
                        yield data['delta']
                #return {"assistantMessage": messages ,"session_id": session_id,"message_id": message_id}
            except Exception as e:
                current_app.logger.info_module(
                    f"我能帮你交互调用异常-handle_help_session：{e},文件：{e.__traceback__.tb_frame.f_globals['__file__']};行数：{e.__traceback__.tb_lineno}",
                    "model")
                if response is not None and response.content:
                    current_app.logger.info_module(f"respones:{response.content.decode('utf-8')}", "model")
                raise
        except Exception as e:
            current_app.logger.error(f"处理帮助会话失败: {str(e)}")
            raise
    @staticmethod
    def handle_help_session_response(document_id: int, node_id: str, session_id: str,message:str,attachment,user_id,message_id):
        """处理"我能帮你"会话"""
        try:
            # 1. 获取节点信息
            node = DocumentNode.query.filter_by(
                document_id=document_id,
                node_id=node_id
            ).first()
            # 获取文档信息
            project_doc = ProjectDocument.query.get(document_id)
            if 'key' in attachment  and   '.' in attachment['key']:
                file_ext = attachment.rsplit('.', 1)[1].lower()
            else:
                file_ext = ''
            if file_ext not in ["jpg", "jpeg", "png", "webp", "bmp", "doc", "docx", "pdf",""]:
                raise Exception("文件格式错误")
            attachments = []
            if file_ext in ["doc", "docx", "pdf"]:
                cache = current_app.extensions.get('cache')
                mark_down_text, image_url = UploadFileService.ai_deal(user_id, attachment, cache, document_id)
            elif file_ext in ["jpg", "jpeg", "png", "webp", "bmp"]:
                image_url = {f"IMAGE_{str(int(time.time() * 100000)) + str(user_id)}":attachment['file_url']}
                mark_down_text = ""
            request_data = {
                'node_id': node_id,
                'session_id': session_id,
                'message': message,
            }
            if file_ext in  ["jpg", "jpeg", "png", "webp", "bmp", "doc", "docx", "pdf"]:
                attach = DocumentAttachment(
                    document_id=document_id,
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
            # 2. 创建或获取任务
            task = AITaskService.create_task(
                document_id=document_id,
                task_type='help',
                node_id=node.id,
                request_data=request_data
            )
            headers = {
                "Content-Type": "application/json",
                "Authorization": "Bearer token123"
            }
            try:
                data = {
                    "projectId": f"{document_id}",
                    "sessionId": session_id,
                     "messages": [
                        {
                            "messageId": message_id,
                            "role": "user",
                            "content": message,
                            "attachment": attachments
                        }
                    ]
                }
                # 发送请求，stream=True 表示流式接收
                response = None
                response = requests.post(
                    f"{app_config['ai_server']}/api/i-can/chat/message",
                    headers=headers,
                    json=data,
                    stream=True,  # 关键：开启流式模式
                    timeout=900
                )
                response.raise_for_status()  # 检查 HTTP 状态码

                # 逐块读取流式数据（按字节/行）
                message_id = 0
                messages = ""
                for chunk in response.iter_lines(chunk_size=1024):  # 按行读取
                    if chunk:  # 过滤空块
                        # 字节转字符串（根据接口编码调整，通常 utf-8）
                        data = json.loads(chunk.decode("utf-8"))
                        if "assistantMessage" in data:
                            message_id = data["assistantMessage"]["messageId"]
                            yield json.dumps({'session_id': session_id, "message_id": message_id,"status":"draft"})
                            continue
                        if 'done' in data:
                            AITaskService.save_conversation_message(
                                task_id=task.id,
                                session_id=session_id,
                                message_id=message_id,
                                role='assistant',
                                content=messages,
                                message_type='question'
                            )
                            AITaskService.update_task_status(task.id, 'completed', progress=100)
                            break
                        print(data['delta'])
                        messages = messages + data['delta']
                        yield data['delta']
                return {"assistantMessage": messages }
            except Exception as e:
                current_app.logger.info_module(
                    f"我能帮你交互调用异常-handle_help_session：{e},文件：{e.__traceback__.tb_frame.f_globals['__file__']};行数：{e.__traceback__.tb_lineno}",
                    "model")
                if response is not None and response.content:
                    current_app.logger.info_module(f"respones:{response.content.decode('utf-8')}", "model")
                raise
        except Exception as e:
            current_app.logger.error(f"处理帮助会话失败: {str(e)}")
            raise
    # =========== 6. 一键合入 ===========
    @staticmethod
    def handle_merge(document_id: int, node_id: str, draft_ids: list) -> dict:
        """处理一键合入"""
        try:
            # 1. 获取节点信息
            node = DocumentNode.query.filter_by(
                document_id=document_id,
                node_id=node_id
            ).first()

            if not node:
                raise ValueError(f"节点不存在: node_id={node_id}")

            # 获取文档信息
            project_doc = ProjectDocument.query.get(document_id)

            # 获取写作规则
            review_rules = AITaskService.get_review_rules()
            rule_text = "\n".join([rule['content'] for rule in review_rules])
            # 2. 创建任务
            task = AITaskService.create_task(
                document_id=document_id,
                task_type='merge',
                node_id=node.id,
                request_data={
                    'node_id': node_id,
                    'draft_ids': draft_ids
                }
            )
            # 3. 收集所有选中的草稿内容
            selected_drafts = ImprovementDraft.query.filter_by(
                document_id=document_id,
                node_id=node.id,
                is_merged=False
            ).all()

            if not selected_drafts:
                raise ValueError("没有选中的草稿内容")
            # 4. 准备合并数据
            text_list, history_text_list, now_node, write_rule, review_rule, headers, project_doc = AITaskService.get_public_data(
                document_id, node_id)
            merge_prompt = AITaskService.get_prompt('oneKeyCombine')
            merge_correct_prompt = AITaskService.get_prompt('oneKeyCombineCheckPrompt')
            if now_node.level==2:
                write_rule_key = "sectionWriteRule"
            else:
                write_rule_key = "chapterWriteRule"
            try:
                suggestion = []
                try:
                    suggestion = json.loads(node.suggestion)
                except:
                    suggestion = [node.suggestion] if node.suggestion else [""]
                data = {
                    "projectId": f"{document_id}",
                    f"{write_rule_key}":write_rule,
                    "textList": text_list,
                    "sessionList": AITaskService.get_session_list(document_id,draft_ids),
                    "historyTextList": history_text_list,
                    "review": {
                        "evaluate": node.evaluate,
                        "suggestion": suggestion,
                        "to_do_list": AITaskService.get_ican_list(document_id,node_id)
                    },
                    "industry": project_doc.industry,
                    "prompt": {
                        "mergePrompt": merge_prompt,
                        "mergeCorrectPrompt": merge_correct_prompt
                    }
                }
                print(json.dumps(data,ensure_ascii=False))
                # 发送请求，stream=True 表示流式接收
                response = None
                response = requests.post(
                    f"{app_config['ai_server']}/api/merge",
                    headers=headers,
                    json=data,
                    stream=True,  # 关键：开启流式模式
                    timeout=600
                )
                json_data = response.json()
                print("返回的json：")
                print(json_data)
                new_texts = json_data.get('textList', [])
                for text in new_texts:
                    text['text'] = convert_markdown_to_html(text['text'].replace("\\n", "\n"))
                AITaskService.update_task_status(task.id, 'completed', progress=100)
                ImprovementDraft.query.filter_by(
                    document_id=document_id,
                    node_id=node.id,
                    is_merged=False
                ).update({"is_merged": True, "is_deleted": True})  # 一键合入的同时设置删除状态
                return {
                    "taskId": task.task_uuid,
                    "texts": new_texts
                }
            except Exception as e:
                current_app.logger.info_module(
                    f" 一键合入接口异常-handle_merge：{e},文件：{e.__traceback__.tb_frame.f_globals['__file__']};行数：{e.__traceback__.tb_lineno}",
                    "model")
                if response is not None and response.content:
                    current_app.logger.info_module(f"respones:{response.content.decode('utf-8')}", "model")
                    raise
        except Exception as e:
            if task:
                AITaskService.update_task_status(task.id, 'failed', error_message=str(e))
            current_app.logger.error(f"一键合入失败: {str(e)}")
            raise

    @staticmethod
    def all_chapters_reviews(document_id,tag=0):
        chapters = DocumentNode.query.filter_by(
            document_id=document_id,
            level=1
        ).filter(
            DocumentNode.status != 'reviewed'
        ).all()
        error = 0
        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = []
            for chapter in chapters:
                future = executor.submit(AITaskService.thread_handle_chapter_review, document_id, chapter.node_id)
                futures.append(future)
            for f in futures:
                try:
                    f.result()
                except Exception as e:
                    error = 1
        if error==1 and tag<3:
            AITaskService.all_chapters_reviews(document_id, tag=tag+1)
        elif error==1 and tag>=2:
            current_app.logger.info_module(
                f"全文评审-逐个未评审的章节评审-handle_full_review-all_chapters_reviews循环超过三次不成功：{e},文件：{e.__traceback__.tb_frame.f_globals['__file__']};行数：{e.__traceback__.tb_lineno}",
                "model")
            raise
    @staticmethod
    def thread_handle_chapter_review(document_id, chapter_node_id):
        from app import app
        with app.app_context():
            AITaskService.handle_section_review(document_id, chapter_node_id)

    # =========== 7. 全文评审 ===========
    @staticmethod
    def handle_full_review(document_id,project_doc) -> dict:
        """处理全文评审"""
        try:

            AITaskService.all_chapters_reviews(document_id)
            all_level_1_nodes = DocumentNode.query.filter_by(document_id=document_id,level=1).order_by(DocumentNode.node_id.asc()).all()
            final_score = 0
            cut_point = 6
            content = ""
            all_scores = {f"{node.node_id}":float(node.review_score)  for node in all_level_1_nodes}
            print(all_scores)
            if  all_scores["1"]<6:
                final_score = round((all_scores["1"]*0.2),1)
                content = '''
                从目前整体评审结果来看，产品立项工作还处于"待澄清市场机会"状态，下一步的工作重点还在于充分识别清楚产品所面对的客户场景与市场机会。建议将下一步重点工作定为:重点审视前文关于机会识别视角的评审建议，进一步细化并完成第1章相关内容，在完成此阶段工作后，再逐步推进后续工作.
                '''
            elif all_scores["2"]<6:
                final_score = round((2+all_scores["2"]*0.1),1)
                content = '''
                从目前的评审结果来看，产品立项工作还处于“待明确产品价值定位”状态，下一步的工作重点还在于清晰地确定产品定位，尽可能避免浮于表面，从专业的视角深入场景提出能给用户有建设性、眼前一亮感觉的产品关键价值，并预测产品可参与市场空间。建议将下一步重点工作定为：重点审视前文关于产品定位视角的评审建议，进一步细化并完成第2章相关内容，在完成此阶段工作后，再逐步推进后续工作
                '''
                if all_scores["1"]<8:
                    content = '''
                    在进一步设计产品关键客户价值的同时，也可以对第1章市场机会内容进行同步审视与刷新，让两件事情互相促进，争取在完成产品价值定位的同时，也进一步把第1章对于市场机会识别的内容做得更扎实。为全篇的产品立项报告工作输出打下一个更好的基础
                    '''
            elif all_scores["3"]<6:
                final_score = round((3+all_scores["3"]*0.1),1)
                content = '''
                    从目前的评审结果来看，产品立项工作还处于“待明确产品包定义”状态，下一步的工作重点还在于清晰地完成产品全价值链条的产品需求与痛点识别，以及对应的产品包全方位关键特性设计与销售目标确定。建议将下一步重点工作定为：重点审视前文
关于产品包定义视角的评审建议，进一步细化并完成第3章相关内容，在完成此阶段工作后，再逐步推进后续工作。
                '''
                if all_scores["2"]<8:
                    content = '''
                      在进一步设计产品包关键特性的同时，也可以对第2章中的产品价值定位进行同步审视与刷新，让两件事情互相促进，争取在完成产品包定义的同时，也进一步把第2章对于产品价值定位的内容做得更扎实。为全篇的产品立项报告工作输出打下一个更好的基础。
                      '''
            elif all_scores["4"]<6:
                final_score = round((4+all_scores["4"]*0.1),1)
                content = '''
                从目前的评审结果来看，产品立项工作已经推进到“执行策略制定”状态，下一步的工作重点在于针对可能阻碍产品商业成功的关键因素，进行充分的执行策略设计，以及壁垒构建策略制定。建议将下一步重点工作定为：重点审视前文关于机会识别视角的评审建议，进一步细化并完成第1章相关内容，在完成此阶段工作后，再逐步推进投入产出计算工作
                '''
                if all_scores["3"]<8 or all_scores["2"]<8:
                    content = '''
                        在进一步完成投入产出计算工作的同时，也可以对第2章、第3章、第4章中的产品价值定位、产品包定义、以及执行策略内容进行同步审视与刷新，让这几件事情与投资收益计算的工作互相印证与促进，争取在完成投资收益计算的同时，也进一步把第2章、第3章、第4章的内容做得更扎实，为全篇的产品立项报告工作输出打下一个更好的基础                    
                    '''
            elif all_scores["5"]<6:
                final_score =round((5+all_scores["4"]*0.1),1)
                content = '''
                从目前的评审结果来看，产品立项工作已经推进到“投资收益计算”状态，下一步的工作重点在于梳理清楚投入产出计算逻辑，建议详细审视前文对于投资收益视角的评审建议，完成产品立项报告的最后一个章节工作
                '''
                if all_scores["3"]<8 or all_scores["2"]<8 or all_scores["4"]:
                    content = '''
                    在进一步完成投入产出计算工作的同时，也可以对第2章、第3章、第4章中的产品价值定位、产品包定义、以及执行策略内容进行同步审视与刷新，让这几件事情与投资收益计算的工作互相印证与促进，争取在完成投资收益计算的同时，也进一步把第2章、第3章、第4章的内容做得更扎实，为全篇的产品立项报告工作输出打下一个更好的基础。
                    '''
            elif all_scores["3"]<8 or all_scores["2"]<8 or all_scores["4"]<8 or all_scores["5"]<8:
                final_score = round(sum([v for v in all_scores.values()])/5,1)
                content = '''
                在进一步完成投入产出计算工作的同时，也可以对第2章、第3章、第4章中的产品价值定位、产品包定义、以及执行策略内容进行同步审视与刷新，让这几件事情与投资收益计算的工作互相印证与促进，争取在完成投资收益计算的同时，也进一步把第2章、第3章、第4章的内容做得更扎实，为全篇的产品立项报告工作输出打下一个更好的基础。
                '''
            else:
                content = '''
                从目前的评审结果来看，您的产品立项工作已经达到了非常专业的水准，下一步的工作，可以以此报告为原型，启动与投资决策委员会团队各委员以及主席的立项前沟通，认真听取意见。并在按意见完成修改后，参与产品立项决策会议，听取最终的立项决策意见
                '''
                final_score = round(sum([v for v in all_scores.values()])/5,1)
            ProjectDocument.query.filter_by(id=document_id).update({"total_review_score":final_score,"total_review_content":content})
            db.session.commit()
            result = {"total_review_score":final_score,"total_review_content":content}
            return result
            # 2. 创建任务
            '''
           task = AITaskService.create_task(
                document_id=document_id,
                task_type='full_review',
                request_data={}
            )

            review_list = []
            chapters = DocumentNode.query.filter_by(
                document_id=document_id,
                level=1
            ).all()

            for chapter in chapters:
                # 解析评审详情
                summary_list = []
                detail = chapter.review_detail or ""
                if detail:
                    # 简单解析，实际可能需要更复杂的逻辑
                    summary_list = [line.strip() for line in detail.split('\n') if line.strip()]

                review_list.append({
                    "chapterTitle": chapter.title,
                    "chapterId": chapter.node_id,
                    "review": {
                        "score": chapter.review_score or 0,
                        "evaluate": chapter.evaluate or "",
                        "suggestion": chapter.suggestion or ""
                    }
                })

            # 4. 调用AI服务进行全文评审
            full_review_prompt = AITaskService.get_prompt('fullReviewPrompt')
            full_review_text = ReviewRules.query.order_by(ReviewRules.id.desc()).first()

            data = {
                "projectId": f"{document_id}",
                "title": project_doc.title,
                 "reviewList": review_list,
                "fullReviewText": full_review_text,
                "prompt": {
                    "fullReviewPrompt": full_review_prompt
                }
            }
            headers = {
                "Content-Type": "application/json",
                "Authorization": "Bearer token123"
            }
            response = requests.post(
                f"{app_config['ai_server']}/api/full-review",
                headers=headers,
                json=data,
                stream=True,  # 关键：开启流式模式
                timeout=600
            )
            json_data = response.json()
            # 5. 更新任务状态
            AITaskService.update_task_status(
                task.id,
                'completed',
                response_data=json_data,
                progress=100
            )
            return {
                "taskId": task.task_uuid,
                "fullReviewAns": json_data.get('fullReviewAns', '')
            }
            '''
        except Exception as e:
            current_app.logger.info_module(
                f"{e},文件：{e.__traceback__.tb_frame.f_globals['__file__']};行数：{e.__traceback__.tb_lineno}",
                "model")
            current_app.logger.error(f"全文评审失败: {str(e)}")
            raise

    # =========== 8. 全文AI润色 ===========
    @staticmethod
    def handle_full_polish(document_id: int) -> dict:
        """处理全文AI润色"""
        try:
            # 1. 创建任务
            task = AITaskService.create_task(
                document_id=document_id,
                task_type='full_polish',
                request_data={}
            )

            # 2. 获取完整文档
            full_text = ProjectDocumentService.get_full_text_for_ai(document_id)

            # 3. 调用AI服务进行润色
            polish_prompt = AITaskService.get_prompt('fullTextPolishing')

            ai_request = {
                "task": "fullPolish",
                "fullText": full_text,
                "polishPrompt": polish_prompt
            }

            current_app.logger.info(f"调用AI全文润色: {ai_request}")
            headers = {
                "Content-Type": "application/json",
                "Authorization": "Bearer token123"
            }
            data = {
                "projectId": f"{document_id}",
                "fullText": AITaskService.get_all_nodes(document_id),
                "prompt": {
                    "polishPrompt": polish_prompt,
                }
            }
            #print(json.dumps(data, ensure_ascii=False))
            # 发送请求，stream=True 表示流式接收
            response = None
            response = requests.post(
                f"{app_config['ai_server']}/api/full-polish",
                headers=headers,
                json=data,
                stream=True,  # 关键：开启流式模式
                timeout=600
            )
            json_data = response.json()
            for chapter in json_data.get('newFullText', []):
                DocumentNode.query.filter_by(document_id=document_id,node_id=chapter['chapterId']).update({"title":chapter['chapterTitle']})
                for child in chapter['children']:
                    DocumentNode.query.filter_by(document_id=document_id, node_id=child['sectionId']).update({"title": child['sectionTitle'],"content": convert_markdown_to_html(child['text'].replace("\\n", "\n"))})
            db.session.commit()
            return {
                "taskId": task.task_uuid,
                "newFullText": json_data.get('newFullText', [])
            }

        except Exception as e:
            current_app.logger.error(f"全文润色失败: {str(e)}")
            raise

    # =========== 9. 评审立项报告（新文件） ===========
    @staticmethod
    def handle_text_restruct(file_path: str, project_id: str = None) -> dict:
        """处理文本结构化重组"""
        try:
            # 1. 创建任务
            task = AITaskService.create_task(
                document_id=None,
                task_type='text_restruct',
                request_data={'file_path': file_path, 'project_id': project_id}
            )

            # 2. 获取提示词
            restruct_prompt = AITaskService.get_prompt('restruct')
            outline_prompt = AITaskService.get_prompt('outline')

            # 3. 调用AI服务进行结构化重组
            ai_request = {
                "task": "textRestruct",
                "file_path": file_path,
                "restructPrompt": restruct_prompt,
                "outlinePrompt": outline_prompt
            }

            current_app.logger.info(f"调用AI结构化重组: {ai_request}")

            ai_response = AITaskService.call_ai_service('/api/text-restruct', ai_request)

            # 4. 更新任务状态
            AITaskService.update_task_status(
                task.id,
                'completed',
                response_data=ai_response,
                progress=100
            )

            return {
                "taskId": task.task_uuid,
                "docGuide": ai_response.get('docGuide', ''),
                "outline": ai_response.get('outline', []),
                "fullText": ai_response.get('fullText', [])
            }

        except Exception as e:
            current_app.logger.error(f"文本结构化重组失败: {str(e)}")
            raise

    # =========== 10. 悬浮球 ===========
    @staticmethod
    def handle_float_ball(title: str, text: str, target_text: str, user_input: str) -> dict:
        """处理悬浮球请求"""
        try:
            # 获取提示词
            float_prompt = AITaskService.get_prompt('float')

            # 准备AI请求数据
            ai_request = {
                "task": "float",
                "title": title,
                "text": text,
                "targetText": target_text,
                "userInput": user_input,
                "floatPrompt": float_prompt
            }

            current_app.logger.info(f"调用悬浮球AI: {ai_request}")

            # 调用AI服务
            ai_response = AITaskService.call_ai_service('/api/float', ai_request)

            return {
                "task": "float",
                "floatText": ai_response.get('floatText', '')
            }

        except Exception as e:
            current_app.logger.error(f"悬浮球处理失败: {str(e)}")
            raise

    # =========== 11. 知识库相关 ===========
    @staticmethod
    def index_document_to_kb(document_id:int =None):
        """将文档索引到知识库"""
        attachments = DocumentAttachment.query.filter_by(document_id=document_id).all()
        for attachment in attachments:
            try:
                payload = {
                    "action": "index",
                    "projectId": f"{document_id}",
                    "document_id": f"{attachment.id}",
                    "image_url": attachment.img_urls,
                    "text": attachment.content
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
                if 'status' in data:
                    if data['status'] == 'indexed':
                        attachment.is_in_knowledge_base = 1
                        db.session.commit()
            except Exception as e:
                current_app.logger.info_module(f"知识库创建异常-index_document_to_kb：{e},文件：{e.__traceback__.tb_frame.f_globals['__file__']};行数：{e.__traceback__.tb_lineno}","model")
                if response is not None and response.content:
                    current_app.logger.info_module(f"respones:{response.content.decode('utf-8')}","model")
        return None

    @staticmethod
    def delete_document_from_kb(document_id: int) -> bool:
        """从知识库删除文档"""
        try:
            kb_doc = KnowledgeBaseDocument.query.get(document_id)
            if not kb_doc:
                raise ValueError(f"知识库文档不存在: {document_id}")

            # 更新状态为删除中
            kb_doc.status = 'deleting'

            db.session.commit()

            # 调用Agent服务删除索引
            agent_request = {
                "action": "delete",
                "projectId": kb_doc.project_id,
                "document_id": f"doc_{document_id}"
            }

            agent_response = AITaskService.call_agent_service('/api/kb/documents', agent_request)

            if agent_response.get('status') == 'deleted':
                # 删除文件
                FileHandler.delete_file(kb_doc.file_url)

                # 更新记录状态
                kb_doc.status = 'deleted'
                kb_doc.deleted_at = datetime.now()

                db.session.commit()
                return True
            else:
                kb_doc.status = 'failed'
                kb_doc.error_reason = agent_response.get('error', '删除失败')
                db.session.commit()
                return False

        except Exception as e:
            current_app.logger.error(f"删除知识库文档失败: {str(e)}")
            return False

    # =========== 工具方法 ===========
    @staticmethod
    def create_task(document_id: int, task_type: str, node_id: str = None,
                    request_data: dict = None) -> Task:
        """创建任务记录"""
        try:
            print(request_data)
            task = Task(
                task_uuid=AITaskService.generate_task_uuid(),
                document_id=document_id,
                node_id=node_id,
                task_type=task_type,
                status='created',
                request_data=request_data or {},
                created_at=datetime.now()
            )

            db.session.add(task)
            db.session.flush()

            current_app.logger.info(f"创建任务成功: task_uuid={task.task_uuid}, type={task_type}")
            return task

        except Exception as e:
            current_app.logger.error(f"创建任务失败: {str(e)}")
            raise

    @staticmethod
    def update_task_status(task_id: int, status: str, response_data: dict = None,
                           error_message: str = None, progress: int = None):
        """更新任务状态"""
        try:
            task = Task.query.get(task_id)
            if not task:
                raise ValueError(f"任务不存在: {task_id}")

            task.status = status
            task.updated_at = datetime.now()

            if response_data:
                task.response_data = response_data

            if error_message:
                task.error_message = error_message

            if progress is not None:
                task.progress = progress

            if status == 'processing' and not task.started_at:
                task.started_at = datetime.now()
            elif status in ['completed', 'failed', 'cancelled'] and not task.completed_at:
                task.completed_at = datetime.now()

            db.session.commit()

        except Exception as e:
            current_app.logger.error(f"更新任务状态失败: {str(e)}")
            raise

    @staticmethod
    def save_conversation_message(task_id: int, session_id: str, message_id: str,
                                  role: str, content: str, message_type: str = None,
                                  attachment_paths: list = None, message_metadata: dict = None):
        """保存对话消息"""
        try:
            message = ConversationMessage(
                task_id=task_id,
                session_id=session_id,
                message_id=message_id,
                role=role,
                message_type=message_type,
                content=content,
                message_metadata=message_metadata or {},
                created_at=datetime.now()
            )

            db.session.add(message)
            db.session.commit()

        except Exception as e:
            current_app.logger.error(f"保存对话消息失败: {str(e)}")
            raise

    @staticmethod
    def get_outline_rules():
        """获取大纲规则"""
        try:
            rules = OutlineRules.query.order_by(OutlineRules.sort).all()
            return [
                {
                    'title_num': rule.title_num,
                    'content': rule.content
                }
                for rule in rules
            ]
        except Exception as e:
            current_app.logger.error(f"获取大纲规则失败: {str(e)}")
            return []

    @staticmethod
    def get_review_rules():
        """获取评审规则"""
        try:
            rules = ReviewRules.query.order_by(ReviewRules.sort).all()
            return [
                {
                    'title_num': rule.title_num,
                    'content': rule.content
                }
                for rule in rules
            ]
        except Exception as e:
            current_app.logger.error(f"获取评审规则失败: {str(e)}")
            return []

    @staticmethod
    def call_ai_service(endpoint: str, data: dict) -> dict:
        """调用AI服务（模拟实现）"""
        # 这里应该实现实际的HTTP请求到AI服务
        # 为了演示，我们返回模拟数据

        current_app.logger.info(f"调用AI服务: {endpoint}")

        # 模拟延迟
        time.sleep(1)

        # 根据不同的端点返回不同的模拟数据
        if endpoint == '/api/industry':
            return {
                "task": "industry",
                "industryName": "互联网科技"
            }
        elif endpoint == '/api/project-outline':
            return {
                "docGuide": [
                    {
                        "keyword": "核心关键词1（如Who）",
                        "content": "该关键词对应的具体撰写指引内容"
                    },
                    {
                        "keyword": "核心关键词2（如What）",
                        "content": "该关键词对应的具体撰写指引内容"
                    }
                ],
                "outline": [
                    {
                        "nodeId": "1",
                        "level": 1,
                        "title": "项目概述",
                        "keyPoint": "本章写作要点xxxx",
                        "children": [
                            {"nodeId": "1.1", "level": 2, "title": "项目背景"},
                            {"nodeId": "1.2", "level": 2, "title": "项目目标"}
                        ]
                    }
                ]
            }
        elif endpoint == '/api/project-outline/keyPoint':
            return {
                "task": "outline",
                "title": "项目概述",
                "keyPointList": [
                    {"nodeId": "1.1", "keyPoint": "本节写作要点1"},
                    {"nodeId": "1.2", "keyPoint": "本节写作要点2"}
                ]
            }
        elif endpoint == '/api/heuristic-writing':
            return {
                "nodeId": "1.1",
                "title": "项目背景",
                "task": "heuristicWriting",
                "sessionId": "test_session",
                "status": "ask",
                "assistantMessage": {
                    "messageId": "m_ai_1",
                    "role": "assistant",
                    "type": "question",
                    "content": "首先请回答你希望你的场景是电商还第三方仓库？"
                }
            }
        elif endpoint == '/api/heuristic-writing/message':
            # 模拟第2-5轮的问题
            message_count = len(data.get('messages', []))
            if message_count < 9:  # 5轮 * 2 - 1 = 9条消息时结束
                return {
                    "nodeId": "1.1",
                    "title": "项目背景",
                    "task": "heuristicWriting",
                    "status": "ask",
                    "sessionId": "test_session",
                    "assistantMessage": {
                        "messageId": f"m_ai_{message_count // 2 + 1}",
                        "role": "assistant",
                        "type": "question",
                        "content": f"第{message_count // 2 + 1}个问题..."
                    }
                }
            else:
                return {
                    "nodeId": "1.1",
                    "title": "项目背景",
                    "task": "heuristicWriting",
                    "status": "draft",
                    "sessionId": "test_session",
                    "assistantMessage": {
                        "messageId": "m_ai_6",
                        "role": "assistant",
                        "type": "text",
                        "content": "这是根据5轮问答生成的正文内容..."
                    }
                }
        elif endpoint == '/api/section-review':
            return {
                "task": "sectionReview",
                "nodeId": "1.1",
                "title": "项目背景",
                "sessionId": "test_session",
                "review": {
                    "score": 5,
                    "evaluate": "市场机会分析的评估原因分析",
                    "suggestion": "市场机会分析的改进建议",
                    "to_do_list": [
                        "我能帮你把目标写得更量化",
                        "我能帮你补充市场数据"
                    ]
                }
            }
        elif endpoint == '/api/i-can/chat':
            return {
                "task": "help",
                "nodeId": "1.1",
                "title": "项目背景",
                "sessionId": "test_session",
                "assistantMessage": {
                    "messageId": "m_ai_1",
                    "role": "assistant",
                    "content": "我可以帮您优化目标描述..."
                }
            }
        elif endpoint == '/api/i-can/chat/message':
            return {
                "task": "help",
                "nodeId": "1.1",
                "title": "项目背景",
                "sessionId": "test_session",
                "assistantMessage": {
                    "messageId": "m_ai_2",
                    "role": "assistant",
                    "content": "这是进一步的帮助内容..."
                }
            }
        elif endpoint == '/api/merge':
            return {
                "nodeId": "1.1",
                "title": "项目背景",
                "task": "merge",
                "texts": [
                    {"nodeId": "1.1", "level": 2, "title": "项目背景", "text": "合并后的正文内容..."}
                ]
            }
        elif endpoint == '/api/full-review':
            return {
                "task": "fullReview",
                "fullReviewAns": "全文评审结果..."
            }
        elif endpoint == '/api/full-polish':
            return {
                "task": "full_polish",
                "newFullText": [
                    {
                        "chapterId": "1",
                        "chapterTitle": "项目概述",
                        "children": [
                            {
                                "sectionId": "1.1",
                                "sectionTitle": "项目背景",
                                "text": "润色后的正文内容1.1...",
                                "image_url": {}
                            },
                            {
                                "sectionId": "1.2",
                                "sectionTitle": "项目目标",
                                "text": "润色后的正文内容1.2...",
                                "image_url": {}
                            }
                        ]
                    },
                    {
                        "chapterId": "2",
                        "chapterTitle": "技术方案",
                        "children": [
                            {
                                "sectionId": "2.1",
                                "sectionTitle": "架构设计",
                                "text": "润色后的正文内容2.1...",
                                "image_url": {}
                            },
                            {
                                "sectionId": "2.2",
                                "sectionTitle": "实现细节",
                                "text": "润色后的正文内容2.2...",
                                "image_url": {}
                            }
                        ]
                    }
                ]
            }
        elif endpoint == '/api/text-restruct':
            return {
                "docGuide": "全文写作要点...",
                "outline": [
                    {
                        "nodeId": "1",
                        "level": 1,
                        "title": "项目概述",
                        "keyPoint": "本章写作要点",
                        "children": [
                            {"nodeId": "1.1", "level": 2, "title": "项目背景", "keyPoint": "本节写作要点"}
                        ]
                    }
                ],
                "fullText": [
                    {
                        "nodeId": "1",
                        "title": "项目概述",
                        "level": 1,
                        "children": [
                            {"nodeId": "1.1", "level": 2, "title": "项目背景", "text": "结构化后的正文..."}
                        ]
                    }
                ]
            }
        elif endpoint == '/api/float':
            return {
                "task": "float",
                "floatText": "这是悬浮球生成的文本"
            }
        else:
            return {"status": "success", "data": "模拟AI响应"}

    @staticmethod
    def call_agent_service(endpoint: str, data: dict) -> dict:
        """调用Agent服务（模拟实现）"""
        current_app.logger.info(f"调用Agent服务: {endpoint}")
        time.sleep(0.5)

        if data.get('action') == 'index':
            return {
                "document_id": data['document_id'],
                "status": "indexed",
                "chunk_count": 10
            }
        elif data.get('action') == 'delete':
            return {
                "document_id": data['document_id'],
                "status": "deleted"
            }
        else:
            return {"status": "success"}

    @staticmethod
    def get_public_data(document_id,node_id):
        current_node = DocumentNode.query.filter_by(document_id=document_id,node_id=node_id).first()
        text_list = []
        if current_node.level == 2:
            current_section_content, tag, current_section_urls = aliOss.get_ai_contents(document_id, current_node.content, 0,{})
            text_list.append({
                            "sectionId": current_node.node_id,
                            "sectionTitle": current_node.title,
                            "text": current_section_content,
                            "image_url": current_section_urls
                        })
        else:
            child_nodes = DocumentNode.query.filter_by(
                document_id=document_id,
                parent_id=node_id
            ).order_by(DocumentNode.order_num).all()
            for node in child_nodes:
                current_section_content, tag, current_section_urls = aliOss.get_ai_contents(document_id, current_node.content, 0,{})
                text_list.append({
                    "sectionId": node.node_id,
                    "sectionTitle": node.title,
                    "text": current_section_content,
                    "image_url": current_section_urls
                })
        pre_chapters = DocumentNode.query.filter(DocumentNode.document_id == document_id,DocumentNode.node_id < node_id,DocumentNode.level==1).order_by(DocumentNode.node_id.asc()).all()
        history_text_list = []
        tag = 0
        for pre_chapter in pre_chapters:
            children = DocumentNode.query.filter(DocumentNode.document_id==document_id,DocumentNode.parent_id==pre_chapter.id,DocumentNode.node_id < node_id).order_by(DocumentNode.node_id.asc()).all()
            children_list = []
            for child in children:
                ai_content,tag,ai_urls = aliOss.get_ai_contents(document_id,child.content,tag,{})
                children_list.append(
                    {
                        "sectionId": child.node_id,
                        "sectionTitle": child.title,
                        "text": ai_content,
                        "image_url":ai_urls
                    }
                )
            history_text_list.append({
                "chapterId": pre_chapter.node_id,
                "chapterTitle": pre_chapter.title,
                "children":children_list
            })
        write_rule = OutlineRules.query.filter_by(title_num=node_id).first()
        review_rule  = ReviewRules.query.filter_by(title_num=node_id).first()
        write_rule_content = write_rule.content if write_rule and write_rule.content else ""
        review_rule_content = review_rule.content if review_rule and review_rule.content else ""
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer token123"
        }
        project_doc = ProjectDocument.query.get(document_id)
        return text_list,history_text_list,current_node,write_rule_content,review_rule_content,headers,project_doc

    @staticmethod
    def get_session_list(document_id, draft_ids):
       session_list = []
       improvement_drafts = ImprovementDraft.query.filter(ImprovementDraft.id.in_(draft_ids), ImprovementDraft.document_id==document_id).all()
       session_ids = [draft.session_id for draft in improvement_drafts]
       for session_id in session_ids:
           messages = ConversationMessage.query.filter(ConversationMessage.session_id==session_id).all()
           messages_list = []
           for message in messages:
                m = {
                    "messageId": message.message_id,
                    "role": message.role,
                    "content": message.content,
                }
                if message.document_attachments_id!=0:
                    attach = DocumentAttachment.query.filter(DocumentAttachment.id==message.document_attachments_id).first()
                    m["attachments"]= [
                        {
                            "text": attach.content,
                            "image_url": attach.img_urls
                        }
                    ]
                messages_list.append(m)
           session_list.append({"sessionId":session_id,"messages":messages_list})
       print(session_list)
       return session_list
    @staticmethod
    def get_ican_list(document_id,node_id):
        drafts = ImprovementDraft.query.filter_by(document_id=document_id,node_id=node_id)
        ican_list = []
        for draft in drafts:
            ican_list.append("help_text")
        return ican_list

    @staticmethod
    def get_all_nodes(document_id):
        nodes = DocumentNode.query.filter_by(document_id=document_id).order_by(DocumentNode.node_id.asc()).all()
        full_text = []
        for node in nodes:
            if node.level==1:
                chapter = {
                    'chapterId': node.node_id,
                    'chapterTitle': node.title
                }
                children = []
                tag = 0
                for level2_node in nodes:
                    if level2_node.level == 2 and level2_node.parent_id == node.id:
                        content = level2_node.content if level2_node.content is not None  else ""
                        content,tag,ai_urls = aliOss.get_ai_contents(node.id,content,tag,{})
                        section ={
                            "sectionId":level2_node.node_id,"sectionTitle":level2_node.title,"text":content,"image_url":ai_urls
                        }
                        children.append(section)
                chapter['children'] = children
                full_text.append(chapter)
        return full_text