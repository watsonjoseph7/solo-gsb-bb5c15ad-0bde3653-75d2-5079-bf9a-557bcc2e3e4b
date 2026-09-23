# 🔁 URL 重写规则调试台

基于 **FastAPI + 原生 JavaScript** 的 URL 重写规则调试台。用户在左侧定义按顺序执行的
路径匹配、捕获组替换、重定向或内部改写规则，并输入一条请求路径；服务端逐步模拟整条
规则链，展示**每一次匹配、捕获组变量变化、响应状态与最终 URL**，并自动检测循环、
在超过步数上限时停止。支持规则语法错误精确定位、内置示例一键载入、调试结果复制、
**规则精简**与**规则变更回归检查**。

---

## ✨ 功能特性

- **顺序规则链**：自上而下逐行测试；`REWRITE` 改写后可继续下一条（`next`）或从头重启（`last`），`REDIRECT` 命中即终止。
- **逐步执行轨迹**：每条规则的命中 / 未命中、规则原文、行号、捕获组（`$0` 整匹配、数字组、命名组）、路径前后变化、流向标签。
- **最终结果**：HTTP 状态码（200 / 301 / 302 / 303 / 307 / 308 / 508 循环 / 509 超步数）、最终 URL、`Location` 响应头、执行步数 / 重定向跳数。
- **循环检测**：以 `(路径, 规则位置, 重定向跳数)` 为状态指纹，发现重复立即返回 **508 Loop Detected**，不会死循环。
- **步数上限**：默认 100 步（可调 1–500），超限返回 **509**；跟随重定向时最多 20 跳。
- **语法错误定位**：括号未闭合、组引用不存在、非法状态码、未知动作等错误给出**行号 + 列号**，点击错误即可跳转选中。
- **内置示例**：基础重定向、链式改写、循环检测、实战规则集、命名捕获组、语法错误示例，一键载入。
- **复制调试结果**：一键复制包含请求、最终状态、逐步轨迹与捕获组的纯文本报告。
- **✂️ 规则精简**：在左侧下方输入**多条待保障请求路径**（每行一条），沿用当前规则文本、步数上限与跟随重定向选项，贪心求出对每条路径的**最终状态码、最终 URL、Location、结束原因**都保持不变的规则子集。只删除完整有效规则行，注释、空行与其余规则的原文顺序原样保留；按原行号确定性地反复试探删行（每次删行后重新解析并模拟全部路径），直到剩余任一规则单独删除都会改变至少一条路径的结果（不追求全局最短）。结果弹窗给出可复制的精简规则、删除行号（点击可定位到编辑器对应行）以及各路径精简前后的结果对照；路径或规则有误时返回明确错误，**不会覆盖编辑器内容**。
- **场景分享链接**：一键生成包含规则文本、请求路径、步数上限与跟随重定向选项的链接；对方打开即恢复相同编辑状态。状态经**带版本号的 UTF-8 Base64URL** 编码后放在 URL 片段（`#v1=…`）中，**不会发送到服务端**；链接损坏、版本未知或字段非法时显示可见提示并保留默认界面。
- **🧪 规则变更回归检查**：在调试台额外填写**旧版规则**文本，以**当前编辑器内容作为新版**，输入多条请求路径（每行一条），沿用当前步数上限与跟随重定向选项。服务端**分别解析两套规则**并对每条路径各模拟一遍，按**最终状态码、最终 URL、Location、结束原因**四项标记变化路径；对每条变化路径逐个比对两侧**命中的改写 / 重定向动作及其输入输出**（跳过未命中步骤、忽略源码行号），显示**首次分叉**两侧的原行号、规则原文与动作的输入 / 输出；若两侧动作序列完全一致而最终结果不同（例如步数上限被数量不同的未命中步骤耗尽、一侧先触发循环），则显示**终止差异**。两侧规则的语法错误**分别提示**（点击可跳转到对应编辑器），**不覆盖任何已输入内容**。
- **单命令启动**：Docker Compose 或本地 uvicorn，前端为零构建原生 JS。

---

## 🚀 快速开始

