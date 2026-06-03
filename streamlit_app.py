import json, os, urllib.parse, urllib.request
from datetime import datetime
from pathlib import Path
import streamlit as st
from openai import OpenAI

BASE_DIR = Path(__file__).resolve().parent
MEMORY_FILE = BASE_DIR / "memory.json"
st.set_page_config(page_title="专属选题管家", page_icon="🧠", layout="wide")

def get_secret(name, default=""):
    try:
        if name in st.secrets:
            return str(st.secrets[name]).strip()
    except Exception:
        pass
    return os.getenv(name, default).strip()

def get_llm_config():
    return (
        get_secret("LLM_API_KEY") or get_secret("ZHIPUAI_API_KEY") or get_secret("AI_API_KEY"),
        get_secret("LLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4/"),
        get_secret("LLM_MODEL", "glm-4-flash"),
    )

VERIFIED_LITERATURE = [
    {"title":"So what if ChatGPT wrote it? Multidisciplinary perspectives on opportunities, challenges and implications of generative conversational AI for research, practice and policy","authors":"Dwivedi et al.","year":"2023","journal":"International Journal of Information Management","doi":"10.1016/j.ijinfomgt.2023.102642","url":"https://doi.org/10.1016/j.ijinfomgt.2023.102642","tags":["chatgpt","aigc","generative ai","人工智能","生成式","大模型"]},
    {"title":"ChatGPT for good? On opportunities and challenges of large language models for education","authors":"Kasneci et al.","year":"2023","journal":"Learning and Individual Differences","doi":"10.1016/j.lindif.2023.102274","url":"https://doi.org/10.1016/j.lindif.2023.102274","tags":["chatgpt","education","learning","教育","学习","大语言模型"]},
    {"title":"User Acceptance of Information Technology: Toward a Unified View","authors":"Venkatesh, Morris, Davis, Davis","year":"2003","journal":"MIS Quarterly","doi":"10.2307/30036540","url":"https://doi.org/10.2307/30036540","tags":["acceptance","technology","用户接受","技术接受","问卷","模型"]},
    {"title":"Perceived Usefulness, Perceived Ease of Use, and User Acceptance of Information Technology","authors":"Fred D. Davis","year":"1989","journal":"MIS Quarterly","doi":"10.2307/249008","url":"https://doi.org/10.2307/249008","tags":["acceptance","technology","tam","用户接受","技术接受","问卷"]},
    {"title":"Users of the world, unite! The challenges and opportunities of Social Media","authors":"Kaplan, Haenlein","year":"2010","journal":"Business Horizons","doi":"10.1016/j.bushor.2009.09.003","url":"https://doi.org/10.1016/j.bushor.2009.09.003","tags":["social media","media","传播","社交媒体","短视频"]},
]

def load_memory():
    if not MEMORY_FILE.exists(): MEMORY_FILE.write_text('[]', encoding='utf-8')
    try:
        data=json.loads(MEMORY_FILE.read_text(encoding='utf-8'))
        return data if isinstance(data, list) else []
    except Exception:
        return []

def save_memory(history):
    MEMORY_FILE.write_text(json.dumps(history[-30:], ensure_ascii=False, indent=2), encoding='utf-8')

def clear_memory(): save_memory([])

def summarize_history(history):
    if not history: return '暂无历史记录，这是第一次建档。'
    return '\n'.join([f"- {i.get('created_at','')}｜{i.get('major','')}｜{i.get('direction','')}｜{i.get('chosen_focus','')}" for i in history[-5:]])

def pick_verified_literature(query):
    text=(query or '').lower(); picked=[]
    for item in VERIFIED_LITERATURE:
        if any(tag.lower() in text for tag in item['tags']):
            x=dict(item); x['source']='内置已核验 DOI'; picked.append(x)
    if not picked:
        for item in VERIFIED_LITERATURE[:3]:
            x=dict(item); x['source']='内置已核验 DOI'; picked.append(x)
    return picked

