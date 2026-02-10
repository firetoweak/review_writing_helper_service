from flask import Blueprint, render_template, request, jsonify, session, g, current_app, redirect, send_file, \
    after_this_request
from models.lx_ai_sug_score.model import LxAiSugScore
from models.doc_files.model import DocFiles
from models.users.models import MobileUserRight
import os
import threading
from common.aliDocAnalysis import aliDocAnalysis
import time
from datetime import datetime
from common.Ai import Ai
from common.aliOss import aliOss
from services.lx_ai_val_service import LxAiValSrvice
from concurrent.futures import ThreadPoolExecutor

import json

from services.upload_file_service import UploadFileService

lxAiVal = Blueprint('lxAiVal', __name__)
lxStepScoreLock = threading.RLock()
LxstepScoresThread = {}
@lxAiVal.before_request
def before_request():
    g.type = 2
    if 'user_id' not in session:
        if request.method == "GET":
            js_code = """
            <script type="text/javascript">
                    alert('请重新登录！！！！');
                    location.href="/"
            </script>
            """
            return js_code
        else:
            return jsonify({'msg': '请先登录', "code": 1}), 200
    return None


@lxAiVal.route('/list')
def lists():
    state = request.values.get('state','')
    search = request.values.get('search','').strip()
    continue_add = request.values.get('continue_add','0')
    pagination,items = LxAiSugScore.getList(g.user_id, g.type, state, search)
    date_end, request_font_red, invite_font_red, Rights = MobileUserRight.get_right_style(g.admin_user_id, g.type)
    caseTextList = DocFiles.getReportCaseArr()
    return render_template('user/lxAiVal/list.html',
                           invite_font_red=invite_font_red,
                           request_font_red = request_font_red,
                           items=items,
                           type=g.type,
                           pagination=pagination,
                           Rights=Rights,
                           user_type=g.user_type,
                           dateEnd=date_end,
                           state=state,
                           search=search,
                           continue_add=continue_add,
                           caseTextList = caseTextList
                           )

@lxAiVal.route('/report')
def report():
    id = request.values.get('id',0)
    data, fish_score1, fish_score2, fish_score3, caseText, reportTitles,item = LxAiValSrvice.get_report(id, g.user_id, state=1)
    return render_template('user/lxAiVal/report.html', xmind=json.dumps(data,ensure_ascii=False), item = item, select_1=LxAiSugScore.select_1_text[int(item.select_1)], select_2=LxAiSugScore.select_2_text[int(item.select_2)], case_text=caseText, fish_score1=fish_score1, fish_score2=fish_score2, fish_score3=fish_score3, report_titles=reportTitles)

@lxAiVal.route('/upload_doc', methods=['POST'])
def upload_doc():
    record_id = request.values.get('id', 0)
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    mobileUserRightRecord = MobileUserRight.get_one_right(g.admin_user_id, g.type)
    rs,code = mobileUserRightRecord.check_request_right(mobileUserRightRecord)
    if code<0:
        return jsonify(rs),200
    MobileUserRight.set_right(mobileUserRightRecord, 'requested_num', (mobileUserRightRecord.requested_num + 1))
    MobileUserRight.ai_val_sms(mobileUserRightRecord, g.admin_user_id, 2)
    extension = os.path.splitext(file.filename)[-1]
    if extension.lower() not in ['.ppt','.pptx','.doc','.docx','.pdf']:
        return jsonify({'msg': '你上传的文件类型不被允许','code': -1}), 200
    if file:
        key,url,_ = UploadFileService.upload_files(file,f"{g.user_id}")
        data = {'file_name': file.filename}
        record_id = LxAiSugScore.addUploadRec(data, g.user_id, g.admin_user_id, record_id)
        cache = current_app.extensions.get('cache')
        cache.setdefault(str(g.user_id) +"upload_state" + str(record_id), "uploading")
        thread = threading.Thread(target=UploadFileService.lx_deal_markdown, args=(g.user_id, key, cache, record_id))
        thread.start()
        return jsonify({'msg': '上传成功', 'id': record_id, 'code': 1}), 200
    else:
        return jsonify({'msg': '服务器端错误', 'filename': "", 'code': -100}), 200

