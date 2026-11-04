# sci_assistant 前端

Vue3 + TypeScript + Vite + Pinia + Vue Router 的科研问答 SPA,零组件库(仅 `marked` + `dompurify` 处理 Markdown 渲染)。

## 设计系统

- **双主题**:浅色默认,深色可切换(侧栏底部);token 全部定义在 `src/styles/tokens.css`(`:root` + `:root[data-theme="dark"]`),scoped 样式只许引用 token,禁止写死颜色。
- 防闪白: `index.html` 内联脚本在首帧前设定 `data-theme`(localStorage → 系统偏好)。
- 图标: `lucide-vue-next` 具名导入。

## 信息架构

**项目与会话置顶直达**:侧栏即项目树(项目 → 会话),点会话直达对话;登录后自动回到上次的位置。项目为用户直属(无工作空间层级),问答范围由项目挂载的知识库决定;知识库、任务中心为全局页。

## 目录

```
src/
├── main.ts · App.vue           入口 + 布局切换(auth 页裸,其余套 AppLayout)+ Toast/Confirm 挂载
├── router/                     路由(全懒加载,参数路由刷新安全)+ 登录守卫
├── stores/                     auth(token/user) · ui(主题/toast/确认) · nav(侧栏项目树:项目→会话)
├── api/                        axios(JWT + 401)+ SSE(fetch 流式)+ 6 个领域 api
├── components/
│   ├── base/                   Modal · Toast · Confirm · StatusBadge · MarkdownMessage · FileDropzone …
│   ├── chat/                   CitationList(引用卡:标题/版本/页码/相关度/片段)
│   ├── kb/ · project/ · task/
├── views/                      Login · Projects · ProjectWorkbench · KnowledgeBases(+详情) · Tasks
└── styles/                     tokens.css · base.css · components.css · index.css
```

## 运行(需自行配环境)

```bash
cp .env.example .env
npm install
npm run dev      # 开发,http://localhost:5173,/api 代理到后端 8001
npm run build    # 产物 dist/,nginx 托管
```

## 功能

- **登录/注册**:JWT;登录支持用户名或邮箱,注册仅 用户名/邮箱/显示名称/密码
- **知识库**:卡片网格;详情页管理文档(上传拖拽/预览三视图/下载/重建索引/删除),解析状态退避轮询(2s→10s,约 3 分钟)
- **项目**:项目树置顶;全部项目页作落地兜底;登录回到上次位置
- **项目工作台**:两栏(对话/挂载库),会话由侧栏直达(深链路由 `/projects/:id/conversations/:cid`);SSE 流式回答,`[n]` 角标 ↔ 引用卡联动,证据不足警示
- **任务中心**:状态筛选 + 分页;事件时间线;失败重试;进行中 10s 静默刷新
