import shutil

from flask import Blueprint, render_template, request, redirect, jsonify, session, g, send_from_directory, \
    after_this_request, Response, current_app,send_file
from conf.config import app_config
from models.ai_sug_score.model import AiSugScore
from models.users.models import MobileUserRight
from models.valAiaq import valAiaq
import pandas as pd
from common.Ai import Ai
from datetime import datetime
import os
from common.aliOss import aliOss
import threading
from models.upload_files.model import UploadFiles
from common.zip import zip
import subprocess
from services.ai_val_service import AiValSrvice
import sys

from services.user_image_service import UserImageService

aiVal = Blueprint('aiVal', __name__)
lxStepScoreLock = threading.RLock()
stepScoresThread = {}
@aiVal.before_request
def before_request():
    if 'user_id' not in session:
        if request.method == "GET":
            js_code = """
            <script type="text/javascript">
                    alert('请重新登录！');
                    location.href="/"
            </script>
            """
            return js_code
        else:
            return jsonify({'msg': '请先登录', "code": 1}), 200
    if g.user_type != 'mobile':
        if MobileUserRight.get_user_type_right(g.user_type, g.user_id, g.admin_user_id, g.type) == 0:
                js_code = """
                <script type="text/javascript">
                        alert('你没有权限');
                        location.href="/user/index"
                </script>
                """
                return js_code
    return None


@aiVal.route('/list')
def lists():
    user_id = g.user_id
    state = request.values.get('state','')
    search = request.values.get('search','')
    record_id = request.values.get('record_id','')
    pagination,items = AiSugScore.get_list(user_id, g.type, state, search,record_id)
    ai_score_ids = []
    for item in items:
        ai_score_ids.append("'"+item.id+"'")
    aiScoreIdStr = ",".join(ai_score_ids)
    result = valAiaq.getListByIdStr(aiScoreIdStr)
    for item in items:
        item.aqs = []
        for rs in result:
            if rs[0] == item.id:
                item.aqs.append([rs[1],rs[2]])
    #dateEnd, request_font_red, invite_font_red, Rights = MobileUserRight.get_right_style(g.admin_user_id, g.type)
    return render_template('user/aiVal/list.html', items=items, type=g.type, pagination=pagination, pageShow=AiSugScore.pageShowConfig[g.type],user_type=g.user_type, uploadFiles=AiSugScore.uploadFiles[int(g.type)],  state=state, search=search,record_id=record_id)
@aiVal.route('/edit', methods=['GET','POST'])
def edit():
    id = request.values.get('id')
    if request.method == "GET":
        item = AiSugScore.get_one(g.user_id, id)
        act = request.values.get('act',"")
        return render_template('user/aiVal/edit.html', item=item, pageShow=AiSugScore.pageShowConfig[g.type], type=g.type, act=act)
    else:
        data = request.json
        data['user_id'] = g.user_id
        AiSugScore.editOne(data)
        return jsonify({'msg': '编辑成功',"code":1}),200
@aiVal.route('/add', methods=['GET','POST'])
def add():
    if request.method == "GET":
        return render_template('user/aiVal/add.html', type=g.type, pageShow=AiSugScore.pageShowConfig[g.type])
    else:
        data = request.json
        id = datetime.now().strftime("%Y%m%d%H%M%S%f")
        data["id"] = str(g.user_id)+id
        data['user_id'] = g.user_id
        data['admin_user_id'] = g.admin_user_id
        data['type'] = g.type
        AiSugScore.add_one(data)
        return jsonify({'msg': 'Data received successfully',"code":1,"id":data["id"]}),200
@aiVal.route('/delete', methods=['GET', 'POST'])
def delete():
    id = request.values.get('id')
    AiSugScore.deleteUserAiSugScore(id, g.user_id)
    return redirect(f"/user/aiVal/list?type={g.type}")

@aiVal.route('/batch_delete', methods=['GET', 'POST'])
def batchDelete():
    data = request.json
    for id in data['ids']:
        print("id_arr:"+id)
        AiSugScore.deleteUserAiSugScore(id, g.user_id)
    return jsonify({'msg': '批量删除成功', "code": 1}), 200