def search_crossref(query, rows=5):
    if not query.strip(): return []
    params=urllib.parse.urlencode({'query':query,'rows':rows,'select':'title,author,issued,container-title,DOI,URL,type','filter':'type:journal-article'})
    try:
        with urllib.request.urlopen(f'https://api.crossref.org/works?{params}', timeout=8) as r:
            data=json.loads(r.read().decode('utf-8'))
    except Exception:
        return []
    out=[]
    for item in data.get('message',{}).get('items',[]):
        title=' '.join(item.get('title',[])[:1]).strip(); doi=item.get('DOI','')
        if not title or not doi: continue
        journal=' '.join(item.get('container-title',[])[:1]).strip() or 'Unknown source'
        parts=item.get('issued',{}).get('date-parts',[[None]]); year=parts[0][0] if parts and parts[0] else 'n.d.'
        authors=[]
        for a in item.get('author',[])[:3]:
            name=' '.join(p for p in [a.get('given',''), a.get('family','')] if p)
            if name: authors.append(name)
        out.append({'title':title,'authors':', '.join(authors) or 'Unknown','year':str(year),'journal':journal,'doi':doi,'url':f'https://doi.org/{doi}','source':'Crossref'})
    return out

def dedupe(items):
    seen=set(); out=[]
    for i in items:
        k=(i.get('doi') or i.get('title') or '').lower()
        if k and k not in seen:
            seen.add(k); out.append(i)
    return out

def search_literature(query):
    enable=str(get_secret('ENABLE_LIVE_LITERATURE','false')).lower()=='true'
    return dedupe(pick_verified_literature(query)+(search_crossref(query) if enable else []))[:8]

def build_prompt(form, history):
    return f"""
你是“专属选题管家”，要像一位会连续追踪学生想法的论文导师。
用户本次输入：
- 专业：{form.get('major','未填写')}
- 年级：{form.get('grade','未填写')}
- 想做方向：{form.get('direction','未填写')}
- 论文/项目类型：{form.get('paper_type','未填写')}
- 研究偏好：{form.get('preference','未填写')}
- 关键词：{form.get('keywords','未填写')}
- 补充说明：{form.get('extra_info','未填写')}
你记住的近期选题记录：
{summarize_history(history)}
请用中文输出：一、记忆与延续判断；二、选题收窄建议；三、推荐选题清单（6个，含研究对象/变量/方法/难度/创新点/可行性）；四、最值得做的3个；五、研究问题与假设；六、数据来源与执行方案；七、避坑提醒；八、下一步行动。不要编造参考文献。
"""

def call_remote_llm(prompt):
    api_key, base_url, model = get_llm_config()
    if not api_key or api_key.startswith('请填写'):
        raise RuntimeError('没有检测到有效 API Key，请在 Streamlit Cloud 的 Secrets 中配置 LLM_API_KEY。')
    client=OpenAI(api_key=api_key, base_url=base_url, timeout=45)
    rsp=client.chat.completions.create(model=model, messages=[{'role':'system','content':'你是严谨、具体、适合大学生课程作业的中文论文选题顾问。不要编造文献。'},{'role':'user','content':prompt}], temperature=0.72, max_tokens=1800)
    return rsp.choices[0].message.content

