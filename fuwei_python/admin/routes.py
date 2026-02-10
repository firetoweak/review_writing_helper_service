import hashlib
import threading
import time

from flask import Blueprint, render_template, request, redirect, g, jsonify, session, send_file, Response, current_app
from sqlalchemy import or_

from conf.db import db
from conf.config import app_config
from models.model.model import Models
from models.doc_files.model import DocFiles
from models.users.models import User, MobileUserRight
from models.admin.model import AdminUser, AdminRights
from models.cammand import cammand
from models.ai_sug_score.model import AiSugScore
from models.lx_ai_sug_score.model import LxAiSugScore
from common.aliOss import aliOss
import mammoth
import markdownify
from datetime import datetime
import os
import re
import pandas as pd
from common.zip import zip
import subprocess
from urllib.parse import urlparse
import json

from services import defect_services
from services.defect_services import DefectStageService, DefectWorkflowService, DefectService, DefectStageDataService, \
    DefectFlowHistoryService
from services.lx_ai_val_service import LxAiValSrvice
from models.model.model import ModuleToModel
from models.defect.model import (
    Defect, DefectStatus, DefectStage, StageStatus, DefectLocaleInvitation,
    InvitationStatus, DefectSolutionDivision, DefectStageCollaborator,
    CollaboratorRole, DefectStageData, DataType, EvaluationMethod,
    DefectStageCombineRecord, DefectReminder, ReminderType, ReminderStatus,
    DefectFlowHistory, ActionType, DefectRejection, RejectionType,
    DefectStageType, DefectCounter, DefectSeverity, data_type_map, STATUS_MAPPING
)
from flask_paginate import  get_page_args,Pagination

from services.product_line_services import ProductLineService
from services.tech_group_service import TechGroupService
from models.project_document.model import Prompt,OutlineRules,ReviewRules,IndustryList,DocumentAttachment


admin = Blueprint('admin', __name__)

@admin.before_request
def before_request():
    if request.path !="/admin/login":
        if 'fc_admin_user_id' not in session or 'fc_admin_user_name' not in session:
            js_code = """
            <script type="text/javascript">
                    alert('请重新登录1');
                    location.href="/admin/login"
            </script> 
            """
            return js_code
    #g.menuData = adminRights.getMenu()
    url = request.url
    parsed = urlparse(url)
    g.url =  parsed.path + '?' + parsed.query if parsed.query else parsed.path
    g.menu_pid = request.values.get("menu_pid","-1")
    g.menu_id = request.values.get("menu_id","-1")
    g.query = parsed.query
    if 'fc_admin_rights' in session:
        g.show_menu = AdminRights.getUserMenu(session['fc_admin_rights'], session['fc_admin_user_id'])
        #g.user_rights = session['fc_admin_rights']
    return None


@admin.route('/login', methods=['GET','POST'])
def login():
    if request.method == "GET":
        return render_template('admin/login.html')
    else:
        data = request.json
        item = AdminUser.getLoginUser(data)
        if item==None:
            return jsonify({'msg': '账号密码错误', "code": -1}), 200
        else:
            session['fc_admin_user_id'] = item.user_id
            session['fc_admin_user_name'] = item.user_name
            session['fc_admin_rights'] = str(item.rights).split(',')
            return jsonify({'msg': '登录成功', "code": 1}), 200

@admin.route('/logout')
def logout():
    session.pop('fc_admin_user_id', None)
    session.pop('fc_admin_user_name', None)
    session.pop('fc_admin_rights', None)
    session.pop('fc_admin_rights', None)
    return redirect("/admin/login")
@admin.route('/models', methods=['GET','POST'])
def models():
    if request.method == "GET":
        items = Models.getAll()
        module_all = ModuleToModel.get_all()
        return render_template('admin/models.html',items=items,module_all=module_all)
    else:
        data = request.json
        ModuleToModel.edit_one(data)
        return jsonify({'msg': '修改成功',"code":1}),200
@admin.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    if file:
        id = request.values.get('id',0)
        upload_type = request.values.get('upload_type','val')
        filenameExt = file.filename
        fileExtension = os.path.splitext(filenameExt)[1]
        if fileExtension.lower()!=".docx" and fileExtension.lower()!=".doc":
            return jsonify({'msg': '只允许上传word文档', "code": 1}), 200
        fileName = os.path.splitext(filenameExt)[0]
        filename = fileName+datetime.now().strftime("%Y%m%d%H%M%S")+'-admin-'+fileExtension
        local_file = f'./tmp/upload/{filename}'
        file.save(local_file)
        key,url = aliOss.uploadSignDoc(local_file)
        with open(local_file, "rb") as docx_file:
            # 转化Word文档为HTML
            result = mammoth.convert_to_html(docx_file)
            html = result.value
            md = markdownify.markdownify(html, heading_style="ATX")
        DocFiles.editOneUpload(id, html, md, key, upload_type)
        os.remove(local_file)
        return jsonify({'msg': '上传成功', "code": 1}), 200