@lxAiVal.route('/upload_finish', methods=['POST'])
def uploadFinish():
    data = request.json
    if 'select_1' not in data:
        data['select_1'] = '0'
    if 'select_2' not in data:
        data['select_2'] = '0'
    if str(data['select_1']) not in ['0','1','2','3']:
        data['select_1'] = '0'
    if str(data['select_2']) not in ['0','1']:
        data['select_2'] = '0'
    LxAiSugScore.saveUploadFinish(data, g.user_id)
    return jsonify({'msg': '更新成功', 'code': 1}), 200

@lxAiVal.route('/get_ai_done_state', methods=['POST', "GET"])
def aiDoneState():
    id = request.values.get('id',0)
    item = LxAiSugScore.getApiOneById(id, g.user_id)
    if item==None:
        return jsonify({'msg': '记录id错误', 'code': -1}), 200
    if item.state == -2:
        return jsonify({'msg': '评估中', 'code': 0}), 200
    if item.state == -3:
        return jsonify({'msg': '评估失败', 'code': -1}), 200
    else:
        return jsonify({'msg': '评估完成', 'code': 1}), 200

@lxAiVal.route('/get_upload_state', methods=['POST'])
def get_upload_state():
    return UploadFileService.get_upload_state()

@lxAiVal.route('/ai_done', methods=['POST', "GET"])
def ai_done():
    record_id = request.values.get('id', 0)
    thread = threading.Thread(target=ai_done_thread, args=(record_id, g.user_id))
    thread.start()
    #return aiDoneThread(id,user_id)
    return jsonify({'msg': 'AI评估中', 'code': 0}), 200


@lxAiVal.route('/download', methods=['POST', "GET"])
def download():
    # def remove_file(tmp_file_path):

    record_id = request.values.get('id', 0)
    user_id = g.user_id
    item = LxAiSugScore.getApiOneById(record_id, user_id)
    if item is None:
        return "文件不存在"
    file_key = item.file_key
    local_path = f'./tmp/download/{user_id}/'
    if not os.path.exists(local_path):
        os.mkdir(local_path)
    tmp_file_path,file_name = aliOss.downLoadOne(file_key,local_path)
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
        if os.path.exists(tmp_file_path):
            os.remove(tmp_file_path)

        # thread = threading.Thread(target=remove_file,args=(tmp_file_path,))
        # thread.start()



@lxAiVal.route('/delete', methods=['POST', "GET"])
def delOne():
    id = request.values.get('id',0)
    LxAiSugScore.delOne(id, g.user_id)
    return redirect(f"/user/lxAiVal/list?type={g.type}")

@lxAiVal.route('/batch_delete', methods=['GET', 'POST'])
def batchDelete():
    data = request.json
    for id in data['ids']:
        LxAiSugScore.delOne(id, g.user_id)
    return jsonify({'msg': '批量删除成功', "code": 1}), 200

@lxAiVal.route('/repeat', methods=['GET', 'POST'])
def repeat():
    id = request.values.get('id',0)
    LxAiSugScore.repeat_set_state(id, g.user_id)
    thread = threading.Thread(target=ai_done_thread, args=(id, g.user_id))
    thread.start()
    return  jsonify({'msg': '评估中', 'code': 0}), 200

# @lxAiVal.route("/test", methods=['GET', 'POST'])
# def test():
#     shared_variable = {}
#     def test2():
#         from app import app
#         with app.app_context():
#             global shared_variable
#             lock.acquire()  # 获取锁
#             shared_variable['test'].append('11111')
#             shared_variable['test2'].append('22222')
#             lock.release()  # 释放锁
#     shared_variable['test'] = []
#     shared_variable['test2'] = []
#     thread = threading.Thread(target=test2)
#     thread.start()
#     thread.join()
#     print(shared_variable)
#     del shared_variable['test']
#     print(shared_variable)
#     return ""