def fallback_answer(form, history, err=''):
    major=form.get('major') or '你的专业'; direction=form.get('direction') or '你感兴趣的方向'; pref=form.get('preference') or '问卷调查'; keywords=form.get('keywords') or direction
    if any(w in f'{major} {direction} {keywords}'.lower() for w in ['aigc','短视频','传播','新闻','媒介']):
        topics=[('《AIGC 使用对大学生短视频内容判断能力的影响研究》','经常刷短视频的大学生','AIGC识别能力、内容信任度、转发意愿、媒介素养','问卷调查+访谈'),('《生成式 AI 参与短视频脚本创作对内容原创性认知的影响研究》','有短视频创作经验的大学生','创作效率、原创性评价、工具依赖、署名意识','访谈+案例分析'),('《大学生对 AIGC 生成新闻短视频的信任度研究》','新闻传播相关专业或普通大学生','来源标注、画面真实感、平台信任、信息核验习惯','问卷+情境材料对比'),('《AIGC 背景下大学生短视频信息核验行为研究》','短视频平台高频用户','核验意识、核验渠道、谣言敏感度、平台提示效果','问卷调查'),('《AIGC 工具对新闻传播专业学生课程作业完成方式的影响研究》','新闻传播专业学生','使用场景、效率提升、作业质量、学术规范风险','访谈+小样本问卷'),('《短视频创作者使用 AIGC 辅助选题的动机与顾虑研究》','校园短视频创作者或社团账号运营者','选题效率、热点追踪、风格同质化、隐私顾虑','半结构访谈')]
    else:
        topics=[(f'《{direction}背景下大学生行为变化研究》','相关大学生群体','使用动机、态度变化、收益感知、风险感知','问卷调查'),(f'《{direction}在{major}学习场景中的应用与问题研究》',f'{major}学生','应用场景、实际效果、限制因素、改进建议','访谈+案例分析'),(f'《大学生对{keywords}的接受意愿研究》','本科生群体','感知有用性、感知易用性、风险感知、使用意愿','问卷调查')]
    lines='\n'.join([f'{n}. {t}\n研究对象：{o}；核心维度：{d}；研究方法：{m}；难度：中；可行性：较高。' for n,(t,o,d,m) in enumerate(topics,1)])
    return f"""【本地备用回答】
远程 API 暂时没有调用成功，但网页、历史记忆和文献工具仍可展示。
失败原因：{err}

一、记忆与延续判断
{summarize_history(history)}

二、选题收窄建议
你现在的方向是“{direction}”，专业是“{major}”。建议限定对象、场景、变量和方法。你偏好“{pref}”，所以题目最好能直接设计问卷、访谈或案例材料。

三、推荐选题清单
{lines}

四、最值得做的 3 个
1. {topics[0][0]}：题目具体，样本容易获得。
2. {topics[1][0]}：能体现专业特色，适合写出分析深度。
3. {topics[2][0]}：可以设计变量和假设，论文结构更稳。

五、研究问题与假设
RQ1：大学生为什么会关注或使用“{keywords}”相关工具/内容？
RQ2：哪些因素会影响他们的接受度、信任度或使用意愿？
RQ3：这个方向在{major}学习或实践中带来了哪些收益和风险？
H1：感知有用性越高，持续使用意愿越强。
H2：风险感知越高，信任度越低。
H3：使用频率越高，对学习或创作效率的主观评价越高。

六、数据来源与执行方案
建议收 80-150 份问卷，再访谈 3-5 位同学。样本可来自同班同学、学院群、课程群或社交平台。

七、避坑提醒
不要写成“{direction}的影响”这种大题。最好加上对象、平台、变量和方法。

八、下一步行动
1. 从最推荐的 3 个题目里选 1 个。
2. 确定研究对象。
3. 选 4 个核心变量。
4. 写 12 道问卷题或 6 个访谈问题。
5. 用下面的真实文献作为开题报告参考。"""

def extract_topics(result):
    topics=[]
    for line in result.splitlines():
        if '《' in line and '》' in line:
            s=line.find('《'); e=line.find('》',s)
            if e>s: topics.append(line[s:e+1])
        if len(topics)>=6: break
    return topics

def format_lit(lit):
    if not lit: return '\n\n九、已核验参考文献\n本次没有检索到合适文献。'
    lines=['\n\n九、已核验参考文献']
    for n,i in enumerate(lit,1): lines.append(f"{n}. {i['authors']} ({i['year']}). {i['title']}. {i['journal']}. DOI: {i.get('doi','')}. {i.get('url','')} 来源：{i.get('source','')}.")
    lines.append('说明：本章节由后端真实检索或内置 DOI 库生成，不由大模型编造。')
    return '\n'.join(lines)