@admin.route('/upload_lx2_file', methods=['POST'])
def upload_lx2_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    if file:
        upload_name = request.values.get('upload_name','outlineRule')
        filename_ext = os.path.splitext(file.filename)[1]
        if filename_ext.lower()!=".md":
            return jsonify({'msg': '只允许上传markdown文档', "code": 1}), 200
        file_name = os.path.splitext(file.filename)[0]
        if upload_name=="outlineRule":
            file_name = "全文写作规则"
        elif upload_name=="reviewRule":
            file_name = "评审规则"
        else:
            file_name = "行业规则"
        filename = file_name+'-'+datetime.now().strftime("%Y%m%d%H%M%S")+'-admin-'+filename_ext
        local_file = f'./tmp/upload/{filename}'
        file.save(local_file)
        key,url = aliOss.uploadSignDoc(local_file)
        with open(local_file, "r", encoding="utf-8") as mark_down_file:
            md_content = mark_down_file.read()
        DocumentAttachment.delete_admin_file(upload_name)
        DocumentAttachment.add_one({"document_id":None,
                                    "filename":upload_name,
                                    "file_url":f"{key}",
                                    "is_admin":1,
                                    "mime_type":"md",
                                    "file_size":0,
                                    "is_in_knowledge_base":False,
                                    "knowledge_doc_id":None
                                    })
        if upload_name=='outlineRule' or upload_name=='reviewRule':
            if upload_name=='outlineRule':
                model = OutlineRules
            else:
                model = ReviewRules
            # for data in datas:
            #     if upload_name=='outlineRule':
            #         prompt[data['title_num'] if data.title_num else "0"] = data.prompt

            #model.query.delete()
            single_hash_pattern = r"(?<!#)#(?!#)"
            content_list =re.split(single_hash_pattern, md_content)
            if content_list[0]!="":
                rs = model.query.filter_by(title_num="").first()
                if not rs:
                    data = {}
                    data['title_num'] = ""
                    data['sort'] = 0
                    data['content'] = content_list[0]
                    model.add_one(data)
                else:
                    rs.content = content_list[0]
            sort = 1
            for i in range(1,len(content_list)):
                data = {}
                content2_list = content_list[i].split("##")
                for content2 in content2_list:
                    match  = re.match(r'^(\d+\.\d*)', content2.strip())
                    if match:
                        data['title_num'] = match.group(1)
                        if data['title_num'][-1:] ==".":
                            data['title_num'] =data['title_num'][0:-1]
                    else:
                        data['title_num'] = "-1"
                    rs = model.query.filter_by(title_num=data['title_num']).first()
                    if not rs:
                        data['sort'] = sort
                        data['content'] = content2.strip()
                        model.add_one(data)
                        sort = sort+1
                    else:
                        rs.content = content2.strip()
                        db.session.commit()
        elif upload_name=='industryCharacteristics':
            IndustryList.query.delete()
            content_list = md_content.split("#")
            for i in range(0,len(content_list)):
                data = {}
                lines = content_list[i].split("\n")
                name = lines[0]
                content =  ''.join(lines[1:])
                data['name'] = name
                data['content'] = content
                IndustryList.add_one(data)
        return jsonify({'msg': '上传成功', "code": 1,'data':{"key":key,"url":url,"md_content":md_content}}), 200

@admin.route('/download_lx2_file', methods=['GET'])
def download_lx2_file():
    def remove_file(filePath):
        if os.path.exists(filePath):
            time.sleep(60)
            os.remove(filePath)
    local_path = f'./tmp/download/admin/'
    if not os.path.exists(local_path):
        os.mkdir(local_path)
    doc = DocumentAttachment.get_admin_file_by_name(request.values.get('filename'))
    tmp_file_path,file_name = aliOss.downLoadOne(doc.file_url,local_path)
    try:
        return send_file(
            tmp_file_path,
            mimetype='application/octet-stream',
            as_attachment=True,
            download_name=file_name,  # Flask 2.0+ 支持
            # 对于旧版 Flask，用 `attachment_filename`
            # attachment_filename=fileName,
        )
    finally:
        # if os.path.exists(tmp_file_path):
        #     os.remove(tmp_file_path)
        thread = threading.Thread(target=remove_file,args=(tmp_file_path,))
        thread.start()
