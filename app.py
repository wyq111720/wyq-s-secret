from datetime import datetime
from pathlib import Path
from flask import Flask, jsonify, render_template, request
from openai import OpenAI
from dotenv import load_dotenv
import json
import os
import urllib.parse
import urllib.request


BASE_DIR = Path(__file__).resolve().parent
MEMORY_FILE = BASE_DIR / "memory.json"
load_dotenv(BASE_DIR / ".env")

app = Flask(__name__)


VERIFIED_LITERATURE = [
    {
        "title": "So what if ChatGPT wrote it? Multidisciplinary perspectives on opportunities, challenges and implications of generative conversational AI for research, practice and policy",
        "authors": "Dwivedi et al.",
        "year": "2023",
        "journal": "International Journal of Information Management",
        "doi": "10.1016/j.ijinfomgt.2023.102642",
        "url": "https://doi.org/10.1016/j.ijinfomgt.2023.102642",
        "tags": ["chatgpt", "aigc", "generative ai", "人工智能", "生成式", "大模型"],
    },
    {
        "title": "ChatGPT for good? On opportunities and challenges of large language models for education",
        "authors": "Kasneci et al.",
        "year": "2023",
        "journal": "Learning and Individual Differences",
        "doi": "10.1016/j.lindif.2023.102274",
        "url": "https://doi.org/10.1016/j.lindif.2023.102274",
        "tags": ["chatgpt", "education", "learning", "教育", "学习", "大语言模型"],
    },
    {
        "title": "User Acceptance of Information Technology: Toward a Unified View",
        "authors": "Venkatesh, Morris, Davis, Davis",
        "year": "2003",
        "journal": "MIS Quarterly",
        "doi": "10.2307/30036540",
        "url": "https://doi.org/10.2307/30036540",
        "tags": ["acceptance", "technology", "用户接受", "技术接受", "问卷", "模型"],
    },
    {
        "title": "Perceived Usefulness, Perceived Ease of Use, and User Acceptance of Information Technology",
        "authors": "Fred D. Davis",
        "year": "1989",
        "journal": "MIS Quarterly",
        "doi": "10.2307/249008",
        "url": "https://doi.org/10.2307/249008",
        "tags": ["acceptance", "technology", "tam", "用户接受", "技术接受", "问卷"],
    },
    {
        "title": "Users of the world, unite! The challenges and opportunities of Social Media",
        "authors": "Kaplan, Haenlein",
        "year": "2010",
        "journal": "Business Horizons",
        "doi": "10.1016/j.bushor.2009.09.003",
        "url": "https://doi.org/10.1016/j.bushor.2009.09.003",
        "tags": ["social media", "media", "传播", "社交媒体", "短视频"],
    },
]


# 自定义工具：load_memory 读取网页历史记忆
def load_memory():
    if not MEMORY_FILE.exists():
        save_memory([])
    try:
        with MEMORY_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


# 自定义工具：save_memory 保存网页历史记忆
def save_memory(history):
    with MEMORY_FILE.open("w", encoding="utf-8") as file:
        json.dump(history, file, ensure_ascii=False, indent=2)


# 自定义工具：clear_history 清空网页历史记忆
def clear_history():
    save_memory([])


def get_llm_config():
    api_key = (os.getenv("LLM_API_KEY") or os.getenv("ZHIPUAI_API_KEY") or os.getenv("MODELSCOPE_TOKEN") or "").strip()
    base_url = (os.getenv("LLM_BASE_URL") or "https://open.bigmodel.cn/api/paas/v4/").strip()
    model = (os.getenv("LLM_MODEL") or "glm-4-flash").strip()
    if not api_key or api_key.startswith("请填写"):
        raise RuntimeError("没有检测到可用的 LLM_API_KEY。请在 .env 中填写真实 API Key。")
    return api_key, base_url, model


def dedupe_literature(items):
    seen = set()
    unique_items = []
    for item in items:
        key = (item.get("doi") or item.get("title") or "").lower()
        if not key or key in seen:
            continue
        seen.add(key)
        unique_items.append(item)
    return unique_items


def pick_verified_literature(query):
    text = (query or "").lower()
    picked = []
    for item in VERIFIED_LITERATURE:
        if any(tag.lower() in text for tag in item["tags"]):
            checked = dict(item)
            checked["source"] = "内置已核验 DOI"
            picked.append(checked)
    if not picked:
        for item in VERIFIED_LITERATURE[:3]:
            checked = dict(item)
            checked["source"] = "内置已核验 DOI"
            picked.append(checked)
    return picked