### 方式一：Docker Compose（推荐，单命令）

```bash
docker compose up --build
```

启动后用浏览器打开：

> **http://localhost:8000**

端口映射为宿主机 **8000** → 容器 8000。停止用 `Ctrl+C`，后台运行用
`docker compose up -d --build`，停止并移除用 `docker compose down`。

### 方式二：本地 Python 运行

需要 Python 3.11+：

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

同样访问 http://localhost:8000 。

> 如需更换端口，修改 `docker-compose.yml` 中 `"宿主端口:8000"` 的左侧，
> 或调整 uvicorn 的 `--port` 参数即可。容器内服务固定监听 8000。

---

## 📖 规则语法

每行一条规则，以 `#` 开头（或行尾 ` #`）为注释，空行忽略。支持双引号包裹的参数
（用于包含空格或 `#` 的正则 / 替换串）。

### `REWRITE` —— 内部改写（URL 不变，继续走规则链）

```
REWRITE  <正则表达式>  <替换串>  [next|last]
```

| 参数 | 说明 |
| --- | --- |
| 正则 | Python 风格正则，**非锚定搜索**（与 nginx 一致，子串命中即匹配）；建议用 `^` / `$` 锚定 |
| 替换串 | `$0` 整匹配、`$1`..`$n` 第 n 个捕获组、`${1}` 歧义消除、`${name}` 命名组、`$$` 字面量 `$` |
| 标志 | 可省略，默认 `next`：替换后继续下一条；`last`：替换后**从第 1 条规则重新匹配** |

> **整路径替换**：`REWRITE` 命中后以替换串作为**整条新路径**（与 nginx/rewrite
> 一致），正则未捕获的部分不会自动保留——需要时用 `$0` 或 `(.*)` + `$1` 带上，
> 例如 `REWRITE ^/api/v1/(.*)$ /api/legacy/$1 next`。

### `REDIRECT` —— 重定向（规则链终止，返回 3xx）

```
REDIRECT  <正则表达式>  <替换串>  <状态码>
```

状态码可选：`301`（永久）、`302`（默认式临时）、`303`（See Other）、
`307`（临时保留方法）、`308`（永久保留方法）。

替换结果以单个 `/` 开头时视为**站内地址**；勾选「跟随站内重定向」后，浏览器发起
新请求、规则链从第 1 条重新模拟（计入跳数）。以 `http://`、`https://`、`//`
开头的站外地址不继续模拟。

### 执行模型

1. 规则从第 1 条开始，用正则依次测试当前路径；
2. 未命中 → 尝试下一条；全部未命中 → **200 内部放行**，当前路径即最终 URL；
3. `REWRITE` 命中 → 按捕获组替换路径，按 `next` / `last` 推进；
4. `REDIRECT` 命中 → 立即返回对应 3xx 与 `Location`；
5. 同一 `(路径, 规则下标, 跳数)` 状态再次出现 → **508 循环**；
6. 执行步数达到上限 → **509 超限停止**。

### 示例

```nginx
# /old/about 永久搬迁到 /about
REDIRECT ^/old/about$ /about 301

# 去掉 .html 后缀后继续下一条
REWRITE ^/docs/(.+)\.html$ /docs/$1 next

# docs 改名 help，并从头重新匹配
REWRITE ^/docs/(.+)$ /help/$1 last

# 命名捕获组：/zh/guide -> /index.php?lang=zh&page=guide
REWRITE ^/(?P<lang>[a-z]{2})/(?P<page>.+)$ /index.php?lang=${lang}&page=${page} next
```

---

## 🔗 场景分享链接

点击「🔗 复制分享链接」，当前编辑状态（**规则文本、请求路径、步数上限、跟随重定向
选项**）会被编码进链接并复制到剪贴板，同时同步到浏览器地址栏。任何人打开该链接，
四项内容都会原样恢复到编辑区（不会自动运行，点「运行调试」即可查看结果）。

链接格式：

```
http://localhost:8000/#v1=<Base64URL(JSON)>
```

