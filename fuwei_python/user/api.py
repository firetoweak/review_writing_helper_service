import time
from flask import Blueprint, request, jsonify, session, g
from models.ai_sug_score.model import AiSugScore  as aiSugScore
from models.valAiaq import valAiaq
from datetime import datetime
from models.users.models import User, MobileUserRight
import threading
from common.Ai import Ai
from common.aliOss import aliOss
from models.upload_files.model import UploadFiles
import os
from models.lx_ai_sug_score.model import LxAiSugScore
from common.aliDocAnalysis import aliDocAnalysis
from services.ai_val_service import AiValSrvice
from user.lxAiVal import ai_done_thread

api = Blueprint('api', __name__)
@api.before_request
def before_request():
    try:
        if request.path not in ["/user/api/get_token"]:
            if request.path =="/user/api/lx_upload_doc_deal":
                data = request.form
            else:
                data = request.json
            item = User.get_user_by_token(data['token'])
            if item is None or data['token']== "":
                return jsonify({'msg': 'token过期或错误，请重新生成', "code": -1, 'items': []}), 200
            else:
                g.user_id = item.user_id
                g.admin_user_id = item.user_id
        else:
            if 'user_id' not  in session:
                js_code = """
                <script type="text/javascript">
                        alert('请重新登录2');
                        location.href="/"
                </script>
                """
                return js_code
    except Exception as e:
        print(e)
        return jsonify({'msg': '请求参数有误', "code": -1, 'items': []}), 200

@api.route('/ai_val', methods=['POST'])
def ai_val():
    data = request.json
    steps = data['items']
    service_type = data['service_type']
    asy = data['async']
    record_id = datetime.now().strftime("%Y%m%d%H%M%S%f")
    mobile_user_right_record = MobileUserRight.get_one_right(g.admin_user_id, service_type)
    rs,code = mobile_user_right_record.check_request_right(mobile_user_right_record)
    if code<0:
        return jsonify(rs),200
    MobileUserRight.set_right(mobile_user_right_record, 'requested_num', (mobile_user_right_record.requested_num + 1))
    MobileUserRight.ai_val_sms(mobile_user_right_record, g.admin_user_id, service_type)
    try:
        data["id"] = record_id + str(g.user_id)
        if 'email_user_id' in data and "defect_id" in data:
            data['user_id'] = data['email_user_id']
        else:
            data['user_id'] = g.user_id
            data['process_id'] = None
            data['from_type'] = ""
        data['type'] = service_type
        data['step1'],url1,error1,error_img1 = aliOss.dealImgSrc(steps[0],g.user_id)
        data['step2'],url2,error2,error_img2 = aliOss.dealImgSrc(steps[1],g.user_id)
        data['step3'],url3,error3,error_img3 = aliOss.dealImgSrc(steps[2],g.user_id)
        data['step4'],url4,error4,error_img4 = aliOss.dealImgSrc(steps[3],g.user_id)
        data['admin_user_id'] = g.admin_user_id
        error_imgs =  error_img1+error_img2+error_img3+error_img4
        if len(error_imgs)>0:
            url_str = ',  '.join(error_imgs)
            return jsonify({'msg': '你的要评估的内容中的图片url服务器无法访问：'+url_str, "code": -1, 'items': [],"record_id":0}), 200
        if (error1+error2+error3+error4)>0:
            return jsonify({'msg': '数据录入超时，请重新发请求', "code": -1, 'items': [],"record_id":0}), 200
        urls = url1+url2+url3+url4
        UploadFiles.bulkInsert(urls, data["id"], g.user_id)
        aiSugScore.add_one(data)
    except Exception as e:
        MobileUserRight.set_right(mobile_user_right_record, 'requested_num', (mobile_user_right_record.requested_num - 1))
        return jsonify({'msg': '数据处理异常' , "code": -1, 'items': [],"record_id": 0}), 200
    if asy:
        thread = threading.Thread(target=done_ai, args=(data, service_type))
        thread.start()
        return jsonify({'msg': 'AI评估进行中,请稍后根据record_id发请求查看评估结果', "code": 0, 'items': [],"record_id": data["id"]}), 200
    else:
        items, msg = done_ai(data, service_type)
        code = 1  if items else -1
        return jsonify({'msg': msg, "code": code, 'items': items, "record_id": data["id"]}), 200


def done_ai(data, service_type):
    from app import app
    with app.app_context():
        try:
            rs = AiValSrvice.get_score_suggestion(service_type, data)
            aiSugScore.edit_ai(rs)
            return [[rs['ai_step1'], rs['step1_score']], [rs['ai_step2'], rs['step2_score']],
                    [rs['ai_step3'], rs['step3_score']], [rs['ai_step4'], rs['step4_score']]], 'AI评估成功'
        except Exception as e:
            mobile_user_right_record = MobileUserRight.get_one_right(data['admin_user_id'], service_type)
            MobileUserRight.set_right(mobile_user_right_record, 'requested_num', (mobile_user_right_record.requested_num - 1))
            return [], "请求超时，请重新发起评估请求"