@admin.route('/prompt', methods=['GET','POST'])
def prompt():
    if request.method == "GET":
        add = str(request.values.get('add',''))
        type = int(request.values.get('type',-1))
        child_type_1 =  int(request.values.get('child_type_1',-1))
        child_type_2 =  int(request.values.get('child_type_2',-1))
        fileName = request.values.get('file_name',"")
        docId = int(request.values.get('id',-1))
        pagination,items = DocFiles.getList(type=type, child_type_1=child_type_1, child_type_2=child_type_2, file_name=fileName)
        html = ""
        cammand = ""
        markdown = ""
        file_name =""
        item = DocFiles.getOneById(docId)
        if item is not None:
            html = item.html
            cammand = item.cammand
            markdown = item.markdown
            file_name = item.file_name
        return render_template('admin/prompt01.html',html=html,
                               items=items,
                               type=type,
                               child_type_1=child_type_1,
                               child_type_2=child_type_2,
                               doc_id=docId,
                               pagination=pagination,
                               cammand =cammand,
                               add = add,
                               markdown = markdown,
                                file_name =file_name,
                               page = request.values.get('page','1')
                               )
    else:
        data = request.json
        #data['markdown'] = markdownify.markdownify(data['html'], heading_style="ATX")
        if data['id']!= '-1':
            DocFiles.editOne01(data)
        else:
            data['type'] = '10'+str(data['type'])
            data['step'] = '-1'
            DocFiles.addOne(data)
        return jsonify({'msg': '编辑成功', "code": 1}), 200

@admin.route('/lx_prompt', methods=['GET','POST'])
def lxPrompt():
    if request.method == "GET":
        type = int(request.values.get('type',-1))
        child_type_1 =  int(request.values.get('child_type_1',-1))
        child_type_2 =  int(request.values.get('child_type_2',-1))
        fileName = request.values.get('file_name',"")
        docId = int(request.values.get('id',-1))
        step = int(request.values.get('step',0))
        pagination,items = DocFiles.getList(type=type, child_type_1=child_type_1, child_type_2=child_type_2, file_name=fileName)
        html = "请点选左边列表文档"
        cammand = ""
        title_show = ""
        html_content = ""
        ifile_name = ""
        big_title_show = ""
        if child_type_1<100:
            for item in  items:
                if docId==item.id:
                    html = item.html
                    cammand = item.cammand
                    title_show = item.title_show
                    child_type_1 = item.child_type_1
                    html_content = item.html_content
                    ifile_name = item.file_name
                    big_title_show = item.big_title_show
        else:
            item =DocFiles.getOne(type, child_type_1, child_type_2, step)
            cammand = item.cammand
        return render_template('admin/prompt2.html',html=html,
                               items=items,
                               type=type,
                               child_type_1=child_type_1,
                               child_type_2=child_type_2,
                               doc_id=docId,
                               pagination=pagination,
                               cammand =cammand,
                               title_show = title_show,
                               html_content = html_content,
                               ifile_name = ifile_name,
                               sfile_name = fileName,
                               big_title_show = big_title_show
                               )
    else:
        data = request.json
        if data['child_type_1'] <100:
            data['markdown'] = markdownify.markdownify(data['html'], heading_style="ATX")
            data['markdown_content'] = markdownify.markdownify(data['html_content'], heading_style="ATX")
            DocFiles.editOne2(data)
        else:
            DocFiles.editOneCammand(data)
        return jsonify({'msg': '上传成功', "code": 1}), 200

@admin.route('/lx2_prompt', methods=['GET','POST'])
def lx2Prompt():
    '''
    立项prompt设置
    '''
    if request.method == "GET":
        prompts = Prompt.query.filter(Prompt.is_active==1).all()
        prompt_dict = {}
        for prompt in prompts:
            prompt_dict[prompt.name] = prompt.content
        docs = DocumentAttachment.get_admin_files()
        doc_dict = {}
        for doc in docs:
            print(doc.filename)
            doc_dict[doc.filename] = doc
        return render_template('admin/prompt3.html', prompt_dict=prompt_dict,doc_dict=doc_dict)
    else:
        datas = request.form
        for key,val in datas.items():
            print(key)
            prompt = Prompt.query.filter(Prompt.name==key).first()
            prompt.content = val
        db.session.commit()
        return ''