- **仅存在于 URL 片段（`#` 之后）**：浏览器不会把片段发给服务端，规则文本不会出现在
  服务端访问日志里；`v1` 是格式版本号，JSON 以 **UTF-8** 序列化后再做 Base64URL
  （`-` / `_`，无填充），可安全放入链接、完整保留中文等多字节字符。
- **打开时严格校验**：载荷损坏（截断 / 非法 Base64URL / 非法 UTF-8 / 非法 JSON）、
  版本号未知、出现非约定字段或字段类型 / 取值非法（如步数越界、路径不以 `/` 开头）时，
  页面上方显示**可关闭的醒目提示**，编辑区保持默认界面不被污染，同时自动清除损坏片段。
- 片段并非分享链接（如普通页内锚点）时静默忽略；规则文本很长时链接也会很长，建议通过
  剪贴板直接粘贴发送，避免手工删改片段内容。

状态 JSON 的四个字段：

```json
{ "v": 1, "rules": "REWRITE ^/a$ /b next", "path": "/a",
  "max_steps": 100, "follow_redirects": false }
```

---

## ✂️ 规则精简

入口就在调试台首页左侧**规则编辑器下方的「规则精简」区**（也可使用快捷键
`Ctrl/Cmd + Shift + Enter`），无需打开新页面：

1. 在多行输入框中填入**多条待保障请求路径**，每行一条（自动忽略空行、去除首尾空白、按首次出现顺序去重，最多 50 条）；
2. 步数上限、跟随站内重定向选项直接**沿用页面上方**的当前设置，规则文本取编辑器当前内容；
3. 点击「✂️ 开始精简」。

算法在保证每条路径的 **HTTP 最终状态码、最终 URL、`Location` 响应头、结束原因**
四项完全不变的前提下：

- **只删除完整有效规则所在行**——注释、空行、有语法错误的行一律保留，其余行的原文顺序逐字节不动；
- 每一轮按**原行号从小到大**逐条试探，每次删行后都**重新解析整个规则文本并对全部路径重新模拟**；四项有任一项变化即放弃该次删除；
- 反复扫描直到一整轮没有任何规则可删：此时剩余规则中任取一条单独删除，都会改变至少一条路径的结果；
- 结果是一个**贪心不动点**，删除顺序确定、结果可复现，但**不保证全局最短**。

结果弹窗包含：删除条数与试探次数、**删除的原行号**（点击行号胶囊可在编辑器中定位该行）、
**可一键复制的精简规则文本**（只复制，不会写回编辑器），以及每条路径精简**前 / 后**的
状态码、最终 URL、Location、结束原因四格对照（有差异的字段会标红）。

输入路径不合法（为空、不以 `/` 开头、含空白、超过 50 条等）或规则文本存在语法错误时，
会通过弹窗提示 / 错误列表明确报错，**编辑器与已输入内容不会被覆盖**。

单条命令启动后访问入口：

```bash
docker compose up --build   # 然后打开 http://localhost:8000 ，规则精简区在左侧编辑器下方
```

---

## 🧪 规则变更回归检查

改动线上规则前，用它确认一批真实请求路径在新版规则下的命运是否与旧版一致。入口就在
调试台首页左侧最下方的「🧪 规则变更回归检查」区（也可使用快捷键
`Ctrl/Cmd + Alt + Enter`）：

1. 在「旧版规则」框中粘贴变更前的规则文本（留空表示旧版没有任何规则，框体可折叠收起）；
2. **新版规则直接取当前编辑器内容**，无需复制两遍；
3. 在多行输入框填入回归请求路径，每行一条（自动忽略空行、去除首尾空白、按首次出现顺序去重，最多 50 条）；
4. 步数上限、跟随站内重定向选项**沿用页面上方**的当前设置，点击「🧪 开始回归检查」。

服务端对两套规则**分别独立解析**，再对每条路径各模拟一次：

- **结果标记**：以 **HTTP 最终状态码、最终 URL、`Location`、结束原因** 四项作为指纹，
  任一项不同即标记为「✗ 结果变化」，结果弹窗按路径给出旧 / 新四格对照（变化字段标红）；