@api.route('/get_val_result', methods=['GET', 'POST'])
def getValResult():
    data = request.json
    item = aiSugScore.get_one(g.user_id, data['record_id'])
    if item == None:
        return jsonify({'msg': 'record_id错误', "code": -1, 'items': [], "record_id": data["record_id"]}), 200
    if item.state == 0:
        timestamp = int(time.mktime(time.strptime(str(item.create_time), '%Y-%m-%d %H:%M:%S')))
        current_timestamp = time.time()
        if (current_timestamp - timestamp) >= 600:
            mess = "大模型评估超时"
            d = {}
            d['user_id'] = g.user_id
            d['state'] = -3
            aiSugScore.edit_ai_false_state(d, mess)
            return jsonify(
                {'msg': '系统评估失败，请稍后再重发请求', "code": -1, 'items': [], "record_id": data["id"]}), 200
        else:
            return jsonify({'msg': 'AI评估进行中,请稍后再根据record_id发请求查看评估结果', "code": 0, 'items': [],
                            "record_id": data["record_id"]}), 200
    elif item.state == -3:
        return jsonify(
            {'msg': '系统评估失败，请稍后再重发请求', "code": -1, 'items': [], "record_id": data["record_id"]}), 200
    elif item.state == -4:
        return jsonify(
            {'msg': '系统评估失败，请联系管理员检查原因', "code": -1, 'items': [], "record_id": data["record_id"]}), 200
    elif item.state == 1:
        items = [[item.ai_step1, item.step1_score], [item.ai_step2, item.step2_score],
                 [item.ai_step3, item.step3_score], [item.ai_step4, item.step4_score]]
        return jsonify({'msg': 'AI评估成功', "code": 1, 'items': items, "record_id": data["record_id"]}), 200
    else:
        return jsonify({'msg': 'record_id错误', "code": -1, 'items': [], "record_id": data["record_id"]}), 200


@api.route('/ai_question', methods=['POST'])
def aiQuestion():
    data = request.json
    item = aiSugScore.get_one(g.user_id, data['ai_score_id'])
    data['user_id'] = g.user_id
    asy = data['async']
    data['admin_user_id'] = g.admin_user_id
    data['answer'] = ""
    data['type'] = item.type
    mobileUserRightRecord = MobileUserRight.get_one_right(g.admin_user_id, item.type)
    rs,code = mobileUserRightRecord.check_request_right(mobileUserRightRecord)
    if code<0:
        return jsonify(rs),200
    dbId = valAiaq.addOne(data)
    markdown_table = aiSugScore.getMarkDownData(item)
    if asy == False:
        # answer = Ai.askScoreSuggestionTable(markdown_table, data['question'], str(item.type))
        # valAiaq.setAnswer(answer, dbId)
        # mobileUserRight.setRght(mobileUserRightRecord, 'requested_num', (mobileUserRightRecord.requested_num + 1))
        answer = doneAiAnswer(markdown_table, data['question'], item.type, dbId, item.admin_user_id)
        return jsonify({'msg': '回复成功', "code": 1, "answer": answer}), 200
    else:
        thread = threading.Thread(target=doneAiAnswer,args=(markdown_table, data['question'], item.type, dbId, item.admin_user_id))
        thread.start()
        return jsonify({'msg': '您的问题AI大模型正在思考中，请稍后根据val_ai_aq_id请求接口获取回答', "code": 0, 'answer': "","val_ai_aq_id": dbId}), 200


def doneAiAnswer(markdown_table, question, type, dbId, admin_user_id):
    from app import app
    with app.app_context():
        answer = Ai.askScoreSuggestionTable(markdown_table, question, str(type))
        valAiaq.setAnswer(answer, dbId)
        mobileUserRightRecord = MobileUserRight.get_one_right(admin_user_id, type)
        MobileUserRight.set_right(mobileUserRightRecord, 'requested_num', (mobileUserRightRecord.requested_num + 1))
        MobileUserRight.ai_val_sms(mobileUserRightRecord, admin_user_id, type)
        return answer

@api.route('/get_ai_answer', methods=['POST'])
def getAiAnswer():
    data = request.json
    item = valAiaq.getAqById(data['val_ai_aq_id'], g.user_id)
    if item == None:
        return jsonify({'msg': 'val_ai_aq_id错误', "code": -1, 'items': [], "record_id": data['val_ai_aq_id']}), 200
    if item.answer == "":
        timestamp = int(time.mktime(time.strptime(str(item.create_time), '%Y-%m-%d %H:%M:%S')))
        current_timestamp = time.time()
        if (current_timestamp - timestamp) >= 600:
            return jsonify(
                {'msg': "大模型思考超时", "code": -1, 'answer': "", "val_ai_aq_id": data['val_ai_aq_id']}), 200
        return jsonify(
            {'msg': '您的问题AI大模型正在思考中，请稍后根据val_ai_aq_id请求接口获取回答', "code": 0, 'answer': "",
             "val_ai_aq_id": data['val_ai_aq_id']}), 200
    else:
        return jsonify({'msg': '回复成功', "code": 1, "answer": item.answer}), 200