@admin.route('/lx2-chapter-prompt', methods=['GET','POST'])
def lx2ChapterPrompt():
    act = request.values.get("act","chapterReviewPrompt")
    prompt = Prompt.query.filter(Prompt.name == act).first()
    if act =="chapterReviewPrompt" or act =="sectionReviewPrompt":
        rules = ReviewRules.query.filter(ReviewRules.title_num!="").order_by(ReviewRules.title_num.asc()).all()
    else:
        rules = OutlineRules.query.filter(OutlineRules.title_num!="").order_by(OutlineRules.title_num.asc()).all()
    all_prompts = []
    for rule in rules:
        if act =="firstHeuristicWriting":
            rule.prompt = rule.heuristic_writing_prompt
        if act =="chapterReviewPrompt":
            if re.match(r'^\d+$',rule.title_num) is not None:
                all_prompts.append(rule)
        else:
            if re.match(r'^\d+$', rule.title_num) is  None:
                all_prompts.append(rule)
    return render_template('admin/prompt3-chapter.html', all_prompts=all_prompts,prompt=prompt,act=act)

@admin.route('/edit_special_prompt', methods=['GET','POST'])
def editPrompt():
    try:
        data = request.json
        if data['act'] == "chapterReviewPrompt" or data['act'] == "sectionReviewPrompt":
            rule = ReviewRules.query.filter(ReviewRules.title_num==data['title_num']).first()
            rule.prompt = data['prompt']
        else:
            rule = OutlineRules.query.filter(OutlineRules.title_num==data['title_num']).first()
            rule.heuristic_writing_prompt = data['prompt']
        db.session.commit()
        return jsonify({'msg': '添加成功', "code": 1}), 200
    except:
        return jsonify({'msg': '添加失败', "code": -1}), 200


@admin.route('/edit_public_prompt', methods=['GET','POST'])
def editPublicPrompt():
    try:
        data = request.json
        prompt = Prompt.query.filter(Prompt.name==data['act']).first()
        prompt.content = data['prompt']
        db.session.commit()
        return jsonify({'msg': '添加成功', "code": 1}), 200
    except:
        return jsonify({'msg': '添加失败', "code": -1}), 200


@admin.route('/cammands', methods=['GET','POST'])
def cammands():
    if request.method == "GET":
        items = cammand.adminGetAll()
        return render_template('admin/cammands.html',items=items)
    else:
        data = request.json
        cammand.editOne(data)
        return jsonify({'msg': '修改成功', "code": 1}), 200

@admin.route('/usersDocs')
def usersDocs():
    record_type = int(request.values.get('type', 0))
    search = request.values.get('search',"").strip()
    pagination,items = AiSugScore.get_user_ai_sug_score(record_type, search)
    for item in items:
        item[0].log_content = ""
        for l in item[0].anti_shake_logs:
            item[0].log_content = l.content
    return render_template('admin/usersDocs.html', items=items, pagination=pagination, search=search, type=record_type)

@admin.route('/lxDocs')
def lxDocs():
    act = request.values.get('act','list')
    if act == 'list':
        record_type = int(request.values.get('type', 2))
        user_name = request.values.get('user_name',"").strip()
        pagination,items = LxAiSugScore.getUserAiSugScore(user_name)
        case_text_list = DocFiles.getReportCaseArr()
        for item in items:
            item[0].log_content = ""
            for l in item[0].anti_shake_logs:
                item[0].log_content = l.content
        return render_template('admin/lxDocs.html', items=items, pagination=pagination, user_name=user_name, type=record_type, caseTextList=case_text_list)
    elif act == 'download':
        file_key = request.values.get('file_key')
        local_path = './tmp/'
        tmpFilePath,fileName = aliOss.downLoadOne(file_key,local_path)
        try:
            return send_file(
                tmpFilePath,
                mimetype='application/octet-stream',
                as_attachment=True,
                download_name=fileName,  # Flask 2.0+ 支持
                # 对于旧版 Flask，用 `attachment_filename`
                # attachment_filename=fileName,
            )
        finally:
            if os.path.exists(tmpFilePath):
                os.remove(tmpFilePath)