- **首次分叉定位**：对每条变化路径，只抽取两侧**命中的动作**（`REWRITE` / `REDIRECT`），
  按「动作类型 + 输入路径 + 输出目标（重定向还含状态码）」逐个对齐比较——
  **未命中步骤不计入、源码行号与书写风格不参与比较**；第一个对不上的动作即首次分叉，
  弹窗并列展示两侧的**原行号、规则原文、路径输入 / 输出**（一侧已无更多命中动作时
  明确标注「无更多命中动作」）；
- **终止差异**：若两侧命中动作序列逐项一致、最终结果却不同（差异只能来自终止方式，
  例如新版多出来的未命中规则耗尽了步数上限导致 508 循环变成 509 超步），
  则改为列出状态码 / 最终 URL / Location / 结束原因中真正不同的字段；
- **语法错误分别提示**：旧版与新版的解析错误在结果弹窗中分两块列出，均带行 / 列定位，
  点击任一条即可跳转到**对应**规则框的出错位置；检查过程**不会覆盖编辑器与旧版规则框
  的任何内容**。

```bash
docker compose up --build   # 然后打开 http://localhost:8000 ，回归检查区在左侧最下方
```

---

## 🔌 HTTP API

### `POST /api/debug`

```json
{
  "rules": "REWRITE ^/a/ /b/ next",
  "path": "/a/x",
  "max_steps": 100,
  "follow_redirects": false
}
```

成功响应（关键字段）：

```json
{
  "ok": true,
  "rule_count": 1,
  "trace": [
    { "seq": 1, "type": "rewrite", "line": 1, "rule": "REWRITE ^/a/ /b/ next",
      "matched": true, "path": "/a/x", "new_path": "/b/x",
      "groups": [{ "index": 0, "name": null, "value": "/a/" }],
      "flow": "next：继续下一条", "status": null, "location": null }
  ],
  "result": {
    "final_url": "/b/x",
    "status": 200,
    "location": null,
    "finish_reason": "fallthrough",
    "steps": 1,
    "hops": 0
  }
}
```

语法错误响应（`errors` 中含 `line` / `col` / `length` / `message`）：

```json
{ "ok": false, "rule_count": 0, "errors": [
  { "line": 1, "col": 18, "length": 1, "message": "正则表达式错误：missing ), unterminated subpattern", "source": "..." }
] }
```

### `POST /api/minimize`

对多条请求路径求结果保持不变的规则子集（贪心删行）：

```json
{
  "rules": "REWRITE ^/a/ /b/ next\nREWRITE ^/unused/ /zz/ next",
  "paths": ["/a/x", "  /a/y  "],
  "max_steps": 100,
  "follow_redirects": false
}
```

成功响应：

```json
{
  "ok": true,
  "paths": ["/a/x", "/a/y"],
  "removed_lines": [2],
  "minimized_rules": "REWRITE ^/a/ /b/ next\n",
  "original_rule_count": 2,
  "minimized_rule_count": 1,
  "attempts": 3,
  "results": [
    {
      "path": "/a/x",
      "unchanged": true,
      "before": { "status": 200, "final_url": "/b/x", "location": null,
                  "finish_reason": "fallthrough", "steps": 1, "hops": 0 },
      "after":  { "status": 200, "final_url": "/b/x", "location": null,
                  "finish_reason": "fallthrough", "steps": 1, "hops": 0 }
    }
  ]
}
```

规则语法错误时同样返回 `200` 且 `ok: false`、`errors` 为行列定位列表；
路径不合法（为空 / 不以 `/` 开头 / 含空白 / 超过 50 条）或 `max_steps` 越界返回 `422`。

### `POST /api/regression`

规则变更回归检查：`old_rules` 为旧版规则，`rules` 为新版（对应页面当前编辑器），
其余选项含义与 `/api/debug` 一致：

```json
{
  "old_rules": "REWRITE ^/a/(.*)$ /b/$1 next\nREDIRECT ^/old$ /new 302",
  "rules": "REWRITE ^/a/(.*)$ /c/$1 next\nREDIRECT ^/old$ /new 301",
  "paths": ["/a/x", "/old"],
  "max_steps": 100,
  "follow_redirects": false
}
```

