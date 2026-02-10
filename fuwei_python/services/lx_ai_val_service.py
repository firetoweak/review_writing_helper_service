from models.doc_files.model import DocFiles
from models.lx_ai_sug_score.model import LxAiSugScore
import json
from models.lx_ai_sug_score.model import LxAntiShakeLog
from models.model.model import ModuleToModel
from common.Ai import Ai


class LxAiValSrvice:
    @staticmethod
    def get_report(id, user_id=0, state=1, is_admin=False):
        """
        :param is_admin:
        :param id:
        :param user_id:
        :param state:
        :return:
        """
        if not is_admin:
            item = LxAiSugScore.getOneById(id, user_id, state)
        else:
            item = LxAiSugScore.adminGetOneById(id, state=1)
        xmind_json = item.xmind_json
        xmind_json = json.loads(xmind_json)
        data = {'id': "root", 'topic': item.title, 'children': xmind_json['all_nodes']}
        fish_score1 = min([item.step_1_score, item.step_2_score])
        fish_score2 = item.step_3_score
        fish_score3 = min([item.step_3_score, item.step_4_score])
        case_text = DocFiles.getReportCase(item.case)
        report_titles = DocFiles.getReportTitles(item.select_1, item.select_2)
        return data, fish_score1, fish_score2, fish_score3, case_text,report_titles,item

    @staticmethod
    def get_total(record_id, user_id, old_state:int =-2):
        """

        :param record_id:
        :param user_id:
        :param old_state: -2为新增和调api
        :return:
        """
        item = LxAiSugScore.getOneById(record_id, user_id, old_state)
        state = 1
        five_step = 0
        three_step = 0
        tow_step = 0
        for i in range(1, 6):
            print('step_' + str(i) + '_score')
            score = getattr(item, 'step_' + str(i) + '_score')
            print("score:" + str(i))
            print(score)
            if score < 0:
                state = -3
                break
            if i <= 3:
                three_step = three_step + score
            if 2 <= i <= 3:
                tow_step = tow_step + score
            five_step = five_step + score
        summarize_text = getattr(item, 'summarize_text')
        xmind_json = getattr(item, 'xmind_json')
        summarize_val_sug = getattr(item, 'summarize_val_sug')
        if summarize_text == "" or xmind_json == "" or summarize_text is None or xmind_json is None or summarize_val_sug is None or summarize_val_sug == "":
            state = -3
        if state == 1:
            five_step = five_step / 5
            three_step = three_step / 3
            tow_step = tow_step / 2
            totalScore = min([five_step, three_step, tow_step])
            LxAiSugScore.set_sucess(record_id, user_id, 1, totalScore, old_state)
            return {'msg': 'AI评估成功', 'code': 1}
        else:
            LxAiSugScore.set_fail(record_id, user_id, old_state)
            return {'msg': 'AI评估失败', 'code': -1}

    @staticmethod
    def set_score_by_last_level(record_id, user_id, state):
        """
        根据上级得分是否及格决定下级得分的分数
        :param record_id:
        :param user_id:
        :param state:
        :return:
        """
        item = LxAiSugScore.getOneBySpecialId(record_id)
        log_content = f"原来的分数:{LxAiSugScore.drives['1']}:{item.step_1_score},{LxAiSugScore.drives['2']}:{item.step_2_score},{LxAiSugScore.drives['3']}:{item.step_3_score},{LxAiSugScore.drives['4']}:{item.step_4_score},{LxAiSugScore.drives['5']}:{item.step_5_score};"
        last_step_score = item.step_1_score
        for i in range(2,6):
            score = getattr(item,f'step_{i}_score')
            if last_step_score<6:
                if score>6:
                    score = 5
                else:
                    score = score - 1 if score>=1 else 0
                LxAiSugScore.set_score(item, i, score)
            last_step_score = score
        log_content = f"{log_content}最终得分：{LxAiSugScore.drives['1']}:{item.step_1_score},{LxAiSugScore.drives['2']}:{item.step_2_score},{LxAiSugScore.drives['3']}:{item.step_3_score},{LxAiSugScore.drives['4']}:{item.step_4_score},{LxAiSugScore.drives['5']}:{item.step_5_score}<br>"
        return log_content

    @staticmethod
    def set_case(record_id, user_id, state):
        item = LxAiSugScore.getOneById(record_id, user_id, state)
        tag = 1
        val_score = 6
        for text in LxAiSugScore.CASE_TEXT:
            if tag==1:
                if item.step_1_score<val_score or item.step_2_score<val_score:
                    break
            if tag == 2:
                if item.step_3_score<val_score:
                    break
            if tag == 3:
                if item.step_4_score < val_score or item.step_5_score < val_score:
                    break
            if tag ==4:
                if item.step_4_score >= val_score and item.step_5_score >= val_score:
                    break
            tag = tag+1
        item = LxAiSugScore.set_case(item, tag)
        return item

    @staticmethod
    def set_score_twice(record_id, user_id, state, step, res):
        item = LxAiSugScore.getOneById(record_id, user_id, state)
        score = getattr(item,f'step_{step}_score')
        log_content = f"{LxAiSugScore.drives[str(step)]}的原来分数：{score},AI返回结果：{res}"
        if score>=6 and res=='不合格':
            LxAiSugScore.set_score(item, step, 5)
            log_content = log_content+",最终入库分数：5"
        else:
            log_content = log_content + f",最终入库分数：{score}"
        return log_content

    @staticmethod
    def get_step_average_score(score_list):
        qualified = []
        not_qualified = []
        for score in score_list:
            if score>=6:
                qualified.append(score)
            else:
                if score<0:
                    return -1
                not_qualified.append(score)
        if len(qualified)>=3:
            return round(sum(qualified)/len(qualified))
        else:
            return round(sum(not_qualified)/len(not_qualified))


    @staticmethod
    def set_average_score(record_id, user_id, state, step_average_score, step_scores):
        """

        :param record_id:
        :param user_id:
        :param state:
        :param step_average_score: 平均分list
        :param step_scores: 所有的分数list
        :return:
        """
        item = LxAiSugScore.getOneById(record_id, user_id, state)
        content = ""
        for step,value in step_average_score.items():
            LxAiSugScore.set_score(item, step, value)
            content = f"{content}{LxAiSugScore.drives[step]}5次分数:{step_scores[str(record_id)][step]},平均分：{step_average_score[step]}<br>"
        return content

    @staticmethod
    def add_anti_shake_log(record_id, content):
        data = {'lx_id': record_id,  'content': content}
        LxAntiShakeLog.add_one(data)

    @staticmethod
    def get_lx_model():
        return ModuleToModel.get_module_model(2)

    @staticmethod
    def summarize_val_sug(record_id, user_id, state):
        item = LxAiSugScore.getOneById(record_id, user_id, state)
        ai_return,_ = Ai.summarize_val_sug(item)
        LxAiSugScore.set_summarize_val_sug(record_id, user_id, state, ai_return)