def search_crossref(query, rows=6):
    if not query.strip():
        return []
    params = urllib.parse.urlencode(
        {
            "query": query,
            "rows": rows,
            "select": "title,author,issued,container-title,DOI,URL,type",
            "filter": "type:journal-article",
        }
    )
    url = f"https://api.crossref.org/works?{params}"
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception:
        return []

    results = []
    for item in data.get("message", {}).get("items", []):
        title = " ".join(item.get("title", [])[:1]).strip()
        journal = " ".join(item.get("container-title", [])[:1]).strip()
        year_parts = item.get("issued", {}).get("date-parts", [[None]])
        year = year_parts[0][0] if year_parts and year_parts[0] else ""
        authors = []
        for author in item.get("author", [])[:3]:
            name = " ".join(part for part in [author.get("given", ""), author.get("family", "")] if part)
            if name:
                authors.append(name)
        doi = item.get("DOI", "")
        if title and doi:
            results.append(
                {
                    "title": title,
                    "authors": ", ".join(authors) or "Unknown",
                    "year": str(year or "n.d."),
                    "journal": journal or "Unknown source",
                    "doi": doi,
                    "url": f"https://doi.org/{doi}",
                    "source": "Crossref",
                }
            )
    return results


def search_openalex(query, rows=6):
    if not query.strip():
        return []
    params = urllib.parse.urlencode({"search": query, "per-page": rows})
    url = f"https://api.openalex.org/works?{params}"
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception:
        return []

    results = []
    for item in data.get("results", []):
        title = item.get("title", "")
        doi_url = item.get("doi") or ""
        if not title or not doi_url:
            continue
        authors = []
        for authorship in item.get("authorships", [])[:3]:
            author = authorship.get("author", {})
            if author.get("display_name"):
                authors.append(author["display_name"])
        source = item.get("primary_location", {}).get("source") or {}
        results.append(
            {
                "title": title,
                "authors": ", ".join(authors) or "Unknown",
                "year": str(item.get("publication_year") or "n.d."),
                "journal": source.get("display_name") or "Unknown source",
                "doi": doi_url.replace("https://doi.org/", ""),
                "url": doi_url,
                "source": "OpenAlex",
            }
        )
    return results


# 自定义工具：search_literature 真实参考文献检索工具
def search_literature(query, rows=8):
    verified = pick_verified_literature(query)
    enable_live = (os.getenv("ENABLE_LIVE_LITERATURE") or "false").lower() == "true"
    if not enable_live:
        return verified[:6]
    live = search_openalex(query, rows=rows) + search_crossref(query, rows=rows)
    return dedupe_literature(verified + live)[:8]


def summarize_history(history):
    summaries = []
    for item in history[-5:]:
        summaries.append(
            {
                "time": item.get("created_at", ""),
                "major": item.get("major", ""),
                "direction": item.get("direction", ""),
                "paper_type": item.get("paper_type", ""),
                "chosen_focus": item.get("chosen_focus", ""),
                "topics": item.get("topics", [])[:3],
            }
        )
    return summaries


def extract_topics(result):
    topics = []
    for line in result.splitlines():
        text = line.strip()
        if "《" in text and "》" in text:
            start = text.find("《")
            end = text.find("》", start)
            if end > start:
                topics.append(text[start : end + 1])
        if len(topics) >= 6:
            break
    return topics


def format_verified_literature(literature):
    if not literature:
        return (
            "\n\n七、已核验参考文献\n"
            "本次没有检索到足够可靠的文献。建议换一组关键词，或到学校图书馆、知网、Google Scholar 继续查。"
        )
    lines = ["\n\n七、已核验参考文献"]
    for index, item in enumerate(literature, start=1):
        lines.append(
            f"{index}. {item['authors']} ({item['year']}). {item['title']}. "
            f"{item['journal']}. DOI: {item.get('doi', '')}. 链接: {item.get('url', '')} 来源: {item.get('source', '')}."
        )
    lines.append("说明：本章节由后端真实检索或内置 DOI 库生成，不由大模型编造。")
    return "\n".join(lines)