@admin.route('/profile', methods=['GET','POST'])
def profile():
    if request.method == "GET":
        item = AdminUser.getOne(session['fc_admin_user_id'])
        return render_template('admin/profile.html',item=item)
    else:
        data = request.json
        if data['password']!=data['confirm_password']:
            return jsonify({'msg': '两次密码输入必须一样', "code": -1}), 200
        password = data['password'].strip()
        if len(password)>0 and len(password)<6:
            return jsonify({'msg': '密码至少6位', "code": -1}), 200
        pattern = r'^1\d{10}$'
        mobile = data['mobile'].strip()
        if not re.match(pattern, data['mobile']):
            return jsonify({'msg': '请输入正确的手机号码', "code": -1}), 200
        AdminUser.updateProfile(password, mobile)
        return jsonify({'msg': '修改成功', "code": 1}), 200

@admin.route('/aiVal_batch_delete', methods=['GET','POST'])
def aiValBatchDelete():
    data = request.json
    for id in data['ids']:
        AiSugScore.adminDeleteAiSugScore(id)
    return jsonify({'msg': '批量删除成功', "code": 1}), 200


@admin.route('/lx_batch_delete', methods=['GET','POST'])
def lxBatchDelete():
    data = request.json
    for id in data['ids']:
        LxAiSugScore.adminDeleteAiSugScore(id)
    return jsonify({'msg': '批量删除成功', "code": 1}), 200

'''
移动用户就是管理员用户
'''
@admin.route('/mobile_users', methods=['GET','POST'])
def mobileUsers():
    act = request.values.get('act','list')
    if act == 'list':
        mobile = request.values.get('mobile','')
        mobile = mobile.strip()
        pagination,items = User.get_mobile_user_list(mobile)
        return render_template('admin/mobileUserList.html',
                                   items=items,
                                   pagination=pagination,
                                   mobile=mobile,
                                   allEmployeesNum=User.allEmployeesNum,
                                   allSense=User.allSense,
                                   allPosition=User.allPosition
                               )
    elif act=="add":
        data = request.json
        pattern = r'^1\d{10}$'
        if not re.match(pattern, data['mobile']):
            return jsonify({'msg': '请输入正确的手机号码', "code": -1}), 200
        if len(data['password'])<6:
            return jsonify({'msg': '密码至少6位', "code": -1}), 200
        if data['password'] != data['password2']:
            return jsonify({'msg': '两次输入密码不一致', "code": -1}), 200
        item = User.check_register_user(data)
        user_id = 0
        if item!=None:
            if item.status == 1:
                return jsonify({'msg': '你注册的手机号码已被注册', "code": -1}), 200
            else:
                user_id = item.user_id
        token = hashlib.md5((data['password'] + data['mobile'] + str(time.time())).encode(encoding='UTF-8')).hexdigest()
        data['token'] = token
        user_id = User.add_admin_mobile_user(data, user_id)
        MobileUserRight.add_one({"user_id":user_id, "type":0})
        MobileUserRight.add_one({"user_id":user_id, "type":1})
        MobileUserRight.add_one({"user_id":user_id, "type":2})
        return jsonify({"msg":"新增成功","code":1})

@admin.route('/mobile_user_edit', methods=['GET', 'POST'])
def mobile_user_edit():
    if request.method == "GET":
        user_id = request.values.get('user_id',0)
        user = User.get_user_by_id(user_id)
        items = MobileUserRight.get_rights(user_id)
        for item in items:
            field = 'type_'+str(item.type)
            item.emailUserNum = User.get_inner_user_num(user_id, field)
        return render_template('admin/mobileUserEdit.html',items=items,user=user)
    else:
        data = request.json
        MobileUserRight.set_rights(data)
        return jsonify({'msg': '修改成功', "code": 1}), 200
@admin.route('/del_mobile_users', methods=['GET','POST'])
def batchDeleteUser():
    data = request.json
    for id in data['ids']:
        User.delete_mobile_user(int(id))
        User.delete_inner_user(0, int(id))
    return jsonify({'msg': '批量删除成功', "code": 1}), 200
@admin.route('/del_one_user', methods=['GET','POST'])
def delOneUser():
    user_id = request.values.get('user_id',0)
    User.delete_mobile_user(int(user_id))
    User.delete_inner_user(0, int(user_id))
    return redirect("/admin/mobile_users")


'''
添加原本没有的模块的权限
'''
@admin.route('/add_right', methods=['GET','POST'])
def addRight():
    '''

    :return:
    '''
    records = User.get_all_mobile_user()
    for rec in records:
        if rec.status ==1:
            right = MobileUserRight.get_one_right(rec.user_id, 3)
            if right==None:
                MobileUserRight.add_one({"user_id": rec.user_id, "type": 3})

