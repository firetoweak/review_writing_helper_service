import markdown
import html
from typing import Optional, Dict, Any


def convert_markdown_to_html(
        markdown_text: str,
) -> str:
    """
    将Markdown字符串转换为HTML标签

    参数:
        markdown_str: Markdown格式的字符串
    返回:
        转换后的HTML字符串

    示例:
        >>> md = "# 标题\\n**粗体**和*斜体*"
        >>> html = convert_markdown_to_html(md)
    """
    try:
        # 导入markdown库，如果未安装则给出提示
        try:
            import markdown
        except ImportError:
            raise ImportError(
                "请先安装markdown库：pip install markdown"
            )
        # 将Markdown转换为HTML md_in_html
        html = markdown.markdown(markdown_text, extensions=['tables'])
        return html

    except Exception as e:
        # 返回错误信息或回退到简单转换
        raise RuntimeError(f"Markdown转换失败: {str(e)}")


# 增强版本：支持更多选项和自定义处理
def convert_markdown_to_html_advanced(
        markdown_str: str,
        sanitize_html: bool = True,
        add_wrapper: bool = False,
        wrapper_class: str = "markdown-body",
        highlight_code: bool = False,
        **kwargs
) -> str:
    """
    增强版Markdown转HTML函数

    参数:
        markdown_str: Markdown格式的字符串
        sanitize_html: 是否清理HTML（防止XSS攻击）
        add_wrapper: 是否添加包装div
        wrapper_class: 包装div的CSS类名
        highlight_code: 是否启用代码高亮
        **kwargs: 传递给markdown.markdown的其他参数

    返回:
        转换后的HTML字符串
    """
    try:
        import markdown
        from markdown.extensions import Extension

        # 构建扩展列表
        extensions = kwargs.get('extensions', [])

        # 添加基础扩展
        base_extensions = ['extra', 'fenced_code', 'tables', 'nl2br']
        for ext in base_extensions:
            if ext not in extensions:
                extensions.append(ext)

        # 如果需要代码高亮
        if highlight_code:
            try:
                import pygments
                if 'codehilite' not in extensions:
                    extensions.append('codehilite')
            except ImportError:
                print("提示：要启用代码高亮，请安装Pygments: pip install pygments")

        # 如果启用HTML清理
        if sanitize_html:
            try:
                from markdown.extensions import sanitizer
                if 'sanitizer' not in extensions:
                    extensions.append('sanitizer')
            except ImportError:
                # 如果sanitizer不可用，使用safe_mode
                kwargs['safe_mode'] = True

        # 更新扩展列表
        kwargs['extensions'] = extensions

        # 转换Markdown
        html_output = markdown.markdown(markdown_str, **kwargs)

        # 添加包装div
        if add_wrapper:
            html_output = f'<div class="{wrapper_class}">{html_output}</div>'

        return html_output

    except ImportError:
        raise ImportError("请安装markdown库：pip install markdown")
    except Exception as e:
        # 如果转换失败，返回原始文本作为段落
        return f'<p>{html.escape(markdown_str)}</p>'


# 实用工具函数：处理常见场景
class MarkdownConverter:
    """Markdown转换器类，提供更多控制选项"""

    def __init__(self, **kwargs):
        """
        初始化转换器

        参数:
            **kwargs: 配置选项
        """
        self.config = {
            'extensions': ['extra', 'fenced_code', 'tables'],
            'output_format': 'html5',
            'safe_mode': False,
            **kwargs
        }

    def convert(self, markdown_str: str) -> str:
        """转换Markdown字符串"""
        return convert_markdown_to_html(markdown_str, **self.config)

    def convert_file(self, input_path: str, output_path: Optional[str] = None) -> str:
        """
        转换Markdown文件

        参数:
            input_path: 输入文件路径
            output_path: 输出文件路径（可选）

        返回:
            转换后的HTML字符串
        """
        with open(input_path, 'r', encoding='utf-8') as f:
            markdown_str = f.read()

        html_str = self.convert(markdown_str)

        if output_path:
            # 创建完整HTML文档
            full_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Markdown转换结果</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            line-height: 1.6;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
        }}
        pre {{
            background: #f5f5f5;
            padding: 1em;
            border-radius: 4px;
            overflow-x: auto;
        }}
        code {{
            background: #f5f5f5;
            padding: 2px 4px;
            border-radius: 3px;
        }}
        table {{
            border-collapse: collapse;
            width: 100%;
        }}
        th, td {{
            border: 1px solid #ddd;
            padding: 8px;
            text-align: left;
        }}
        th {{
            background-color: #f2f2f2;
        }}
        blockquote {{
            border-left: 4px solid #ddd;
            margin-left: 0;
            padding-left: 1em;
            color: #666;
        }}
    </style>