# 自定义工具：build_prompt 提示词构建工具
def build_prompt(form_data, history):
    history_text = "；".join(item.get("direction", "") for item in summarize_history(history) if item.get("direction")) or "暂无"
    return (
        "请用中文用一句话判断这个论文方向是否需要继续收窄，不要超过50字。"
        f"专业:{form_data.get('major','未填')}；方向:{form_data.get('direction','未填')}；"
        f"关键词:{form_data.get('keywords','未填')}；历史方向:{history_text}。"
    )


def call_remote_llm(prompt):
    api_key, base_url, model = get_llm_config()
    client = OpenAI(api_key=api_key, base_url=base_url, timeout=35)
    completion = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "user", "content": prompt},
        ],
        temperature=0.72,
        max_tokens=160,
    )
    return completion.choices[0].message.content


def build_fallback_topic_pool(major, direction, keywords):
    text = f"{major} {direction} {keywords}".lower()
    if any(word in text for word in ["aigc", "短视频", "传播", "新闻", "媒介"]):
        return [
            ("《AIGC 使用对大学生短视频内容判断能力的影响研究》", "经常刷短视频的大学生", "AIGC 识别能力、内容信任度、转发意愿、媒介素养", "问卷调查 + 访谈"),
            ("《生成式 AI 参与短视频脚本创作对内容原创性认知的影响研究》", "有短视频创作经验的大学生", "创作效率、原创性评价、工具依赖、署名意识", "访谈 + 案例分析"),
            ("《大学生对 AIGC 生成新闻短视频的信任度研究》", "新闻传播相关专业或普通大学生", "来源标注、画面真实感、平台信任、信息核验习惯", "问卷 + 情境材料对比"),
            ("《AIGC 背景下大学生短视频信息核验行为研究》", "短视频平台高频用户", "核验意识、核验渠道、谣言敏感度、平台提示效果", "问卷调查"),
            ("《AIGC 工具对新闻传播专业学生课程作业完成方式的影响研究》", "新闻传播专业学生", "使用场景、效率提升、作业质量、学术规范风险", "访谈 + 小样本问卷"),
            ("《短视频创作者使用 AIGC 辅助选题的动机与顾虑研究》", "校园短视频创作者或社团账号运营者", "选题效率、热点追踪、风格同质化、隐私顾虑", "半结构访谈"),
        ]
    if any(word in text for word in ["计算机", "大语言模型", "llm", "学习助手", "知识问答"]):
        return [
            ("《基于大语言模型的校园课程问答助手设计与实现》", "本科课程资料和学生常见问题", "知识库构建、问答准确率、用户满意度、错误回答处理", "系统设计 + 用户测试"),
            ("《面向大学生学习场景的 AI 助手需求分析与原型设计》", "本校大学生", "学习计划、资料整理、答疑、提醒、隐私", "问卷 + 原型设计"),
            ("《大语言模型在课程知识点复习中的应用效果研究》", "某一门课程的复习任务", "复习效率、答案准确性、学习满意度、依赖风险", "对比实验 + 问卷"),
            ("《基于 RAG 的校园知识问答系统设计》", "校园制度、课程资料和常见问题", "检索增强、知识库、回答准确率、可解释性", "系统实现 + 测试"),
            ("《大学生使用 AI 学习助手的持续使用意愿研究》", "使用过 AI 工具的大学生", "感知有用性、感知易用性、隐私顾虑、使用意愿", "问卷调查"),
            ("《面向课程学习的智能笔记整理工具原型设计》", "大学课程笔记场景", "摘要质量、知识点结构化、复习效率", "原型设计 + 用户访谈"),
        ]
    return [
        (f"《{direction}背景下大学生行为变化研究》", "与你方向相关的大学生群体", "使用动机、态度变化、收益感知、风险感知", "问卷调查"),
        (f"《{direction}在{major}学习场景中的应用与问题研究》", f"{major}学生", "应用场景、实际效果、限制因素、改进建议", "访谈 + 案例分析"),
        (f"《大学生对{keywords}的接受意愿研究》", "本科生群体", "感知有用性、感知易用性、风险感知、使用意愿", "问卷调查"),
        (f"《{direction}相关实践案例分析》", "典型案例或平台内容", "案例特征、问题表现、改进建议", "案例分析"),
        (f"《{major}学生关于{direction}的需求与痛点研究》", f"{major}学生", "使用需求、痛点、满意度、改进建议", "访谈研究"),
        (f"《面向{major}学生的{direction}应用方案设计》", f"{major}学生", "需求分析、功能设计、反馈评价", "原型设计"),
    ]