@lxAiVal.route("/test", methods=['GET', 'POST'])
def test():
    from conf.db import db
    from sqlalchemy import text

    record_id = 277
    stmt = text("SELECT step_1_score,step_2_score FROM ai_sug_score_2 WHERE id = :id")
    result = db.session.execute(stmt, {"id": record_id})

    print(result.first())


    # from models.model.model import ModuleToModel
    # model:ModuleToModel = AiVal2Srvice.get_lx_model().model
    # print(model.to_dict())
    # return model.to_dict()
    # from models.aiSugScore import AiSugScore
    # from models.antiShakeLog import LxAntiShakeLog
    # a:AiSugScore = AiSugScore.query.get('10920250718094030218771')
    # print(a.anti_shake_logs.filter(LxAntiShakeLog.type==102).all())
    #     aiDoneThread(177,76,-3)
    #     return ''
def ai_done_thread(record_id, user_id, state=-2):
    """
    这个函数api一起调用的
    重新评估的时候state=-3
    调用api的时候state=-2
    选完那两项以后state=-2
    """
    from app import app
    with app.app_context():
        item = LxAiSugScore.getOneById(record_id, user_id, state)
        print("aiDoneThread")
        if item is None:
            print('id错误')
            return jsonify({'msg': 'id错误或立项文档处理失败', 'code': -1}), 200
        model = LxAiValSrvice.get_lx_model()
        module = model.model.to_dict()
        model = model.to_dict()
        current_threads = []
        step_threads = []
        is_val_score = False
        lxStepScoreLock.acquire()
        LxstepScoresThread[str(record_id)] = {}
        LxstepScoresThread[str(record_id)]['tmp_log'] = ""
        lxStepScoreLock.release()
        if module['key_name']!= "xj-qianwen":
            for x in range(1,6):
                for key,value in LxAiSugScore.drives.items():
                    data = {'stepNum': key, 'child_type_1': item.select_1, 'child_type_2': item.select_2,'markdown': item.all_markdwon_text}
                    score = getattr(item,'step_'+key+'_score')
                    print('score:'+str(score))
                    if score is None or score==-1:
                        if key not in  LxstepScoresThread[str(record_id)]:
                            lxStepScoreLock.acquire()
                            LxstepScoresThread[str(record_id)][key] = []
                            lxStepScoreLock.release()
                        is_val_score = True
                        thread = threading.Thread(target=get_step, args=(record_id, user_id, data, state, model,module))
                        step_threads.append(thread)
                        thread.start()
                if model['anti_shake_status']=="closed" or module['key_name']== "xj-qianwen":
                    break
        summarize =  getattr(item,'summarize_text')
        if summarize is None or summarize== "":
            thread = threading.Thread(target=get_summarize, args=(record_id, user_id, item.all_markdwon_text, state))
            current_threads.append(thread)
            thread.start()
        xmind_json = getattr(item,'xmind_json')
        if xmind_json is None or xmind_json== "":
            thread = threading.Thread(target=get_xmind, args=(record_id, user_id, item.all_markdwon_text, state))
            current_threads.append(thread)
            thread.start()
        for thread in step_threads:
            thread.join()
        if item.summarize_val_sug == "" or item.summarize_val_sug is None:
            thread = threading.Thread(target=summarize_val_sug, args=(record_id,user_id,state))
            current_threads.append(thread)
            thread.start()
        if is_val_score:
            step_average_score = {}
            print(LxstepScoresThread[str(record_id)])
            content_logs = ""
            if model['anti_shake_status']=="open" and module['key_name']!="xj-qianwen":
                for key, value in LxstepScoresThread[str(record_id)].items():  # 如果是repeat的话有可能不是全部执行
                    if key =="tmp_log":
                        continue
                    step_average_score[key] = LxAiValSrvice.get_step_average_score(LxstepScoresThread[str(record_id)][key])
                    # 获取分数失败
                    if step_average_score[key] == -1:
                        LxAiSugScore.set_fail(record_id, user_id, state)
                        lxStepScoreLock.acquire()
                        del LxstepScoresThread[str(record_id)]
                        lxStepScoreLock.release()
                        return {'msg': 'AI评估失败', 'code': -1}
                content_logs = "<b>平均分记录入库：</b><br>"
                content_log = LxAiValSrvice.set_average_score(record_id, user_id, state, step_average_score, LxstepScoresThread)
                content_logs = content_logs+content_log
            if model['anti_shake_status']=="closed":
                content_logs ="防抖已被关闭<br>"
            with ThreadPoolExecutor(max_workers=2) as executor:
                # 提交所有任务
                future_list = [executor.submit(get_twice_score, record_id, user_id, state, step) for step in [2, 3]]
                # 等待所有任务完成，并获取结果
                results = [future.result() for future in future_list]
            content_logs = content_logs + "<b>根据AI评估建议判定是否合格：</b><br>"+";".join(results)+"<br>"
            content_log = LxAiValSrvice.set_score_by_last_level(record_id, user_id, state)
            content_logs = content_logs+"<b>根据上级得分是否及格决定下级得分:</b><br>"+content_log
            lxStepScoreLock.acquire()
            del LxstepScoresThread[str(record_id)]
            lxStepScoreLock.release()
            LxAiValSrvice.add_anti_shake_log(record_id, content_logs)
        item = LxAiValSrvice.set_case(record_id, user_id, state)
        print(f"setScoretwice:{item.step_1_score},{item.step_2_score},{item.step_3_score},{item.step_4_score},{item.step_5_score}")
        for thread in current_threads:
            thread.join()
        return jsonify(LxAiValSrvice.get_total(record_id, user_id, state)),200