@aiVal.route('/done', methods=['POST'])
def done():
    data = request.json
    data['user_id'] = g.user_id
    item = AiSugScore.get_one(g.user_id, data['id'])
    if item.state>0:
        return jsonify({'msg': '已经评估过的不可以再评估', "code": -1}), 200
    data['step1'],url1,error1,_ = aliOss.dealImgSrc(item.step1, g.user_id)
    data['step2'],url2,error2,_ = aliOss.dealImgSrc(item.step2, g.user_id)
    data['step3'],url3,error3,_ = aliOss.dealImgSrc(item.step3, g.user_id)
    data['step4'],url4,error4,_ = aliOss.dealImgSrc(item.step4, g.user_id)
    if (error1+error2+error3+error4)>0:
        AiSugScore.edit_ai_save_state(data)
        return jsonify({'msg': '数据录入超时', "code": -1}),200
    urls = url1 + url2 + url3 + url4
    if len(urls) > 0:
        UploadFiles.bulkInsert(urls, data['id'], g.user_id)
    mobile_user_right_record = MobileUserRight.get_one_right(g.admin_user_id, g.type)
    rs,code = mobile_user_right_record.check_request_right(mobile_user_right_record)
    if code<0:
        AiSugScore.edit_ai_save_state(data)
        return jsonify(rs),200
    MobileUserRight.set_right(mobile_user_right_record, 'requested_num', (mobile_user_right_record.requested_num + 1))
    MobileUserRight.ai_val_sms(mobile_user_right_record, g.admin_user_id, item.type)
    try:
        data = AiValSrvice.get_score_suggestion(g.type, data)
        AiSugScore.edit_ai(data)
    except Exception as e:
        current_app.logger.error(f"评估失败异常-done：{e},文件：{e.__traceback__.tb_frame.f_globals['__file__']};行数：{e.__traceback__.tb_lineno}")
        MobileUserRight.set_right(mobile_user_right_record, 'requested_num', (mobile_user_right_record.requested_num - 1))
        return jsonify({'msg': "AI评估失败", "code": -1}), 200
    return jsonify({'msg': '评估成功', "code": 1}), 200

@aiVal.route('/question', methods=['GET','POST'])
def question():
    id = request.values.get('id')
    item = AiSugScore.get_one(g.user_id, id)
    if request.method == "GET":
        aqs = valAiaq.getList(g.user_id,id)
        if item.state<=0:
            js_code = """
            <script type="text/javascript">
                    alert('记录状态错误');
                    location.href="/user/login"
            </script>
            """
            return js_code
        else:
            return render_template('user/aiVal/result.html', item=item, aqs=aqs, pageShow = AiSugScore.pageShowConfig[g.type], type=g.type)
    else:
        mobileUserRightRecord = MobileUserRight.get_one_right(g.admin_user_id, g.type)
        rs, code = mobileUserRightRecord.check_request_right(mobileUserRightRecord)
        if code < 0:
            return jsonify(rs), 200
        data = request.json
        data['user_id'] = g.user_id
        data['ai_score_id'] = id
        data['admin_user_id'] = g.admin_user_id
        data['type'] = g.type
        data['answer'] = ""
        dbId = valAiaq.addOne(data)
        markdown_table = AiSugScore.getMarkDownData(item)
        data['answer'] = Ai.askScoreSuggestionTable(markdown_table,data['question'],str(item.type))
        valAiaq.setAnswer(data['answer'], dbId)
        MobileUserRight.set_right(mobileUserRightRecord, 'requested_num', (mobileUserRightRecord.requested_num + 1))
        MobileUserRight.ai_val_sms(mobileUserRightRecord, g.admin_user_id, item.type)
        return jsonify({'msg': '回复成功', "code": 1,"answer":data['answer']}), 200

@aiVal.route('/batch_add', methods=['POST'])
def batchAdd():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    if file:
        # 保存文件到服务器（例如在当前目录下的uploads文件夹）
        extension = os.path.splitext( file.filename)[-1]
        tmpIdPath = f'./tmp/upload/{g.user_id}/'
        if not os.path.exists(tmpIdPath):
            os.mkdir(tmpIdPath)
        file.save(f'{tmpIdPath}{file.filename}')
        @after_this_request
        def after_request_callback(response):
            if  hasattr(g, 'current_threads'):
                thread = threading.Thread(target=waitThreadEnd, args=(g.current_threads,))
                thread.start()
            return response
        def waitThreadEnd(current_threads):
            for thread in current_threads:
                thread.join()
                del thread
            subprocess.run(f'rm -Rf {tmpIdPath}', shell=True)
        if extension==".xlsx" or extension==".xls":
            return batchExecNoPic(file)
        elif extension==".zip":
            return batchExecWithPic(file,tmpIdPath)