@admin.route('/export_ai_sug_score', methods=['GET', 'POST'])
def exportAiSugScore():
    type = int(request.values.get('type',0))
    date = request.values.get('date',"")
    if date!="":
        b_date =date.split('~')[0].strip()
        e_date =date.split('~')[1].strip()
    else:
        b_date = ""
        e_date = ""
    items = AiSugScore.getDateTypeExport(user_id=0, type=type, state=1, b_date=b_date, e_date=e_date, is_admin=1)
    data = {}
    if type== 1:
        data['ID'] = []
        data['需求描述'] = []
        data['需求描述AI建议'] = []
        data['需求描述得分（满分10）'] = []
        data['需求分析'] = []
        data['需求分析AI建议'] = []
        data['需求分析得分（满分10）'] = []
        data ['需求决策'] = []
        data['需求决策AI建议'] = []
        data['需求决策得分（满分10）'] = []
        data['验证结果'] = []
        data['验证结果AI建议'] = []
        data['验证结果AI得分（满分10）'] = []
        for item in items:
            data['ID'].append(item.id)
            data['需求描述'].append(item.step1)
            data['需求描述AI建议'].append(item.ai_step1)
            data['需求描述得分（满分10）'].append(item.step1_score)
            data['需求分析'].append(item.step2)
            data['需求分析AI建议'].append(item.ai_step2)
            data['需求分析得分（满分10）'].append(item.step2_score)
            data['需求决策'].append(item.step3)
            data['需求决策AI建议'].append(item.ai_step3)
            data['需求决策得分（满分10）'].append(item.step3_score)
            data['验证结果'].append(item.step4)
            data['验证结果AI建议'].append(item.ai_step4)
            data['验证结果AI得分（满分10）'].append(item.step4_score)
    if type == 0:
        data['ID'] = []
        data['产品缺陷描述'] = []
        data['产品缺陷描述AI建议'] = []
        data['产品缺陷描述得分（满分10）'] = []
        data['原因分析'] = []
        data['原因分析AI建议'] = []
        data['原因分析得分（满分10）'] = []
        data['解决措施实施'] = []
        data['解决措施实施AI建议'] = []
        data['解决措施实施得分（满分10）'] = []
        data['回归测试'] = []
        data['回归测试AI建议'] = []
        data['回归测试AI得分（满分10）'] = []
        for item in items:
            data['ID'].append(item.id)
            data['产品缺陷描述'].append(item.step1)
            data['产品缺陷描述AI建议'].append(item.ai_step1)
            data['产品缺陷描述得分（满分10）'].append(item.step1_score)
            data['原因分析'].append(item.step2)
            data['原因分析AI建议'].append(item.ai_step2)
            data['原因分析得分（满分10）'].append(item.step2_score)
            data['解决措施实施'].append(item.step3)
            data['解决措施实施AI建议'].append(item.ai_step3)
            data['解决措施实施得分（满分10）'].append(item.step3_score)
            data['回归测试'].append(item.step4)
            data['回归测试AI建议'].append(item.ai_step4)
            data['回归测试AI得分（满分10）'].append(item.step4_score)
    tmpDatePath = f'./tmp/export/{datetime.now().strftime("%Y%m%d")}/'
    tmpIdPath = tmpDatePath+f"_admin"
    if not os.path.exists(tmpDatePath):
        os.mkdir(tmpDatePath)
    if not os.path.exists(tmpIdPath):
        os.mkdir(tmpIdPath)
    df = pd.DataFrame(data)
    df_filled = df.astype(str).fillna('')
    df_filled.to_excel(f"{tmpIdPath}/export.xlsx", index=False)
    zip.zipDirectory(tmpIdPath,tmpDatePath+f'/admin_export.zip')
    subprocess.run(f'rm -Rf {tmpIdPath}/*',shell=True)
    def generate(file):
        with open(file, 'rb') as f:
            while True:
                chunk = f.read(4096)  # 每次读取 4KB
                if not chunk:
                    subprocess.run(f'rm -Rf {file}', shell=True)
                    break
                yield chunk
    return Response(generate(tmpDatePath+f'admin_export.zip'), mimetype='application/octet-stream',headers={'Content-Disposition': f'attachment;filename=admin_export.zip'})