</head>
<body>
{html_str}
</body>
</html>"""

            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(full_html)

        return html_str

    @staticmethod
    def quick_convert(markdown_str: str) -> str:
        """快速转换（使用默认设置）"""
        return convert_markdown_to_html(markdown_str)


# 使用示例
if __name__ == "__main__":
    # 示例1：基本使用
    markdown_text =  """
    1. 写作宏观逻辑
    
    撰写该立项书的核心主线是构建一个从‘市场机会’到‘商业闭环’的逻辑闭环。首先，必须从真实客户场景出发，锚定‘日常生活’中的具体痛点，而非泛泛而谈‘智能机器人’的潜力。通过深度场景还原，验证痛点的普遍性与紧迫性，进而推导出可量化的市场空间（TAM）。接着，基于痛点定义产品价值，确保关键特性能精准解决客户问题，而非功能堆砌。再通过客户求证，验证价值设定的可行性。随后，从全价值链视角打开产品定义，覆盖从购买、使用到服务的全周期体验，识别并定义关键特性。最后，结合技术可行性、执行策略与财务模型，形成可落地的商业计划。整个过程必须确保每一环都可追溯、可验证、可推演，最终为投资决策者提供一个‘风险可控、收益可期、路径清晰’的商业论证，而非一个理想化的技术蓝图。
2. 思考步骤指导表

    | 思考步骤 | 核心灵魂拷问 | 常见思维误区 | 高阶论证技巧 | 写作落脚点 |
    |---|---|---|---|---|
    | 第一步-市场机会扫描 | 我们要解决的‘日常生活’场景中，到底是什么问题让客户感到痛苦？这个问题是否真实、普遍、且未被充分满足？ | 伪需求：把技术能力当作客户需求；忽视场景真实性。 | 用客户访谈、场景还原、竞品对比三重验证，确保痛点来自真实用户行为。 | 1.1 市场与竞争趋势宏观分析 |
    | 第二步-客户痛点锚定 | 在‘日常生活’场景中，客户具体在什么时间、什么地点、面对什么情境时，会触发这个痛点？ | 场景模糊化：用‘大概’‘可能’代替具体行为描述。 | 用‘5W1H’法（Who, When, Where, What, Why, How）还原场景，确保可复现。 | 1.2 场景化的客户核心痛点与需求分析 |
    | 第三步-痛点普遍性推演 | 这个痛点是否能从单个客户推演到一类人群？这类人群的规模、特征、行为模式是否一致？ | 以偏概全：用少数样本推断整体市场。 | 用客户画像+行为特征矩阵，进行交叉验证，确保推演逻辑自洽。 | 1.3 客户痛点与需求的普遍程度的推演与求证 |
    | 第四步-产品价值设定 | 我们的产品要提供什么关键特性，才能让客户在‘日常生活’中真正感受到价值？这个价值是否可量化、可感知？ | 功能自嗨：只描述技术指标，不关联客户收益。 | 用‘价值=特性×场景×收益’公式，确保每项特性都对应一个可感知的客户收益。 | 2.2 新产品基本概念与关键客户价值 |
    | 第五步-价值求证与假设 | 如果客户不买账，我们的产品价值设定是否还能成立？支撑价值的关键假设是什么？ | 忽视假设：把未验证的设想当作事实。 | 用‘假设-验证-迭代’循环，明确关键假设并设计验证路径。 | 2.3 支撑新产品客户价值的关键假设是什么？ |
    | 第六步-全价值链定义 | 除了核心功能，客户在购买、使用、服务等全旅程中，还有哪些隐性需求未被满足？ | 价值盲区：只关注功能，忽略服务、体验、成本等非功能价值。 | 用客户旅程地图，系统性打开全价值链，识别所有价值触点。 | 3.2 新产品全价值链条上的痛点需求与竞争 |
    | 第七步-技术与执行可行性 | 我们的技术能力能否支撑这些关键特性？如果不能，是否有替代方案或合作路径？ | 技术乐观主义：低估技术难度，高估研发速度。 | 用技术成熟度评估（TRL）+资源矩阵，量化技术风险与应对策略。 | 4.1 产品关键技术点地图与实现可行性分析 |
    | 第八步-商业闭环验证 | 从投入、产出、风险三个维度，是否能形成一个可量化的、正向的商业闭环？ | 财务虚高：收入预测脱离客户求证数据。 | 用‘求证数据→份额目标→SOM→ROI’链条，确保财务模型与市场判断一致。 | 5.2 当前版本新产品投入产出预算 |

3. 新手推荐写作顺序
    推荐写作顺序：1.2 → 1.3 → 2.2 → 2.4 → 3.2 → 3.5 → 3.7 → 4.1 → 5.2。理由：从‘场景化痛点’切入最容易上手，新人可先聚焦‘日常生活’中的具体场景（如家庭清洁、老人照护、儿童陪伴等），还原客户真实行为，避免空谈。接着推演痛点的普遍性，建立市场空间基础。然后基于痛点定义产品价值，再通过客户求证验证价值设定。之后打开全价值链，定义关键特性，并再次求证。最后，结合技术可行性与财务模型，完成商业闭环。此路径符合‘从具体到抽象、从客户到商业’的认知逻辑，避免在宏观分析或财务预测上过早卡壳。
    
    """
    md = "# 标题\\n**粗体**和*斜体*"
    html_result = convert_markdown_to_html(markdown_text)
    print(html_result)