def batchExecWithPic(file,tmpIdPath):
    zip.extractWithEncoding(f'{tmpIdPath}/{file.filename}',tmpIdPath)
    excelFileWin = f"{tmpIdPath}/{AiSugScore.uploadFiles[int(g.type)][0]}"
    #苹果生成的zip文件与win的不同
    excelFileIos = f"{tmpIdPath}/{os.path.splitext(AiSugScore.uploadFiles[int(g.type)][0])[0]}/{AiSugScore.uploadFiles[int(g.type)][0]}"
    excelFile = ""
    if os.path.exists(excelFileWin) :
        excelFile = excelFileWin
    if os.path.exists(excelFileIos):
        excelFile = excelFileIos
        tmpIdPath = f"{tmpIdPath}/{os.path.splitext(AiSugScore.uploadFiles[int(g.type)][0])[0]}"
    if excelFile=='':
        return jsonify({'msg': 'excel文件路径错误，请严格按照导入说明文档的规则上传打包文件', 'filename': "", 'code': -1}), 200
    rs,code,errorTag = excelCheck(excelFile)
    if code ==200:
        return rs,code
    datas = rs
    mobileUserRightRecord = MobileUserRight.get_one_right(g.admin_user_id, g.type)
    rs, code = mobileUserRightRecord.check_request_right(mobileUserRightRecord)
    if code < 0:
        return jsonify(rs), 200
    if (mobileUserRightRecord.request_num - (mobileUserRightRecord.requested_num + len(datas))) < 0:
        return jsonify({'msg': f'EXCEL文件中要提问的记录数量为{len(datas)}条，剩余提问次数的为{(mobileUserRightRecord.request_num - mobileUserRightRecord.requested_num)}次,剩余提问次数不足',"code": -2}), 200
    for data in rs:
        src1 = aliOss.imgFileCheck(data['step1'], tmpIdPath)
        src2 = aliOss.imgFileCheck(data['step2'], tmpIdPath)
        src3 = aliOss.imgFileCheck(data['step3'], tmpIdPath)
        src4 = aliOss.imgFileCheck(data['step4'], tmpIdPath)
        srcAll = src1+src2+src3+src4
        if len(srcAll)>0:
            errorTag = 1
    mobileUserRightRecord = MobileUserRight.get_one_right(g.admin_user_id, g.type)
    MobileUserRight.set_right(mobileUserRightRecord, 'requested_num', (mobileUserRightRecord.requested_num + len(datas)))
    datasArr = splitThreadData(datas)
    g.current_threads = []
    for datas in datasArr:
        thread = threading.Thread(target=threadZipBatchValDone, args=(datas,tmpIdPath))
        g.current_threads.append(thread)
        thread.start()
    return jsonify({'msg': '批量入库成功，AI评估中....', 'filename': "", 'code': 1,'errorTag':errorTag}), 200

def excelCheck(filePath):
    df = pd.read_excel(filePath)
    df = df.astype(str).fillna('')
    datas = []
    id = int(datetime.now().strftime("%Y%m%d%H%M%S%f"))
    errorTag = 0
    if g.type == 0:
        if '产品缺陷描述' not in df or '原因分析' not in df or '解决措施实施' not in df or '回归测试' not in df:
            return jsonify({'msg': '请下载标准模板', "code": -1}), 200,1
        length = len(df['产品缺陷描述'])
        for i in range(0, length):
            data = {}
            data['step1'] = str(df['产品缺陷描述'][i])
            data['step2'] = str(df['原因分析'][i])
            data['step3'] = str(df['解决措施实施'][i])
            data['step4'] = str(df['回归测试'][i])
            if data['step1'] == "" and data['step2'] == "" and data['step3'] == "" and data['step4'] == "":
                errorTag = 1
            #     return jsonify({'msg': 'excel模板文件中：产品缺陷描述，原因分析，解决措施实施，验证结果对应的数据都不可以为空',"code": -1}), 200
            data['type'] = int(g.type)
            data['user_id'] = g.user_id
            data["id"] = str(g.user_id)+str(id + i)
            data["state"] = -1
            data['admin_user_id'] = g.admin_user_id
            datas.append(data)
    if g.type == 1:
        if '需求描述' not in df or '需求分析' not in df or '需求决策' not in df or '验证结果' not in df:
            return jsonify({'msg': '请下载标准模板', "code": -1}), 200,1
        length = len(df['需求描述'])
        for i in range(0, length):
            data = {}
            data['step1'] = str(df['需求描述'][i])
            data['step2'] = str(df['需求分析'][i])
            data['step3'] = str(df['需求决策'][i])
            data['step4'] = str(df['验证结果'][i])
            if data['step1'] == "" and data['step2'] == "" and data['step3'] == "" and data['step4'] == "":
                errorTag = 1
            data['type'] = int(g.type)
            data['user_id'] = g.user_id
            data["id"] = str(g.user_id)+str(id + i)
            data["state"] = -1
            data['admin_user_id'] = g.admin_user_id
            datas.append(data)
    return datas,0,errorTag