@admin.route('/admin_user', methods=['GET', 'POST'])
def adUsers():
    act = request.values.get('act','list')
    if act=='list':
        search = request.values.get('search','').strip()
        pagination,items =AdminUser.getUserList(search)
        allRights = AdminRights.getAllRight()
        menuRights = AdminRights.getMenu()
        return render_template('admin/adminUserList.html',items=items,pagination=pagination,allRights=allRights,search=search,menuRights=menuRights)
    elif act=="add":
        data = request.json
        if data['user_name'] == "":
            return jsonify({"msg":"用户名不可以为空","code":-1})
        if data['password']=="":
            return jsonify({"msg": "密码不可以为空", "code": -1})
        if data['password']!=data['password2']:
            return jsonify({"msg":"两个密码必须一样","code":-1})
        if AdminUser.checkUser(data)==False:
            return jsonify({"msg":"用户名已存在","code":-1})
        rights = data['right_ids']
        rightStr = ','.join(rights)
        data['rights'] = rightStr
        AdminUser.addOne(data)
        return jsonify({"msg": "新增成功", "code": 1})
    elif act=="edit":
        data = request.json
        if data['user_name'] == "":
            return jsonify({"msg":"用户名不可以为空","code":-1})
        if data['password']!=data['password2']:
            return jsonify({"msg":"两个密码必须一样","code":-1})
        if AdminUser.checkUser(data, data['user_id'])==False:
            return jsonify({"msg":"用户名已存在","code":-1})
        rights = data['right_ids']
        rightStr = ','.join(rights)
        data['rights'] = rightStr
        AdminUser.editAdminUser(data)
        return jsonify({"msg": "新增成功", "code": 1})
    elif act=="delete":
        userId = request.values.get('user_id',0)
        AdminUser.delAdminUser(userId)
        return redirect("/admin/admin_user")

@admin.route('/report')
def report():
    id = request.values.get('id',0)
    data, fish_score1, fish_score2, fish_score3, caseText, reportTitles,item = LxAiValSrvice.get_report(id, user_id=0, state=1, is_admin=True)
    return render_template('user/lxAiVal/report.html', xmind=json.dumps(data,ensure_ascii=False), item = item, select_1=LxAiSugScore.select_1_text[int(item.select_1)], select_2=LxAiSugScore.select_2_text[int(item.select_2)], case_text=caseText, fish_score1=fish_score1, fish_score2=fish_score2, fish_score3=fish_score3, report_titles=reportTitles, fromAdmin=1)

@admin.route('/defect_list')
def defect_list():
    page = int(request.values.get('page',1))
    per_page = 50
    search = request.values.get('search',"")
    query = Defect.query
    if search!="":
        query = query.filter(or_(Defect.defect_number==search,Defect.title.like(f'%{search}%')))
    query = query.join(Defect.current_stage).join(DefectStage.assignee).order_by(Defect.updated_time.desc())
    total = query.count()
    defects = query.paginate(page=page, per_page=per_page, error_out=False)
    # sql = query.statement.compile(compile_kwargs={"literal_binds": True})
    # current_app.logger.info(f"最终SQL查询: {sql}")
    version_ids = []
    project_ids = []
    for defect in defects.items:
        if defect.current_stage.stage_type_ref:
            defect.stage_name = defect.current_stage.stage_type_ref.stage_name
        else:
            defect.stage_name = None

        defect.status_name = STATUS_MAPPING.get(defect.status, '未知')

        if defect.version_id is not None:
            version_ids.append(defect.version_id)
        else:
            project_ids.append(defect.project_id)

    project_line = {}
    tech_group = {}
    if version_ids:
        project_line, _ = ProductLineService.get_versions_by_ids(version_ids)
    if project_ids:
        tech_group, _ = TechGroupService.get_projects_by_ids(project_ids)

    for defect in defects.items:
        if defect.version_id is not None:
            defect.product_or_version = project_line.get(defect.version_id)
        else:
            defect.product_or_version = tech_group.get(defect.project_id)
        current_date = datetime.now()
        # 计算天数差（向上取整）
        defect.days_passed = (current_date - defect.created_time).days + 1
    pagination = Pagination(
        page=page,
        per_page=per_page,
        total=total,
        css_framework='bootstrap5',  # 支持 bootstrap4/bootstrap5/foundation 等
        alignment='right',  # 分页居中
        prev_label='<',  # 自定义上一页文本
        next_label='>',  # 自定义下一页文本
    )
    return render_template("admin/defectList.html",defects=defects,pagination=pagination,search=search)

