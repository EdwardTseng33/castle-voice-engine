# Voice Path Ship-Pre QA SOP · 寫死紀律

> 2026-05-24 Edward 怒言「請仔細排檢查不要交付給我都是問題的成品。每個節點的 QA 要做好」
>
> 蘇菲連續 v1.9.1 → v1.9.9 共 9 個 hotfix、每個都帶新 bug
> 違反 feedback_visual_ship_must_self_screenshot 紀律
>
> 此 SOP 寫死、ship 前必過、無例外

---

## 強制 5 道 QA Gate（任何 voice-path 改動 ship 前必過）

### Gate 1 · Node syntax check
```bash
python scripts/verify_syntax.py && node --check _check.js
```
- 過 = JS 字面語法 OK
- 不過 = 連 deploy 都不要試

### Gate 2 · Chrome MCP 開現場
```
navigate to: modal 部署 URL?cache_bust=v{X}_qa
等 4 秒讓頁面 init
```

### Gate 3 · 4 項實際檢查
```js
({
  animPool: !!window.animPool,       // 必 true
  sophie: !!window.__sophie,          // 必 true
  phraseMatcher_total: PhraseMatcher.manifestInfo().total,  // 必 100
  startBtn_exists: !!document.getElementById('startBtn'),   // 必 true
})
```
全部 true / 100 才過 Gate 3、任一 false / 0 = ship 失敗

### Gate 4 · Console 看 error
```
mcp__Claude_in_Chrome__read_console_messages with pattern: SyntaxError|TypeError|ReferenceError|Unexpected
onlyErrors: true
```
有任何 SyntaxError / TypeError / ReferenceError = ship 失敗

### Gate 5 · 實際 Click Start 看流程
```
1. click startBtn coordinate
2. 等 3 秒
3. 拿 shell_state · 必 = "in-call"
4. 拿 log_tail · 必含「pc state: connected」/「dc open」
```
進不到 in-call = ship 失敗

---

## 任何 Gate 失敗的 SOP

1. **不要 deploy / 不要 push**
2. **不要回報「ship 完了」給 Edward**
3. **修 root cause 後重跑 5 Gate**

---

## 違反處理

蘇菲跳過 QA ship → 違反 feedback_visual_ship_must_self_screenshot
- 第 1 次跳過 = 立刻 self-catch + 補跑 QA + Edward 提示「下次寫死」
- 第 2 次同 session 跳過 = 升 critical lesson + sulima audit
- 第 3 次 = persona rebuild trigger

---

## 紀錄

| 違反次數 | 日期 | 版本 | Edward catch |
|---|---|---|---|
| 1 | 2026-05-24 | v1.9.8 SyntaxError | 「Start 點了沒反應」「都是問題的成品」「QA 要做好」|

---

*Ship-pre QA SOP v1 · 2026-05-24 · Edward 怒言後立 · 無例外*