def batchExecNoPic(file):
    rs, code,errorTag = excelCheck(file)
    if code == 200:
        return rs,code
    datas = rs
    mobileUserRightRecord = MobileUserRight.get_one_right(g.admin_user_id, g.type)
    rs, code = mobileUserRightRecord.check_request_right(mobileUserRightRecord)
    if code < 0:
        return jsonify(rs), 200
    if (mobileUserRightRecord.request_num - (mobileUserRightRecord.requested_num + len(datas))) < 0:
        return jsonify({'msg': f'EXCEL文件中要提问的记录数量为{len(datas)}条，剩余提问次数的为{(mobileUserRightRecord.request_num - mobileUserRightRecord.requested_num)}次,剩余提问次数不足',"code": -2}), 200
    MobileUserRight.set_right(mobileUserRightRecord, 'requested_num', (mobileUserRightRecord.requested_num + len(datas)))
    file.close()
    datasArr = splitThreadData(datas)
    g.current_threads = []
    lenNum = 0
    for datas in datasArr:
        lenNum = lenNum + len(datas)
        thread = threading.Thread(target=threadBatchValDone, args=(datas,))
        g.current_threads.append(thread)
        thread.start()
    return jsonify({'msg': '批量入库成功，AI评估中....', 'filename': file.filename, 'code': 1,'errorTag':errorTag}), 200

@aiVal.route('/download/<filename>',methods=['GET'])
def download(filename):
    response = send_from_directory('./static/download', filename)
    response.headers['Content-Disposition'] = 'attachment; filename={}'.format(filename)
    return response

@aiVal.route('/upload_pic',methods=['POST'])
def uploadPic():
    file = request.files['file']
    if file:
        filename = file.filename
        extension = os.path.splitext(filename)[-1]
        tmpFileName = datetime.now().strftime("%Y%m%d%H%M%S%f")+str(g.user_id)+extension
        file.save(f'./tmp/upload/{tmpFileName}')
        aliOss.uploadFile(f'./tmp/upload/{tmpFileName}')
        return jsonify({'msg':"上传成功",'url':f"https://{app_config['ali_bucket']}.{app_config['ali_endpoint']}/{tmpFileName}","code":1}), 200


@aiVal.route('/create_evaluate_image', methods=['POST'])
def create_evaluate_image():
    try:
        data = request.get_json()
        # 参数验证
        if not data:
            return jsonify({'success': False, 'message': '请求体不能为空'}), 400
        image_url = data.get('url')

        if not image_url:
            return jsonify({
                'success': False,
                'message': '缺少图片URL参数'
            }), 400
        user_id = g.user_id
        user_image = UserImageService.create_user_image(
            user_id=user_id,
            url=image_url,
        )
        return jsonify({
            'success': True,
            'id': user_image.id,
            'message': '图片信息保存成功'
        }), 200

    except Exception as e:
        current_app.logger.error(f"创建用户图片记录失败: {str(e)}")
        return jsonify({
            'success': False,
            'message': '图片信息保存失败'
        }), 500