成功响应（每条路径给出旧 / 新最终结果、变化字段与首次分叉）：

```json
{
  "ok": true,
  "total": 2,
  "changed_count": 1,
  "old_rule_count": 2,
  "new_rule_count": 2,
  "paths": [
    {
      "path": "/a/x",
      "changed": true,
      "old": { "status": 200, "final_url": "/b/x", "location": null, "finish_reason": "fallthrough", "steps": 1, "hops": 0 },
      "new": { "status": 200, "final_url": "/c/x", "location": null, "finish_reason": "fallthrough", "steps": 1, "hops": 0 },
      "field_changes": [{ "field": "final_url", "old": "/b/x", "new": "/c/x" }],
      "old_hit_count": 1,
      "new_hit_count": 1,
      "divergence": {
        "type": "action",
        "index": 1,
        "reason": "动作的输出目标不同",
        "old_action": { "kind": "rewrite", "line": 1, "rule": "REWRITE ^/a/(.*)$ /b/$1 next",
                        "input": "/a/x", "output": "/b/x", "status": null },
        "new_action": { "kind": "rewrite", "line": 1, "rule": "REWRITE ^/a/(.*)$ /c/$1 next",
                        "input": "/a/x", "output": "/c/x", "status": null }
      }
    }
  ]
}
```

- `divergence.type` 为 `"action"` 时表示首次命中动作分叉（行号仅用于展示，不参与比较），
  一侧已无更多命中动作时对应 `old_action` / `new_action` 为 `null`；
- `divergence.type` 为 `"terminal"` 时动作序列完全一致，`terminal_diff` 列出终止结果中
  真正不同的字段（如 `508 loop` ↔ `509 step_limit`）；
- 无变化路径的 `changed` 为 `false`、`divergence` 为 `null`。

两侧语法错误分别返回（**不覆盖输入**）：

```json
{ "ok": false,
  "old_rule_count": 1, "new_rule_count": 0,
  "errors": {
    "old": [],
    "new": [{ "line": 1, "col": 16, "length": 1, "message": "正则表达式错误：missing ), unterminated subpattern", "source": "..." }]
  } }
```

路径不合法（为空 / 不以 `/` 开头 / 含空白 / 超过 50 条）或 `max_steps` 越界返回 `422`；
新旧任一单侧有效规则超过 400 条返回 `400`。

其余端点：`GET /api/examples`（内置示例）、`GET /healthz`（健康检查）、
`GET /`（调试台页面）、交互式文档 `GET /docs`。

---

## 🗂 项目结构

```
.
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── README.md
└── app
    ├── __init__.py
    ├── main.py          # FastAPI 入口（/api/debug、/api/minimize、/api/regression、静态页面）
    ├── engine.py        # 词法/语法解析、错误定位、替换串展开
    ├── simulator.py     # 规则链逐步模拟、循环检测、步数上限
    ├── minimizer.py     # 规则精简：按原行号贪心删行，删后重新解析并模拟全部路径
    ├── regression.py    # 规则变更回归检查：新旧规则分别解析模拟，定位首次动作分叉/终止差异
    ├── examples.py      # 内置示例
    └── static
        ├── index.html   # 调试台页面（含规则精简、规则变更回归检查入口与结果弹窗）
        ├── style.css
        ├── share.js     # 场景分享编解码（带版本号 UTF-8 Base64URL，纯函数可单测）
        └── app.js       # 原生 JS（编辑器、轨迹渲染、复制报告、精简、回归检查、分享恢复）
```

## ⚠️ 说明

- 本工具用于**规则逻辑的教学与调试**，正则在服务端直接编译执行，请勿在不可信环境暴露给公网用于执行他人提交的复杂正则（ReDoS 风险）；步数上限只约束规则执行次数，不限制单条正则自身的回溯开销。
- 调试台只模拟路径（含查询串）的变换，不涉及真实后端转发与域名拼接。
