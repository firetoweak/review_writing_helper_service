import json

from flask import current_app

from models.ai_sug_score.model import AiSugScore
from models.ai_sug_score.model import AntiShakeLog
from models.model.model import ModuleToModel
from common.Ai import Ai
from concurrent.futures import ThreadPoolExecutor
from services.lx_ai_val_service import LxAiValSrvice
import sys
import time



class AiValSrvice:
    @staticmethod
    def get_score_suggestion(record_type,data):
        module= ModuleToModel.get_module_model(record_type)
        model = module.model.to_dict()
        module = module.to_dict()
        content_logs = ""
        res = {}
        if module['anti_shake_status'] == "closed" and  model['key_name'] !="xj-qianwen":
            result = Ai.get_score_suggestion(record_type,data,model)
            if result['state'] < 0:
                AiSugScore.edit_ai_false_state(data, result['error_message'])
                raise Exception(result['error_message'])
            res = result
        elif module['anti_shake_status'] == "open" and model['key_name'] !="xj-qianwen":
            with ThreadPoolExecutor(max_workers=5) as executor:
                future_list = [executor.submit(AiValSrvice.ai_get_score_suggestion, record_type,data,model) for step in  range(1,6)]
            # 等待所有任务完成，并获取结果
                results = [future.result() for future in future_list]
                res = results[0]
                score_lists = {}
                step_average_score = {}
                for step in AiSugScore.columnStep:
                    score_lists[step] = []
                    for result in results:
                        if step+'_score' in result and int(result[step+'_score'])>=0:
                            score_lists[step].append(int(result[step+'_score']))
                        else:
                            AiSugScore.edit_ai_false_state(data, result['error_message'])
                            raise Exception(result['error_message'])
                    step_average_score[step] = LxAiValSrvice.get_step_average_score(score_lists[step])
                    content_logs = f"{content_logs}{AiSugScore.pageShowConfig[int(record_type)][step]}5次分数:{score_lists[step]},平均分：{step_average_score[step]}<br>"
                    res[step+"_score"] = step_average_score[step]
        elif model['key_name'] =="xj-qianwen":
            start_time = time.time()
            result = Ai.get_xjqw_score_suggestion(data,model,record_type)
            end_time = time.time()
            if (end_time-start_time)>60:
                current_app.logger.error(f"Ai.get_xjqw_score_suggestion-新疆千问请求超一两分钟，请求时间：{end_time-start_time}")
            if result['state'] < 0:
                AiSugScore.edit_ai_false_state(data, result['error_message'])
                raise Exception(result['error_message'])
            res = result
            try:
                content_logs = AiValSrvice.get_xj_qianwen_log(result,record_type)
                print(content_logs)
            except Exception as e:
                data['state'] = -4
                current_app.logger.error(f"评估失败异常-get_score_suggestion-{model['model_name']}：{e},文件：{e.__traceback__.tb_frame.f_globals['__file__']};行数：{e.__traceback__.tb_lineno}")
                result['error_message'] = f"接口没按约定的格式返回数据:{json.dumps(result,ensure_ascii=False)};异常{e};"
                AiSugScore.edit_ai_false_state(data, result['error_message'])
                raise Exception("AI接口没按约定的格式返回数据")
        if content_logs != "":
            AntiShakeLog.add_one({"val_id":data['id'],"type":record_type,"content":content_logs})
        return res
    @staticmethod
    def ai_get_score_suggestion(record_type,data,model):
        from app import app
        with app.app_context():
            return Ai.get_score_suggestion(record_type,data,model)
    '''
    @staticmethod
    def get_xj_qianwen_log(result,record_type):
        log_content = ""
        score_lists = {}
        correct_score_lists = {}
        try:
            for step in AiSugScore.columnStep:
                score_lists[step] = []
                correct_score_lists[step] = []
                for llm in result['LLM_print'][step]:
                    score_lists[step].append(int(llm['score']))
                if result['correct_llm_print'][step]['type']=='valid':
                    for correct in result['correct_llm_print'][step]['result']:
                        correct_score_lists[step].append(int(correct['score']))
            for step in AiSugScore.columnStep:
                log_content = log_content + f"""
                                               <b>{AiSugScore.pageShowConfig[record_type][step]}:</b><br>
                                               &nbsp;&nbsp;&nbsp;五次防抖得分：{score_lists[step]}<br>
                                               """
                if result['correct_llm_print'][step]['type'] == "valid":
                    log_content = log_content + f"&nbsp;&nbsp;&nbsp;校准模型结果：{correct_score_lists[step]}<br>"
                else:
                    log_content = log_content + f"&nbsp;&nbsp;&nbsp;校准模型结果：没有进行校准模型的校验<br>"
                if result['judge_print'][step]['type'] == "valid":
                    log_content = log_content + f"&nbsp;&nbsp;&nbsp;裁判模型：<br>"
                    for value in result['judge_print'][step]["result"]:
                        log_content = log_content+f'&nbsp;&nbsp;&nbsp&nbsp;&nbsp&nbsp;{value["type"]}:{value["result"]}<br>'
                else:
                    log_content = log_content + f"&nbsp;&nbsp;&nbsp;裁判模型：没有进行裁判模型的裁判<br>"
                log_content =log_content+f'&nbsp;&nbsp;&nbsp;最终得分：{result[step + "_score"]}<br>'
            if str(record_type) == "1":
                if result['decision'] == "BUG":
                    log_content = log_content+"<b>当前需求为抱怨型需求</b><br>"
                else:
                    log_content = log_content+"<b>当前需求为改善型需求</b><br>"
        except Exception as e:
            current_app.logger.error(f"评估失败异常-get_score_suggestion：{e},文件：{e.__traceback__.tb_frame.f_globals['__file__']};行数：{e.__traceback__.tb_lineno}")
            return "日志记录异常"
        return log_content
    '''
    @staticmethod
    def get_xj_qianwen_log(result, record_type):
        log_content = ""
        score_lists = {}
        correct_score_lists = {}
        try:
            for step in AiSugScore.columnStep:
                score_lists[step] = []
                correct_score_lists[step] = []
                for llm in result['LLM_print'][step]:
                    score_lists[step].append(int(llm['score']))
            for step in AiSugScore.columnStep:
                log_content = log_content + f"""
                                               <b>{AiSugScore.pageShowConfig[record_type][step]}:</b><br>
                                               &nbsp;&nbsp;&nbsp;五次防抖得分：{score_lists[step]}<br>
                                               """
                log_content = log_content + f'&nbsp;&nbsp;&nbsp;最终得分：{result[step + "_score"]}<br>'
        except Exception as e:
            current_app.logger.error(
                f"评估失败异常-get_score_suggestion：{e},文件：{e.__traceback__.tb_frame.f_globals['__file__']};行数：{e.__traceback__.tb_lineno}")
            return "日志记录异常"
        return log_content