@aiVal.route('/export',methods=['GET'])
def export():
    #items = aiSugScore.getAllExport(g.user_id, g.type)
    date = request.values.get('date',"")
    if date!="":
        b_date =date.split('~')[0].strip()
        e_date =date.split('~')[1].strip()
    else:
        b_date = ""
        e_date = ""
    items = AiSugScore.getDateTypeExport(user_id=g.user_id, type=g.type, state=1, b_date=b_date, e_date=e_date, is_admin=0)
    id_list = [item.id for item in items]
    pics = UploadFiles.getUserAllPic(id_list)
    tmp_date_path = f'./tmp/export/{datetime.now().strftime("%Y%m%d")}/'
    tmp_id_path = tmp_date_path+f"{g.user_id}"
    if not os.path.exists(tmp_date_path):
        os.mkdir(tmp_date_path)
    if not os.path.exists(tmp_id_path):
        os.mkdir(tmp_id_path)
    pic_dicts = aliOss.batch_download_images_from_oss(pics,tmp_id_path)
    id_list = []
    data = {}
    if g.type== 1:
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
        i = 1
        for item in items:
            id_list.append(item.id)
            data['ID'].append(item.id)
            data['需求描述'].append(aliOss.extract_export_data_images(item.step1,pic_dicts))
            data['需求描述AI建议'].append(item.ai_step1)
            data['需求描述得分（满分10）'].append(item.step1_score)
            data['需求分析'].append(aliOss.extract_export_data_images(item.step2,pic_dicts))
            data['需求分析AI建议'].append(item.ai_step2)
            data['需求分析得分（满分10）'].append(item.step2_score)
            data['需求决策'].append(aliOss.extract_export_data_images(item.step3,pic_dicts))
            data['需求决策AI建议'].append(item.ai_step3)
            data['需求决策得分（满分10）'].append(item.step3_score)
            data['验证结果'].append(aliOss.extract_export_data_images(item.step4,pic_dicts))
            data['验证结果AI建议'].append(item.ai_step4)
            data['验证结果AI得分（满分10）'].append(item.step4_score)
            i = i+1
    if g.type == 0:
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
        i = 1
        for item in items:
            id_list.append(item.id)
            data['ID'].append(item.id)
            data['产品缺陷描述'].append(aliOss.extract_export_data_images(item.step1,pic_dicts))
            data['产品缺陷描述AI建议'].append(item.ai_step1)
            data['产品缺陷描述得分（满分10）'].append(item.step1_score)
            data['原因分析'].append(aliOss.extract_export_data_images(item.step2,pic_dicts))
            data['原因分析AI建议'].append(item.ai_step2)
            data['原因分析得分（满分10）'].append(item.step2_score)
            data['解决措施实施'].append(aliOss.extract_export_data_images(item.step3,pic_dicts))
            data['解决措施实施AI建议'].append(item.ai_step3)
            data['解决措施实施得分（满分10）'].append(item.step3_score)
            data['回归测试'].append(aliOss.extract_export_data_images(item.step4,pic_dicts))
            data['回归测试AI建议'].append(item.ai_step4)
            data['回归测试AI得分（满分10）'].append(item.step4_score)
            i = i+1
    df = pd.DataFrame(data)
    df_filled = df.astype(str).fillna('')
    df_filled.to_excel(f"{tmp_id_path}/export.xlsx", index=False)
    zip.zipDirectory(tmp_id_path,tmp_date_path+f'/{g.user_id}_export.zip')
    shutil.rmtree(tmp_id_path)
    try:
        return send_file(
            tmp_date_path+f'/{g.user_id}_export.zip',
            mimetype='application/octet-stream',
            as_attachment=True,
            download_name=tmp_date_path+f'/{g.user_id}_export.zip',  # Flask 2.0+ 支持
            # 对于旧版 Flask，用 `attachment_filename`
            # attachment_filename=fileName,
        )
    finally:
        if os.path.exists(tmp_date_path+f'/{g.user_id}_export.zip'):
            os.remove(tmp_date_path+f'/{g.user_id}_export.zip')

    # try:
    #     return send_file(
    #         tmpFilePath,
    #         mimetype='application/octet-stream',
    #         as_attachment=True,
    #         download_name=fileName,  # Flask 2.0+ 支持
    #         # 对于旧版 Flask，用 `attachment_filename`
    #         # attachment_filename=fileName,
    #     )
    #
    def generate(file):
        with open(file, 'rb') as f:
            while True:
                chunk = f.read(4096)  # 每次读取 4KB
                if not chunk:
                    subprocess.run(f'rm -Rf {file}', shell=True)
                    break
                yield chunk
    return Response(generate(tmp_date_path+f'/{g.user_id}_export.zip'), mimetype='application/octet-stream',headers={'Content-Disposition': f'attachment;filename={g.user_id}_export.zip'})
