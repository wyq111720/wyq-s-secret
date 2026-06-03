# 专属选题管家 Streamlit Cloud 版

这是可以直接部署到 Streamlit Cloud 的版本。

## 本地运行
```powershell
python -m pip install -r requirements.txt
streamlit run streamlit_app.py
```

## 上传到 Streamlit Cloud
1. 把整个文件夹上传到 GitHub。
2. Streamlit Cloud 新建 App。
3. Main file path 填：`streamlit_app.py`。
4. App settings → Secrets 填：
```toml
LLM_PROVIDER="ZhipuAI"
LLM_API_KEY="你的智谱APIKey"
LLM_BASE_URL="https://open.bigmodel.cn/api/paas/v4/"
LLM_MODEL="glm-4-flash"
ENABLE_LIVE_LITERATURE="false"
```
5. Deploy。

不要把真实 API Key 上传到公开 GitHub 仓库。