def get_step(record_id, user_id, data, state, module,model):
    from app import app
    with app.app_context():
        if model['key_name'] !="xj-qianwen":
            aiReturn,_ = Ai.get_lx_content_score_suggestion(2, data,model)
            if module['anti_shake_status']=="open":
                lxStepScoreLock.acquire()
                LxstepScoresThread[str(record_id)][data['stepNum']].append(int(float(str(aiReturn['step_' + str(data['stepNum']) + '_score']).replace("分",""))))
                lxStepScoreLock.release()
                aiReturn['step_'+str(data['stepNum']+'_score')] = None
            LxAiSugScore.set_step(record_id, user_id, aiReturn, state, len(LxstepScoresThread[str(record_id)][data['stepNum']]))
        else:
            return ""


def get_summarize(record_id, user_id, all_markdwon_text, state):
    from app import app
    with app.app_context():
        aiReturn,_ = Ai.get_summarize(all_markdwon_text)
        #aiReturn['summarize_text'] = markdown.markdown(aiReturn['summarize_text'])
        LxAiSugScore.set_summarize(record_id, user_id, aiReturn, state)

def get_xmind(id, user_id, all_markdwon_text, state):
    from app import app
    with app.app_context():
        aiReturn,_ = Ai.get_xmind(all_markdwon_text)
        LxAiSugScore.setXmind(id, user_id, aiReturn, state)


def get_twice_score(record_id, user_id, state,  step=2):
    from app import app
    with app.app_context():
        item = LxAiSugScore.getOneById(record_id, user_id, state)
        step_ai = getattr(item,f'step_{step}_ai')
        res = Ai.val_score_twice(step_ai, step)
        print(f"二次评定结果{step}："+res)
        return  LxAiValSrvice.set_score_twice(record_id, user_id, state, step, res)
        # lock.acquire()
        # stepScores[str(record_id)]['tmp_log'] = stepScores[str(record_id)]['tmp_log']+log
        # lock.release()

def summarize_val_sug(record_id, user_id, state):
    from app import app
    with app.app_context():
        LxAiValSrvice.summarize_val_sug(record_id, user_id, state)