def threadBatchValDone(datas):
    from app import app
    with app.app_context():
        admin_user_id = 0
        type = 0
        errorIds = []
        for d in datas:
            admin_user_id = d['admin_user_id']
            type = d['type']
            d['step1'], url1,error1,_ = aliOss.dealImgSrc(d['step1'], d['user_id'])
            d['step2'], url2,error2,_ = aliOss.dealImgSrc(d['step2'], d['user_id'])
            d['step3'], url3,error3,_ = aliOss.dealImgSrc(d['step3'], d['user_id'])
            d['step4'], url4,error4,_ = aliOss.dealImgSrc(d['step4'], d['user_id'])
            AiSugScore.add_one(d)
            if (error1 + error2 + error3 + error4) > 0:
                errorIds.append(d["id"])
                continue
            urls = url1 + url2 + url3 + url4
            if len(urls)>0:
                UploadFiles.bulkInsert(urls, d["id"], d['user_id'])
        mobileUserRightRecord = MobileUserRight.get_one_right(admin_user_id, type)
        for d in datas:
            try:
                rs = AiValSrvice.get_score_suggestion(d['type'], d)
                AiSugScore.edit_ai(rs)
            except:
                MobileUserRight.set_right(mobileUserRightRecord, 'requested_num', (mobileUserRightRecord.requested_num - 1))
        MobileUserRight.ai_val_sms(mobileUserRightRecord, admin_user_id, type)
def threadZipBatchValDone(datas,tmpIdPath):
    from app import app
    with app.app_context():
        admin_user_id = 0
        type = 0
        for d in datas:
            admin_user_id = d['admin_user_id']
            type = d['type']
            #tmpIdPath = f"./tmp/upload/{d['user_id']}"
            d['step1'], url1,cod1 = aliOss.extract_local_images(d['step1'], d['user_id'],tmpIdPath)
            d['step2'], url2,cod2 = aliOss.extract_local_images(d['step2'], d['user_id'],tmpIdPath)
            d['step3'], url3,cod3 = aliOss.extract_local_images(d['step3'], d['user_id'],tmpIdPath)
            d['step4'], url4,cod4 = aliOss.extract_local_images(d['step4'], d['user_id'],tmpIdPath)
            AiSugScore.add_one(d)
            if (cod1+cod2+cod3+cod4)!=4:
                print("有文件上传失败")
            urls = url1 + url2 + url3 + url4
            if len(urls)>0:
                UploadFiles.bulkInsert(urls, d["id"], d['user_id'])
        mobileUserRightRecord = MobileUserRight.get_one_right(admin_user_id, type)
        for d in datas:
            try:
                rs = AiValSrvice.get_score_suggestion(d['type'], d)
                AiSugScore.edit_ai(rs)
            except Exception as e:
                MobileUserRight.set_right(mobileUserRightRecord, 'requested_num', (mobileUserRightRecord.requested_num - 1))
                print("Ai评估失败")
        # mobileUserRightRecord = mobileUserRight.getOneRight(admin_user_id, type)
        # aiSugScoreNum = aiSugScore.getAdminUserRecordNum(admin_user_id,type,mobileUserRightRecord.admin_last_update)
        # aqNum = valAiaq.getAdminRecordNum(admin_user_id,type,mobileUserRightRecord.admin_last_update)
        # mobileUserRight.setRght(mobileUserRightRecord, 'requested_num', aqNum+aiSugScoreNum)
        MobileUserRight.ai_val_sms(mobileUserRightRecord, admin_user_id, type)
        #subprocess.run(f'rm -Rf {tmpIdPath}', shell=True)
def splitThreadData(datas):
    thred_num = 30
    #每个线程几条数据
    long = len(datas)
    quotient, remainder = divmod(long, thred_num)
    d = []
    d2 = []
    for i in range(0,thred_num):
        if remainder>0:
            end = quotient+1
            remainder = remainder-1
        else:
            end = quotient
        d = datas[0:end]
        d2.append(d)
        datas = datas[end:]
        if len(datas)==0:
            break
    return d2