@admin.route('/defect_detail')
def defect_detail():
    defect_id = request.values.get('defect_id',0)
    defect = DefectService.get_defect_by_id(defect_id)
    project_version_name, project_version_id = defect_services.get_project_version(defect)
    stages = DefectStageService.get_stages_by_defect(defect_id)
    current_stage = DefectStageService.get_stage_by_id(defect.current_stage_id)
    current_stage_name = DefectWorkflowService.get_current_stage_name(defect)

    stage_data = None  # 当前阶段数据
    if current_stage:
        current_app.logger.info(f'current_stage id: {current_stage.id}')
        stage_data_list = DefectStageDataService.get_all_stage_data_by_criteria(current_stage.id, None, True, None)
        stage_data = stage_data_list[0] if len(stage_data_list) > 0 else None
        if stage_data:
            current_app.logger.debug(f'stage_data.id: {stage_data.id}')
    source_defect = None
    if defect.duplicate_source_id:
        source_defect = DefectService.get_defect_by_id(defect.duplicate_source_id)
    defect_description_list = []
    description_data = DefectStageDataService.get_defect_description_data(defect_id)
    if description_data:
        content_dict = description_data[0].get('content')
        try:
            defect_description_list = json.loads(content_dict.get('description'))
            if defect_description_list:
                current_app.logger.info(
                    f"defect_description_list[0].get('title') : {defect_description_list[0].get('title')}")
                current_app.logger.info(
                    f'current_stage status: {current_stage.status}  description_data status: {description_data[0].get("stage_status")}')
        except Exception as e:
            current_app.logger.error(f'1、description_data 数据格式不符合要求: {e}')
    cause_analysis_data = DefectStageDataService.get_locale_invitation_data(defect_id)
    analysis_data_list = []
    completed_analysis_data = DefectStageDataService.filter_completed_invitations(cause_analysis_data)
    current_app.logger.debug(f'len(completed_analysis_data): {len(completed_analysis_data)}')
    for data in completed_analysis_data:
        for item in data.get('content').get('analyses'):
            analysis_data_list.append(item)
    cause_analysis_ai = None
    if cause_analysis_data:
        defect_stage_id = cause_analysis_data[0]['defect_stage_id']
        cause_analysis_ai = DefectStageCombineRecord.query.filter(
            DefectStageCombineRecord.defect_stage_id == defect_stage_id).first()

    solution_data_list = []
    solution_data = DefectStageDataService.get_solution_division_data(defect_id)
    completed_solution_data = DefectStageDataService.filter_completed_divisions(solution_data)
    solution_ai = None
    solution_data = DefectStageDataService.get_solution_division_data(defect_id)
    if solution_data:
        defect_stage_id = solution_data[0]['defect_stage_id']
        solution_ai = DefectStageCombineRecord.query.filter(
            DefectStageCombineRecord.defect_stage_id == defect_stage_id).first()
    for data in completed_solution_data:
        for item in data.get('content').get('solutions'):
            solution_data_list.append(item)
    test_result_data = DefectStageDataService.get_test_result_data(defect_id)
    test_result_data_list = []
    if test_result_data:
        content_dict = test_result_data[0].get('content')
        try:
            test_result_data_list = json.loads(content_dict.get('description'))
            if test_result_data_list:
                current_app.logger.info( f"test_result_data_list[0].get('title') : {test_result_data_list[0].get('title')}")
                current_app.logger.info(
                    f'current_stage status: {current_stage.status}  test_result_data status: {test_result_data[0].get("stage_status")}')
        except Exception as e:
            current_app.logger.error(f'test_result_data 数据格式不符合要求: {e}')
    defect_flow_histories = DefectFlowHistoryService.get_flow_history(defect_id)
    return render_template("admin/defectDetail.html",
                           defect=defect,
                           project_version_name=project_version_name,
                           stages=stages,
                           stage_data=stage_data,
                           current_stage_name=current_stage_name,
                           current_stage = current_stage,
                           source_defect = source_defect,
                           defect_description_list = defect_description_list,
                           description_data = description_data,
                           analysis_data_list = analysis_data_list,
                           solution_data_list = solution_data_list,
                           solution_data = solution_data,
                           test_result_data_list = test_result_data_list,
                           test_result_data = test_result_data,
                           cause_analysis_ai = cause_analysis_ai,
                           solution_ai = solution_ai,
                           defect_flow_histories = defect_flow_histories,
                           is_admin = 1
                           )
@admin.route('/get_check_logs')
def get_order_logs():
    log_path = "./logs/admin_view.log"
    with open(log_path, "r", encoding="utf-8") as log:
        lines = log.readlines()
        md_content = ''.join(lines[-500:])  # 核心：[-500:]截取尾部500行
    return f"<pre>{md_content}</pre>"