@api.route('/lx_upload_doc_deal', methods=['POST'])
def lxUploadDocDeal():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': ''}), 400
    data = request.form
    if file:
        extension = os.path.splitext(file.filename)[-1]
        tmpIdPath = f'./tmp/upload/{g.user_id}/'
        if not os.path.exists(tmpIdPath):
            os.mkdir(tmpIdPath)
        tmpIdPathFile = tmpIdPath + file.filename
        file.save(tmpIdPathFile)
        mobileUserRightRecord = MobileUserRight.get_one_right(g.admin_user_id, g.type)
        rs, code = mobileUserRightRecord.check_request_right(mobileUserRightRecord)
        if code < 0:
            return jsonify(rs), 200
        MobileUserRight.set_right(mobileUserRightRecord, 'requested_num', (mobileUserRightRecord.requested_num + 1))
        MobileUserRight.ai_val_sms(mobileUserRightRecord, g.admin_user_id, 2)
        recordId = LxAiSugScore.addApiUploadRec(data, file.filename, g.user_id, g.admin_user_id)
        asy = data['async']
        if asy == False:
            return dealLxUploadFileDone(tmpIdPathFile,recordId,g.user_id)
        else:
            thread = threading.Thread(target=dealLxUploadFileDone,args=(tmpIdPathFile,recordId,g.user_id))
            thread.start()
            return jsonify({'msg': '文件Ai处理中', "code": 1,"record_id": recordId,"items": [] }), 200
    else:
        return jsonify({'msg': '文件上传失败', "code": -1}), 200

def dealLxUploadFileDone(tmpIdPathFile,recordId,user_id):
    from app import app
    with app.app_context():
        try:
            id, key = aliDocAnalysis.SubmitDocParserJob(tmpIdPathFile)
        except:
            return jsonify({'msg': '文件上传失败', "code": -1}), 200
        markDownText = ""
        page = 1
        perPageNum = 3000
        lastNumberOfSuccessfulParsing = -1
        try:
            while (True):
                d = aliDocAnalysis.QueryDocParserStatus(id)
                if d['Status'] == 'Fail':
                    break
                if lastNumberOfSuccessfulParsing < d['NumberOfSuccessfulParsing']:
                    lastNumberOfSuccessfulParsing = d['NumberOfSuccessfulParsing']
                else:
                    if lastNumberOfSuccessfulParsing== 0 and d['Status']=="success":
                        break
                    time.sleep(1)
                    continue
                datas = aliDocAnalysis.GetDocParserResult(id, page, perPageNum)
                if lastNumberOfSuccessfulParsing <= page * perPageNum and d['Status'] == 'success':
                    for data in datas:
                        markDownText = markDownText + data['markdownContent']
                    break
                elif lastNumberOfSuccessfulParsing <= page * perPageNum and d['Status'] == 'Processing':
                    time.sleep(1)
                    continue
                elif lastNumberOfSuccessfulParsing > page * perPageNum and (
                        d['Status'] == 'Processing' or d['Status'] == 'success'):
                    for data in datas:
                        markDownText = markDownText + data['markdownContent']
                    page = page + 1
            LxAiSugScore.saveApiMarkdown(recordId, markDownText, key)
            return ai_done_thread(recordId, user_id)
        except Exception as e:
            return jsonify({'msg': '文件处理失败', "code": -1}), 200

# @api.route('/test', methods=['GET', 'POST'])
# def test():
#     return getTotal(50,109)



@api.route('/get_ai_lx', methods=['GET', 'POST'])
def getAiLxResult():
    data = request.json
    item = LxAiSugScore.getApiOneById(data['record_id'], g.user_id)
    if item.state == 1:
        items = [
            [item.step_1,item.step_1_ai,item.step_1_score],
            [item.step_2,item.step_2_ai,item.step_2_score],
            [item.step_3,item.step_3_ai,item.step_3_score],
            [item.step_4,item.step_4_ai,item.step_4_score],
            [item.step_5,item.step_5_ai,item.step_5_score],
        ]
        item_total = [item.total_score, LxAiSugScore.CASE_TEXT[item.case]]
        return jsonify({
           "code": 1,
           "items": items,
           "msg": "评估已完成",
           "item_total":item_total,
           "record_id": data['record_id']
        })
    elif item.state==-2:
        return jsonify({
           "code": 0,
           "items": [],
           "msg": "评估还在进行中",
           "item_total":[],
           "record_id": data['record_id']
        })
    elif item.state==-3:
        return jsonify({
           "code": -1,
           "items": [],
           "msg": "评估失败",
           "item_total":[],
           "record_id": data['record_id']
        })