st.markdown('<style>.block-container{padding-top:2rem}.hero{padding:1.5rem;border-radius:24px;background:#fffaf6;box-shadow:0 20px 55px rgba(43,101,82,.18);margin-bottom:1rem}</style>', unsafe_allow_html=True)
st.markdown('<div class="hero"><b>Topic Butler AI</b><h1>你的专属选题管家</h1><p>告诉我你的专业、方向和论文类型。我会结合历史记忆，帮你拆出可写、可查、可展示的选题。</p></div>', unsafe_allow_html=True)
api_key, base_url, model = get_llm_config()
with st.sidebar:
    st.subheader('运行状态')
    st.write('API Key：', '已配置' if api_key and not api_key.startswith('请填写') else '未配置')
    st.write('模型：', model)
    st.write('接口：', base_url)
    if st.button('清空历史记忆'):
        clear_memory(); st.success('已清空历史。')
    st.caption('Streamlit Cloud 请在 App Settings → Secrets 中配置 LLM_API_KEY 等变量。')

history=load_memory()
left,right=st.columns([1.15,1])
with left:
    st.subheader('选题信息')
    major=st.text_input('专业', value='传播学（舆情分析方向）')
    grade=st.selectbox('年级', ['大一/课程论文','大二/课程论文','大三/学年论文','大四/毕业论文','研究生/课程论文'])
    direction=st.text_input('想做方向', value='AIGC 对短视频内容生产的影响')
    paper_type=st.selectbox('论文/项目类型', ['课程论文','毕业论文','创新创业项目','社会调查报告','竞赛项目'])
    preference=st.selectbox('研究偏好', ['问卷调查，容易落地','访谈研究，适合小样本','案例分析，适合材料型论文','数据分析，想做得更硬核','产品设计，想做原型展示'])
    keywords=st.text_input('关键词', value='AIGC、短视频、大学生、内容生产')
    extra_info=st.text_area('补充说明', value='希望题目不要太大，能做问卷，也能找到真实参考文献。')
    submitted=st.button('生成我的选题方案', type='primary')
with right:
    st.subheader('网页历史记忆')
    if history:
        for i in reversed(history[-5:]): st.markdown(f"**{i.get('direction','未填写方向')}**  \n{i.get('major','')} · {i.get('paper_type','')}  \n{i.get('created_at','')}")
    else: st.info('暂无历史。生成一次后，这里会出现你的选题记忆。')

if submitted:
    form={'major':major,'grade':grade,'direction':direction,'paper_type':paper_type,'preference':preference,'keywords':keywords,'extra_info':extra_info}
    lit=search_literature(' '.join([major,direction,keywords])); prompt=build_prompt(form, history)
    with st.spinner('正在生成选题方案...'):
        err=''
        try: result=call_remote_llm(prompt); status='远程大模型'
        except Exception as e: err=str(e); result=fallback_answer(form, history, err); status='本地备用'
        result=result.rstrip()+format_lit(lit); topics=extract_topics(result)
        history.append({'created_at':datetime.now().strftime('%Y-%m-%d %H:%M:%S'),'major':major,'grade':grade,'direction':direction,'paper_type':paper_type,'keywords':keywords,'chosen_focus':topics[0] if topics else '','topics':topics,'result':result,'literature':lit,'model_status':status})
        save_memory(history)
    st.success(f'生成完成：{status}')
    if err: st.warning(f'远程调用失败原因：{err}')
    st.subheader('AI 选题方案'); st.text_area('结果', value=result, height=620)
    st.subheader('真实文献候选')
    for i in lit: st.markdown(f"**{i['title']}**  \n{i['authors']} · {i['year']}  \n{i['journal']}  \n[查看 DOI/来源]({i['url']})")