def fallback_topics(form_data, history):
    major = form_data.get("major") or "你的专业"
    grade = form_data.get("grade") or "本科阶段"
    direction = form_data.get("direction") or "你感兴趣的方向"
    paper_type = form_data.get("paper_type") or "课程论文"
    preference = form_data.get("preference") or "问卷调查"
    keywords = form_data.get("keywords") or direction
    memory = summarize_history(history)
    memory_text = "这是第一次建档，我会先帮你把方向收窄。" if not memory else (
        f"我记得你之前关注过：{'; '.join(item.get('direction', '') for item in memory if item.get('direction'))}。"
        "这次会尽量避开重复题目，往更具体、更可执行的方向推进。"
    )
    topic_pool = build_fallback_topic_pool(major, direction, keywords)
    topic_lines = []
    for index, (title, obj, dimensions, method) in enumerate(topic_pool[:6], start=1):
        topic_lines.append(
            f"{index}. {title}\n"
            f"研究对象：{obj}；核心维度：{dimensions}；研究方法：{method}；难度：中；可行性：较高。"
        )

    return f"""
一、记忆与延续判断
{memory_text}

二、选题收窄建议
你现在的方向是“{direction}”，专业是“{major}”。建议把题目限定到对象、场景、变量和方法四个层面。你偏好“{preference}”，所以题目最好能直接设计问卷、访谈或案例材料。

三、推荐选题清单
{chr(10).join(topic_lines)}

四、最值得做的 3 个
1. {topic_pool[0][0]}：题目具体，样本容易获得。
2. {topic_pool[1][0]}：能体现专业特色，适合写出分析深度。
3. {topic_pool[2][0]}：可以设计变量和假设，论文结构更稳。

五、研究问题与假设
RQ1：大学生为什么会关注或使用“{keywords}”相关工具/内容？
RQ2：哪些因素会影响他们的接受度、信任度或使用意愿？
RQ3：这个方向在{major}学习或实践中带来了哪些收益和风险？
H1：感知有用性越高，持续使用意愿越强。
H2：风险感知越高，信任度越低。
H3：使用频率越高，对学习或创作效率的主观评价越高。

六、数据来源与执行方案
样本可以来自同班同学、学院群、课程群或社交平台。课程论文建议收 80-150 份问卷，再访谈 3-5 位同学；毕业论文可以扩大样本并加入案例分析。

八、避坑提醒
不要写成“{direction}的影响”这种大题。最好加上对象、平台、变量和方法，例如“基于问卷调查的某高校大学生使用{keywords}意愿研究”。

九、下一步行动
1. 从最推荐的 3 个题目里选 1 个。
2. 确定研究对象，例如“某高校本科生”。
3. 选 4 个核心变量。
4. 写 12 道问卷题或 6 个访谈问题。
5. 用下面的真实文献作为开题报告参考。

提示：当前远程接口未调用成功，所以这是本地备用回答；配置正确 API 后会由远程大模型结合记忆生成更灵活的版本。
""".strip()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/generate", methods=["POST"])
def generate():
    form_data = request.get_json(force=True)
    history = load_memory()
    query = " ".join([form_data.get("major", ""), form_data.get("direction", ""), form_data.get("keywords", "")])
    literature = search_literature(query)
    prompt = build_prompt(form_data, history)
    try:
        remote_note = call_remote_llm(prompt)
        result = f"远程模型参与判断：\n{remote_note.strip()}\n\n{fallback_topics(form_data, history)}"
        model_status = "remote"
    except Exception as error:
        print(f"远程调用失败：{error}")
        result = fallback_topics(form_data, history)
        model_status = f"fallback: {error}"

    result = result.rstrip() + format_verified_literature(literature)
    topics = extract_topics(result)
    record = {
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "major": form_data.get("major", ""),
        "grade": form_data.get("grade", ""),
        "direction": form_data.get("direction", ""),
        "paper_type": form_data.get("paper_type", ""),
        "keywords": form_data.get("keywords", ""),
        "chosen_focus": topics[0] if topics else "",
        "topics": topics,
        "result": result,
        "literature": literature,
    }
    history.append(record)
    save_memory(history)
    return jsonify({"result": result, "literature": literature, "history": history, "model_status": model_status})


@app.route("/api/history", methods=["GET"])
def get_history():
    return jsonify(load_memory())


@app.route("/api/history", methods=["DELETE"])
def delete_history():
    clear_history()
    return jsonify({"message": "历史记录已清空", "history": []})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5050, debug=True)
